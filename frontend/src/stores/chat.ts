import { defineStore } from 'pinia';
import { ref, nextTick } from 'vue';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  isTemporary?: boolean;
  corrections?: Array<{
    original: string;
    corrected: string;
    explanation: string;
    correctedSentence?: string;
    severity?: string;
    type: 'grammar' | 'pronunciation' | 'vocabulary';
  }>;
  pronunciation_score?: number;
  pronunciation_tip?: string;
  pronunciation_source?: 'iflytek_ise' | 'text_analysis';
  pronunciation_words?: Array<{ word: string; score: number; error_phonemes?: string[] }>;
  pronunciationPending?: boolean;
  utteranceId?: string;
  audioBlob?: Blob;
  audioUrl?: string;
  audioSegments?: Blob[];
}

export interface ConnectionStatus {
  connected: boolean;
  connecting: boolean;
  error: string | null;
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([]);
  const connectionStatus = ref<ConnectionStatus>({
    connected: false,
    connecting: false,
    error: null,
  });
  const isRecording = ref(false);
  const isAiSpeaking = ref(false);
  const isPaused = ref(false);
  const ttsEnabled = ref(true);
  const currentSessionId = ref<string | null>(null);
  const sceneId = ref<number | null>(null);
  const coachingEnabled = ref(false);
  const pronunciationSkipHint = ref<string | null>(null);

  const COACHING_PREF_KEY = 'coachingTogglePref';

  function findUserMessageForUtterance(
    utteranceId?: string,
    sentenceText?: string,
  ): ChatMessage | undefined {
    if (utteranceId) {
      const byId = messages.value.find(
        (m) => m.role === 'user' && (m.utteranceId === utteranceId || m.id === utteranceId),
      );
      if (byId) return byId;
    }
    const normalized = (sentenceText || '').trim();
    if (normalized) {
      const byText = [...messages.value].reverse().find(
        (m) => m.role === 'user' && m.content.trim() === normalized,
      );
      if (byText) return byText;
    }
    return [...messages.value].reverse().find(
      (m) => m.role === 'user' && !m.pronunciation_score,
    );
  }

  function attachPronunciationFeedback(payload: Record<string, unknown>) {
    const utteranceId = payload.utterance_id as string | undefined;
    const sentenceText = payload.sentence_text as string | undefined;
    const target = findUserMessageForUtterance(utteranceId, sentenceText);
    if (!target) {
      console.warn('pronunciation_feedback: no matching user message', payload);
      return;
    }
    target.pronunciationPending = false;
    target.pronunciation_score = payload.overall_score as number;
    target.pronunciation_tip = payload.brief_tip as string | undefined;
    target.pronunciation_source = payload.source as ChatMessage['pronunciation_source'];
    if (utteranceId) target.utteranceId = utteranceId;
    if (Array.isArray(payload.word_scores)) {
      target.pronunciation_words = payload.word_scores as ChatMessage['pronunciation_words'];
    }
  }

  /** AI 朗读使用浏览器 SpeechSynthesis，不播放服务端 TTS 音频。 */
  const useBrowserTts = true;

  let ws: WebSocket | null = null;
  let connectTimeout: ReturnType<typeof setTimeout> | null = null;
  let messageIdCounter = 0;
  let currentInterruptId: string | null = null;
  let currentAudio: HTMLAudioElement | null = null;
  let playbackSpeed = 1.0;

  // Fallback queue when Web Audio decode fails
  let ttsFallbackQueue: Blob[] = [];
  let ttsPlaying = false;
  let activeTtsInterruptId: string | null = null;
  let streamingInterruptId: string | null = null;
  let streamAiMsgId: string | null = null;
  let webAudioContext: AudioContext | null = null;
  let ttsScheduleTime = 0;
  let ttsActiveSources = 0;
  let ttsDecodeChain: Promise<void> = Promise.resolve();
  let ttsPlaybackGeneration = 0;
  /** Message ID that may still receive server TTS (avoid SpeechSynthesis double-play on replay). */
  let ttsExpectedMsgId: string | null = null;

  function setPlaybackSpeed(speed: number) {
    playbackSpeed = speed;
    if (currentAudio) {
      currentAudio.playbackRate = speed;
    }
  }

  async function ensureWebAudioContext(): Promise<AudioContext | null> {
    if (!webAudioContext || webAudioContext.state === 'closed') {
      webAudioContext = new AudioContext();
      ttsScheduleTime = 0;
    }
    if (webAudioContext.state === 'suspended') {
      await webAudioContext.resume();
    }
    return webAudioContext;
  }

  function onTtsSourceEnded() {
    ttsActiveSources = Math.max(0, ttsActiveSources - 1);
    if (ttsActiveSources === 0) {
      ttsPlaying = false;
      isAiSpeaking.value = false;
      isPaused.value = false;
      clearTtsExpectedIfIdle();
    }
  }

  // --- TTS (Speech Synthesis) ---
  function _getTtsVoiceKey(): string {
    return localStorage.getItem('ttsVoice') || 'en-US-female';
  }

  function _pickBrowserVoice(voiceKey: string): SpeechSynthesisVoice | undefined {
    if (!window.speechSynthesis) return undefined;
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return undefined;

    const isGB = voiceKey.startsWith('en-GB');
    const wantFemale = voiceKey.includes('female');
    const langPrefix = isGB ? 'en-gb' : 'en-us';
    const pool = voices.filter((v) =>
      v.lang.replace('_', '-').toLowerCase().startsWith(langPrefix),
    );
    const searchIn = pool.length
      ? pool
      : voices.filter((v) => v.lang.toLowerCase().startsWith('en'));
    const femaleHints = ['female', 'jenny', 'sonia', 'zira', 'samantha', 'victoria', 'aria'];
    const maleHints = ['male', 'guy', 'ryan', 'david', 'mark', 'alex', 'guy'];
    const hints = wantFemale ? femaleHints : maleHints;
    return (
      searchIn.find((v) => hints.some((h) => v.name.toLowerCase().includes(h)))
      ?? searchIn[0]
    );
  }

  function speakText(text: string) {
    if (!ttsEnabled.value) return;
    if (!window.speechSynthesis) return;
    const trimmed = text.trim();
    if (!trimmed) return;

    stopLocalPlayback();

    const voiceKey = _getTtsVoiceKey();
    const utterance = new SpeechSynthesisUtterance(trimmed);
    utterance.lang = voiceKey.startsWith('en-GB') ? 'en-GB' : 'en-US';
    utterance.rate = playbackSpeed;
    utterance.pitch = 1.0;

    const preferredVoice = _pickBrowserVoice(voiceKey);
    if (preferredVoice) utterance.voice = preferredVoice;

    utterance.onstart = () => { isAiSpeaking.value = true; };
    utterance.onend = () => {
      isAiSpeaking.value = false;
      clearTtsExpectedIfIdle();
    };
    utterance.onerror = () => {
      isAiSpeaking.value = false;
      clearTtsExpectedIfIdle();
    };

    // Chrome can emit duplicate output if speak() runs in the same turn as cancel().
    window.setTimeout(() => window.speechSynthesis.speak(utterance), 0);
  }

  function speakAiResponse(text: string) {
    if (!useBrowserTts) return;
    speakText(text);
  }

  function isTtsExpectedForMessage(msgId: string): boolean {
    return ttsExpectedMsgId === msgId;
  }

  function clearTtsExpectedIfIdle() {
    if (
      ttsActiveSources === 0
      && !ttsPlaying
      && !currentAudio
      && ttsFallbackQueue.length === 0
    ) {
      ttsExpectedMsgId = null;
    }
  }

  function pauseAudio() {
    if (webAudioContext && webAudioContext.state === 'running') {
      webAudioContext.suspend().catch(() => {});
      isPaused.value = true;
    }
    if (currentAudio && !currentAudio.paused) {
      currentAudio.pause();
      isPaused.value = true;
    }
    if (window.speechSynthesis && window.speechSynthesis.speaking) {
      window.speechSynthesis.pause();
      isPaused.value = true;
    }
  }

  function resumeAudio() {
    if (webAudioContext && webAudioContext.state === 'suspended') {
      webAudioContext.resume().catch(() => {});
      isPaused.value = false;
    }
    if (currentAudio && currentAudio.paused) {
      currentAudio.play().catch(() => {});
      isPaused.value = false;
    }
    if (window.speechSynthesis && window.speechSynthesis.paused) {
      window.speechSynthesis.resume();
      isPaused.value = false;
    }
  }

  function togglePause() {
    if (isPaused.value) {
      resumeAudio();
    } else {
      pauseAudio();
    }
  }

  function findAiMessageForTts(interruptId?: string | null): ChatMessage | undefined {
    if (interruptId) {
      const byId = messages.value.find((m) => m.id === interruptId);
      if (byId) return byId;
    }
    if (streamAiMsgId) {
      return messages.value.find((m) => m.id === streamAiMsgId);
    }
    return [...messages.value].reverse().find((m) => m.role === 'assistant');
  }

  function appendTtsSegmentToMessage(msg: ChatMessage, blob: Blob) {
    if (!msg.audioSegments) msg.audioSegments = [];
    msg.audioSegments.push(blob);
    if (msg.audioUrl) URL.revokeObjectURL(msg.audioUrl);
    msg.audioBlob = blob;
    msg.audioUrl = URL.createObjectURL(blob);
  }

  function base64ToBlob(base64: string, mime: string): Blob {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: mime || 'audio/mp3' });
  }

  function stopAudioEngine() {
    ttsPlaybackGeneration += 1;
    if (webAudioContext) {
      webAudioContext.close().catch(() => {});
      webAudioContext = null;
    }
    ttsScheduleTime = 0;
    ttsActiveSources = 0;
    ttsFallbackQueue = [];
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.onended = null;
      currentAudio = null;
    }
  }

  /** Stop local playback only — does not send WS interrupt (for replay / dict). */
  function stopLocalPlayback() {
    clearTtsQueue();
    stopAudioEngine();
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    isAiSpeaking.value = false;
    isPaused.value = false;
  }

  async function decodeTtsBlob(blob: Blob, generation: number): Promise<AudioBuffer | null> {
    if (generation !== ttsPlaybackGeneration) return null;
    const ctx = await ensureWebAudioContext();
    if (!ctx || generation !== ttsPlaybackGeneration) return null;
    try {
      return await ctx.decodeAudioData(await blob.arrayBuffer());
    } catch {
      return null;
    }
  }

  function scheduleDecodedBuffer(audioBuffer: AudioBuffer, generation: number) {
    if (generation !== ttsPlaybackGeneration || !webAudioContext || webAudioContext.state === 'closed') {
      return;
    }
    const ctx = webAudioContext;
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.playbackRate.value = playbackSpeed;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    if (ttsScheduleTime < now) {
      ttsScheduleTime = now;
    }
    const startAt = ttsScheduleTime;
    const duration = audioBuffer.duration / playbackSpeed;
    ttsScheduleTime = startAt + duration;

    ttsActiveSources += 1;
    ttsPlaying = true;
    isAiSpeaking.value = true;
    isPaused.value = false;

    source.onended = () => onTtsSourceEnded();
    source.start(startAt);
  }

  function scheduleTtsBlob(blob: Blob) {
    const generation = ttsPlaybackGeneration;
    const decodePromise = decodeTtsBlob(blob, generation);

    ttsDecodeChain = ttsDecodeChain.then(async () => {
      if (generation !== ttsPlaybackGeneration || !ttsEnabled.value) return;

      const audioBuffer = await decodePromise;
      if (!audioBuffer || generation !== ttsPlaybackGeneration) {
        if (generation === ttsPlaybackGeneration) {
          ttsFallbackQueue.push(blob);
          playNextTtsSegmentFallback(generation);
        }
        return;
      }
      if (!webAudioContext || webAudioContext.state === 'closed') {
        await ensureWebAudioContext();
      }
      scheduleDecodedBuffer(audioBuffer, generation);
    });
  }

  function scheduleTtsBlobBatch(blobs: Blob[]) {
    if (!blobs.length) return;
    const generation = ttsPlaybackGeneration;
    const decodePromises = blobs.map((blob) => decodeTtsBlob(blob, generation));

    ttsDecodeChain = ttsDecodeChain.then(async () => {
      if (generation !== ttsPlaybackGeneration || !ttsEnabled.value) return;

      const buffers = await Promise.all(decodePromises);
      if (!webAudioContext || webAudioContext.state === 'closed') {
        await ensureWebAudioContext();
      }

      let queuedFallback = false;
      for (let i = 0; i < blobs.length; i++) {
        if (generation !== ttsPlaybackGeneration) return;
        const audioBuffer = buffers[i];
        if (audioBuffer) {
          scheduleDecodedBuffer(audioBuffer, generation);
        } else {
          ttsFallbackQueue.push(blobs[i]);
          queuedFallback = true;
        }
      }
      if (queuedFallback) {
        playNextTtsSegmentFallback(generation);
      }
    });
  }

  function playTtsBlobFallback(blob: Blob, generation = ttsPlaybackGeneration) {
    if (generation !== ttsPlaybackGeneration) return;
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.onended = null;
      currentAudio = null;
    }
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.playbackRate = playbackSpeed;
    currentAudio = audio;
    ttsPlaying = true;
    isAiSpeaking.value = true;
    isPaused.value = false;
    audio.onended = () => {
      if (generation !== ttsPlaybackGeneration) {
        URL.revokeObjectURL(url);
        return;
      }
      URL.revokeObjectURL(url);
      currentAudio = null;
      ttsPlaying = false;
      playNextTtsSegmentFallback(generation);
      clearTtsExpectedIfIdle();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      currentAudio = null;
      ttsPlaying = false;
      playNextTtsSegmentFallback(generation);
    };
    audio.play().catch(() => {
      URL.revokeObjectURL(url);
      currentAudio = null;
      ttsPlaying = false;
      playNextTtsSegmentFallback(generation);
    });
  }

  function playNextTtsSegmentFallback(generation = ttsPlaybackGeneration) {
    if (generation !== ttsPlaybackGeneration) return;
    if (ttsFallbackQueue.length === 0 || !ttsEnabled.value || currentAudio) {
      if (ttsActiveSources === 0 && !currentAudio) {
        ttsPlaying = false;
        isAiSpeaking.value = false;
        isPaused.value = false;
      }
      return;
    }
    const blob = ttsFallbackQueue.shift()!;
    playTtsBlobFallback(blob, generation);
  }

  function enqueueTtsChunk(
    base64: string,
    mime: string,
    interruptId?: string | null,
  ) {
    if (!ttsEnabled.value || useBrowserTts) return;
    const blob = base64ToBlob(base64, mime);
    const targetMsg = findAiMessageForTts(interruptId ?? activeTtsInterruptId);
    if (targetMsg) {
      appendTtsSegmentToMessage(targetMsg, blob);
    }
    if (interruptId) {
      activeTtsInterruptId = interruptId;
      if (streamAiMsgId === interruptId) {
        streamAiMsgId = null;
      }
    }
    scheduleTtsBlob(blob);
  }

  function clearTtsQueue() {
    ttsFallbackQueue = [];
    ttsPlaying = false;
    activeTtsInterruptId = null;
  }

  function sendInterrupt() {
    if (ws && ws.readyState === WebSocket.OPEN && streamingInterruptId) {
      ws.send(JSON.stringify({
        type: 'interrupt',
        payload: {
          interrupt_id: streamingInterruptId,
          session_id: currentSessionId.value,
        },
      }));
    }
    clearTtsQueue();
    stopAudioEngine();
  }

  function stopSpeaking() {
    sendInterrupt();
    stopAudioEngine();
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    isAiSpeaking.value = false;
    isPaused.value = false;
  }

  function toggleTts() {
    ttsEnabled.value = !ttsEnabled.value;
    if (!ttsEnabled.value) {
      stopSpeaking();
    }
  }

  function clearConnectTimeout() {
    if (connectTimeout) {
      clearTimeout(connectTimeout);
      connectTimeout = null;
    }
  }

  function failConnection(message: string) {
    clearConnectTimeout();
    connectionStatus.value = {
      connected: false,
      connecting: false,
      error: message,
    };
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      ws.close();
    }
    ws = null;
  }

  function buildWsUrl(token: string): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/api/v1/ws?token=${encodeURIComponent(token)}`;
  }

  function connect(
    sessionId: string,
    token: string,
    options?: { sceneId?: number },
  ) {
    if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    currentSessionId.value = sessionId;
    sceneId.value = options?.sceneId ?? null;
    const savedPref = localStorage.getItem(COACHING_PREF_KEY);
    coachingEnabled.value = savedPref === 'true';
    connectionStatus.value = { connected: false, connecting: true, error: null };
    clearTtsQueue();
    streamAiMsgId = null;
    streamingInterruptId = null;
    ttsExpectedMsgId = null;

    const url = buildWsUrl(token);

    clearConnectTimeout();
    connectTimeout = setTimeout(() => {
      if (connectionStatus.value.connecting) {
        failConnection('连接超时，请确认后端已启动（端口 8000）并刷新页面');
      }
    }, 15000);

    ws = new WebSocket(url);

    ws.onopen = () => {
      if (window.speechSynthesis) {
        window.speechSynthesis.getVoices();
      }
      ws!.send(JSON.stringify({
        type: 'start_session',
        payload: {
          session_id: sessionId,
          scene_id: sceneId.value,
          config: {
            audio_format: 'pcm_s16le',
            tts_voice: _getTtsVoiceKey(),
            browser_tts: useBrowserTts,
            coaching_enabled: coachingEnabled.value,
          },
          custom_scene: JSON.parse(sessionStorage.getItem('activeCustomScene') || 'null'),
        },
      }));
      if (coachingEnabled.value) {
        sendSetCoaching(true);
      }
    };

    ws.onmessage = (event) => {
      try {
        // Handle binary TTS audio frames (ignore for now)
        if (event.data instanceof Blob || event.data instanceof ArrayBuffer) {
          return;
        }

        const data = JSON.parse(event.data);
        const payload = data.payload || {};

        switch (data.type) {
          case 'asr_partial': {
            const partialText = payload.text;
            if (partialText) {
              const pending = [...messages.value].reverse().find(
                (m) => m.role === 'user' && m.isTemporary && !m.utteranceId,
              );
              if (pending) {
                pending.content = partialText;
              } else {
                messages.value.push({
                  id: `user-${++messageIdCounter}`,
                  role: 'user',
                  content: partialText,
                  timestamp: new Date().toISOString(),
                  isTemporary: true,
                });
              }
            }
            break;
          }

          case 'tts_audio': {
            if (useBrowserTts) break;
            const ttsPayload = data.payload || {};
            if (!ttsEnabled.value) break;
            const ttsInterruptId = ttsPayload.interrupt_id || null;
            if (ttsPayload.audio_base64) {
              enqueueTtsChunk(
                ttsPayload.audio_base64,
                ttsPayload.audio_mime || 'audio/mp3',
                ttsInterruptId,
              );
            } else if (ttsPayload.text) {
              const fallbackMsg = findAiMessageForTts(ttsInterruptId);
              const hasAudio = (fallbackMsg?.audioSegments?.length ?? 0) > 0
                || ttsPlaying
                || ttsActiveSources > 0
                || ttsFallbackQueue.length > 0;
              if (!hasAudio) {
                speakText(fallbackMsg?.content || ttsPayload.text);
              }
            }
            if (ttsPayload.is_end && ttsInterruptId && ttsExpectedMsgId === ttsInterruptId) {
              ttsExpectedMsgId = null;
            }
            break;
          }

          case 'session_ready': {
            clearConnectTimeout();
            connectionStatus.value = { connected: true, connecting: false, error: null };
            // Sync session ID from server (in case server reused or created a new one)
            if (payload.session_id) {
              currentSessionId.value = payload.session_id;
            }
            if (payload.negotiated_config?.coaching_enabled != null) {
              coachingEnabled.value = !!payload.negotiated_config.coaching_enabled;
            }
            // Display AI's opening line
            const firstMsg = payload.ai_first_message;
            if (firstMsg?.text) {
              const openingId = firstMsg.utterance_id || `ai-${++messageIdCounter}`;
              activeTtsInterruptId = openingId;
              ttsExpectedMsgId = openingId;
              messages.value.push({
                id: openingId,
                role: 'assistant',
                content: firstMsg.text,
                timestamp: new Date().toISOString(),
                isTemporary: false,
                audioSegments: [],
              });
              // Opening line is complete; do not reuse its id for the next LLM stream.
              streamAiMsgId = null;
              speakAiResponse(firstMsg.text);
            }
            break;
          }

          case 'asr_final': {
            const asrText = (payload.text as string || '').trim();
            const utteranceId = payload.utterance_id as string | undefined;
            if (!asrText) break;

            const pending = [...messages.value].reverse().find(
              (m) => m.role === 'user'
                && !m.utteranceId
                && (m.isTemporary || m.content.trim() === asrText || m.content === '...'),
            );
            if (pending) {
              pending.content = asrText;
              pending.isTemporary = false;
              if (utteranceId) pending.utteranceId = utteranceId;
              if (coachingEnabled.value && pending.pronunciation_score == null) {
                pending.pronunciationPending = true;
              }
            } else if (!findUserMessageForUtterance(utteranceId, asrText)) {
              messages.value.push({
                id: utteranceId || `user-${++messageIdCounter}`,
                role: 'user',
                content: asrText,
                timestamp: new Date().toISOString(),
                utteranceId,
              });
            }
            break;
          }

          case 'llm_response_delta': {
            const delta = payload.text || '';
            streamingInterruptId = payload.interrupt_id || streamingInterruptId;
            let aiMsg = streamAiMsgId
              ? messages.value.find((m) => m.id === streamAiMsgId && m.isTemporary)
              : undefined;
            if (!aiMsg) {
              clearTtsQueue();
              stopAudioEngine();
              const newId = payload.interrupt_id || `ai-${++messageIdCounter}`;
              streamAiMsgId = newId;
              activeTtsInterruptId = newId;
              ttsExpectedMsgId = newId;
              aiMsg = {
                id: newId,
                role: 'assistant',
                content: '',
                timestamp: new Date().toISOString(),
                isTemporary: true,
                audioSegments: [],
              };
              messages.value.push(aiMsg);
            }
            if (aiMsg) {
              aiMsg.content += delta;
            }
            break;
          }

          case 'tts_audio_chunk': {
            if (!ttsEnabled.value || useBrowserTts) break;
            streamingInterruptId = payload.interrupt_id || streamingInterruptId;
            if (payload.audio_base64) {
              enqueueTtsChunk(
                payload.audio_base64,
                payload.audio_mime || 'audio/mp3',
                payload.interrupt_id || streamingInterruptId,
              );
            }
            break;
          }

          case 'tts_cancelled': {
            clearTtsQueue();
            stopAudioEngine();
            if (window.speechSynthesis) {
              window.speechSynthesis.cancel();
            }
            isAiSpeaking.value = false;
            ttsExpectedMsgId = null;
            break;
          }

          case 'llm_response_text': {
            const payload = data.payload || {};
            currentInterruptId = payload.interrupt_id || null;

            const lastMsg = messages.value[messages.value.length - 1];
            let spokenText = payload.text || '';
            if (lastMsg && lastMsg.role === 'assistant' && lastMsg.isTemporary) {
              lastMsg.content = payload.text || lastMsg.content;
              lastMsg.isTemporary = false;
              lastMsg.id = payload.interrupt_id || lastMsg.id;
              spokenText = lastMsg.content;
            } else if (!streamAiMsgId || !messages.value.find((m) => m.id === streamAiMsgId)) {
              messages.value.push({
                id: payload.interrupt_id || `ai-${++messageIdCounter}`,
                role: 'assistant',
                content: payload.text || '',
                timestamp: new Date().toISOString(),
                isTemporary: false,
              });
              spokenText = payload.text || '';
            } else {
              const streamed = messages.value.find((m) => m.id === streamAiMsgId);
              if (streamed?.isTemporary) {
                streamed.content = payload.text || streamed.content;
                streamed.isTemporary = false;
                spokenText = streamed.content;
              } else {
                messages.value.push({
                  id: payload.interrupt_id || `ai-${++messageIdCounter}`,
                  role: 'assistant',
                  content: payload.text || '',
                  timestamp: new Date().toISOString(),
                  isTemporary: false,
                });
                spokenText = payload.text || '';
              }
            }
            streamAiMsgId = null;
            ttsExpectedMsgId = null;
            currentInterruptId = payload.interrupt_id || null;
            speakAiResponse(spokenText);
            break;
          }

          case 'coaching_state': {
            coachingEnabled.value = !!payload.enabled;
            break;
          }

          case 'pronunciation_feedback': {
            pronunciationSkipHint.value = null;
            attachPronunciationFeedback(data.payload || {});
            break;
          }

          case 'pronunciation_skipped': {
            const skipPayload = data.payload || {};
            pronunciationSkipHint.value = skipPayload.message || '发音评测未完成';
            for (const m of messages.value) {
              if (m.role === 'user' && m.pronunciationPending) {
                m.pronunciationPending = false;
              }
            }
            break;
          }

          case 'grammar_hint':
            // Real-time grammar hints disabled; grammar available post-session only
            break;

          case 'session_ended': {
            connectionStatus.value.error = 'Session ended by server.';
            disconnect();
            break;
          }

          case 'error': {
            const payload = data.payload || {};
            failConnection(`[${payload.code}] ${payload.message}`);
            break;
          }

          case 'interrupt_ack': {
            // Server acknowledged our interrupt
            break;
          }
        }
      } catch {
        // ignore parse error for streaming binary
      }
    };

    ws.onerror = () => {
      if (connectionStatus.value.connecting) {
        failConnection('WebSocket 连接失败，请确认后端服务已启动');
      } else {
        connectionStatus.value = {
          connected: false,
          connecting: false,
          error: 'WebSocket connection error',
        };
      }
    };

    ws.onclose = () => {
      clearConnectTimeout();
      if (connectionStatus.value.connecting) {
        connectionStatus.value = {
          connected: false,
          connecting: false,
          error: '连接已断开，请刷新页面重试',
        };
      } else if (!connectionStatus.value.error) {
        connectionStatus.value = { connected: false, connecting: false, error: null };
      } else {
        connectionStatus.value.connecting = false;
        connectionStatus.value.connected = false;
      }
      ws = null;
    };
  }

  function sendSetCoaching(enabled: boolean) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
      type: 'set_coaching',
      payload: {
        session_id: currentSessionId.value,
        enabled,
      },
    }));
  }

  function setCoachingEnabled(enabled: boolean) {
    coachingEnabled.value = enabled;
    localStorage.setItem(COACHING_PREF_KEY, enabled ? 'true' : 'false');
    sendSetCoaching(enabled);
  }

  function sendEndSession() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'end_session',
        payload: {
          session_id: currentSessionId.value,
        },
      }));
      // Don't disconnect immediately — server needs time to process
      // The session_ended handler will call disconnect()
    }
  }

  function disconnect() {
    clearConnectTimeout();
    ws?.close();
    ws = null;
    connectionStatus.value = { connected: false, connecting: false, error: null };
    isAiSpeaking.value = false;
  }

  function sendMessage(text: string) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectionStatus.value.error = 'Not connected to chat server';
      return;
    }

    // Stop AI speaking (user interruption)
    stopSpeaking();

    const userMsg: ChatMessage = {
      id: `user-${++messageIdCounter}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
      pronunciationPending: coachingEnabled.value,
    };
    messages.value.push(userMsg);

    ws.send(JSON.stringify({
      type: 'user_message',
      payload: {
        session_id: currentSessionId.value,
        text,
        coaching_enabled: coachingEnabled.value,
      },
    }));

    nextTick(() => {
      // Scroll handled by view component
    });
  }

  function sendAudioChunk(audioBlob: Blob, isEnd: boolean, text?: string) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = (reader.result as string).split(',')[1];
      ws!.send(JSON.stringify({
        type: 'audio_chunk',
        payload: {
          session_id: currentSessionId.value,
          audio_base64: base64,
          audio_mime: audioBlob.type || 'audio/webm',
          is_end: isEnd,
          text: text || undefined,
          coaching_enabled: coachingEnabled.value,
        },
      }));
    };
    reader.readAsDataURL(audioBlob);
  }

  function finalizeAudioRecording(audioBlob: Blob, text?: string) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectionStatus.value.error = 'Not connected to chat server';
      return;
    }

    stopSpeaking();

    const userMsg: ChatMessage = {
      id: `user-${++messageIdCounter}`,
      role: 'user',
      content: text?.trim() || '...',
      timestamp: new Date().toISOString(),
      isTemporary: true,
      pronunciationPending: coachingEnabled.value,
      audioBlob,
      audioUrl: URL.createObjectURL(audioBlob),
    };
    messages.value.push(userMsg);

    sendAudioChunk(audioBlob, true, text?.trim());
  }

  function sendAudio(audioBlob: Blob) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectionStatus.value.error = 'Not connected to chat server';
      return;
    }

    // Stop AI speaking (user interruption via voice)
    stopSpeaking();

    // Convert audio to base64 and send as JSON metadata frame
    // The server will respond with asr_final which creates the user bubble
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = (reader.result as string).split(',')[1]; // strip data:... prefix
      ws!.send(JSON.stringify({
        type: 'audio_data',
        payload: {
          session_id: currentSessionId.value,
          audio_base64: base64,
          audio_mime: audioBlob.type || 'audio/webm',
          is_end: true,
          coaching_enabled: coachingEnabled.value,
        },
      }));
    };
    reader.onerror = () => {
      connectionStatus.value.error = 'Failed to read audio data';
    };
    reader.readAsDataURL(audioBlob);
  }

  function sendMessageWithAudio(text: string, audioBlob: Blob) {
    // Create blob URL for playback
    const audioUrl = URL.createObjectURL(audioBlob);
    // Call sendMessage but attach audio to the user message
    sendMessage(text);
    // Find the just-created user message and attach audio
    const lastUser = [...messages.value].reverse().find(m => m.role === 'user');
    if (lastUser && !lastUser.audioBlob) {
      lastUser.audioBlob = audioBlob;
      lastUser.audioUrl = audioUrl;
    }
  }

  function playMessageAudio(msg: ChatMessage) {
    stopLocalPlayback();
    const generation = ttsPlaybackGeneration;

    if (msg.role === 'assistant' && msg.audioSegments?.length) {
      activeTtsInterruptId = msg.id;
      scheduleTtsBlobBatch(msg.audioSegments);
      return;
    }
    if (!msg.audioUrl && msg.audioBlob) {
      msg.audioUrl = URL.createObjectURL(msg.audioBlob);
    }
    if (msg.audioUrl) {
      const audio = new Audio(msg.audioUrl);
      audio.playbackRate = playbackSpeed;
      currentAudio = audio;
      ttsPlaying = true;
      isAiSpeaking.value = true;
      audio.onended = () => {
        if (generation !== ttsPlaybackGeneration) return;
        currentAudio = null;
        ttsPlaying = false;
        isAiSpeaking.value = false;
        clearTtsExpectedIfIdle();
      };
      audio.play().catch(() => {
        currentAudio = null;
        ttsPlaying = false;
        isAiSpeaking.value = false;
        clearTtsExpectedIfIdle();
      });
    }
  }

  function addTemporaryMessage(role: 'user' | 'assistant', content: string) {
    messages.value.push({
      id: `${role}-${++messageIdCounter}`,
      role,
      content,
      timestamp: new Date().toISOString(),
      isTemporary: true,
    });
  }

  function clearMessages() {
    messages.value = [];
  }

  return {
    messages,
    connectionStatus,
    isRecording,
    isAiSpeaking,
    isPaused,
    ttsEnabled,
    currentSessionId,
    sceneId,
    coachingEnabled,
    pronunciationSkipHint,
    connect,
    disconnect,
    sendMessage,
    sendAudio,
    sendAudioChunk,
    finalizeAudioRecording,
    setCoachingEnabled,
    sendMessageWithAudio,
    playMessageAudio,
    speakText,
    isTtsExpectedForMessage,
    stopSpeaking,
    stopLocalPlayback,
    pauseAudio,
    resumeAudio,
    togglePause,
    setPlaybackSpeed,
    toggleTts,
    addTemporaryMessage,
    sendEndSession,
    clearMessages,
  };
});