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
  audioBlob?: Blob;
  audioUrl?: string;
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

  let ws: WebSocket | null = null;
  let messageIdCounter = 0;
  let currentInterruptId: string | null = null;
  let currentAudio: HTMLAudioElement | null = null;

  // --- TTS (Speech Synthesis) ---
  function speakText(text: string) {
    if (!ttsEnabled.value) return;
    if (!window.speechSynthesis) return;

    // Stop any ongoing speech (interrupt)
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    utterance.rate = 0.9;  // slightly slower for learners
    utterance.pitch = 1.0;

    utterance.onstart = () => { isAiSpeaking.value = true; };
    utterance.onend = () => { isAiSpeaking.value = false; };
    utterance.onerror = () => { isAiSpeaking.value = false; };

    window.speechSynthesis.speak(utterance);
  }

  function pauseAudio() {
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

  function stopSpeaking() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
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

  function connect(sessionId: string, token: string, options?: { sceneId?: number }) {
    if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    currentSessionId.value = sessionId;
    sceneId.value = options?.sceneId ?? null;
    connectionStatus.value = { connected: false, connecting: true, error: null };

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//localhost:8000/api/v1/ws?token=${token}`;

    ws = new WebSocket(url);

    ws.onopen = () => {
      // Send start_session handshake per protocol
      ws!.send(JSON.stringify({
        type: 'start_session',
        payload: {
          session_id: sessionId,
          scene_id: sceneId.value,
        },
      }));
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
          case 'tts_audio': {
            // Single TTS trigger: Edge-TTS audio if available, SpeechSynthesis fallback
            const payload = data.payload || {};
            if (!ttsEnabled.value) break;
            if (payload.audio_base64) {
              // Play real Edge-TTS MP3 audio
              const binary = atob(payload.audio_base64);
              const bytes = new Uint8Array(binary.length);
              for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
              const blob = new Blob([bytes], { type: payload.audio_mime || 'audio/mp3' });
              const url = URL.createObjectURL(blob);
              const audio = new Audio(url);
              currentAudio = audio;
              isPaused.value = false;
              audio.play().catch(() => {});
              audio.onended = () => {
                URL.revokeObjectURL(url);
                currentAudio = null;
                isPaused.value = false;
              };
            } else if (payload.text) {
              // Fallback: browser SpeechSynthesis
              speakText(payload.text);
            }
            break;
          }

          case 'session_ready': {
            connectionStatus.value = { connected: true, connecting: false, error: null };
            // Sync session ID from server (in case server reused or created a new one)
            if (payload.session_id) {
              currentSessionId.value = payload.session_id;
            }
            // Display AI's opening line
            const firstMsg = payload.ai_first_message;
            if (firstMsg?.text) {
              messages.value.push({
                id: firstMsg.utterance_id || `ai-${++messageIdCounter}`,
                role: 'assistant',
                content: firstMsg.text,
                timestamp: new Date().toISOString(),
                isTemporary: false,
              });
            }
            break;
          }

          case 'asr_final': {
            // Final ASR transcription; display as user message if not already shown
            const asrText = payload.text;
            if (asrText) {
              const lastMsg = messages.value[messages.value.length - 1];
              if (lastMsg?.role === 'user' && lastMsg.isTemporary) {
                lastMsg.content = asrText;
                lastMsg.isTemporary = false;
              } else if (!lastMsg || lastMsg.role !== 'user' || lastMsg.content !== asrText) {
                messages.value.push({
                  id: `user-${++messageIdCounter}`,
                  role: 'user',
                  content: asrText,
                  timestamp: new Date().toISOString(),
                });
              }
            }
            break;
          }

          case 'llm_response_text': {
            const payload = data.payload || {};
            currentInterruptId = payload.interrupt_id || null;

            const lastMsg = messages.value[messages.value.length - 1];
            if (lastMsg && lastMsg.role === 'assistant' && lastMsg.isTemporary) {
              lastMsg.content += payload.text || '';
              if (payload.is_final) {
                lastMsg.isTemporary = false;
                lastMsg.id = payload.interrupt_id || lastMsg.id;
              }
            } else {
              messages.value.push({
                id: payload.interrupt_id || `ai-${++messageIdCounter}`,
                role: 'assistant',
                content: payload.text || '',
                timestamp: new Date().toISOString(),
                isTemporary: !payload.is_final,
              });
            }
            if (!payload.is_final) {
              isAiSpeaking.value = true;
            }
            break;
          }

          case 'pronunciation_feedback': {
            const payload = data.payload || {};
            const lastUserMsg = [...messages.value].reverse().find((m) => m.role === 'user');
            if (lastUserMsg) {
              lastUserMsg.pronunciation_score = payload.overall_score;
            }
            break;
          }

          case 'grammar_hint': {
            const payload = data.payload || {};
            const lastUserMsg = [...messages.value].reverse().find((m) => m.role === 'user');
            if (lastUserMsg) {
              if (!lastUserMsg.corrections) lastUserMsg.corrections = [];
              lastUserMsg.corrections.push({
                original: payload.original_text || '',
                corrected: payload.correction || '',
                explanation: payload.hint || '',
                correctedSentence: payload.corrected_sentence || '',
                severity: payload.severity || 'medium',
                type: payload.hint_type === 'expression' ? 'vocabulary' : 'grammar',
              });
            }
            break;
          }

          case 'session_ended': {
            connectionStatus.value.error = 'Session ended by server.';
            disconnect();
            break;
          }

          case 'error': {
            const payload = data.payload || {};
            connectionStatus.value = {
              connected: false,
              connecting: false,
              error: `[${payload.code}] ${payload.message}`,
            };
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
      connectionStatus.value = {
        connected: false,
        connecting: false,
        error: 'WebSocket connection error',
      };
    };

    ws.onclose = () => {
      connectionStatus.value = { connected: false, connecting: false, error: null };
      ws = null;
    };
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
    };
    messages.value.push(userMsg);

    ws.send(JSON.stringify({
      type: 'user_message',
      payload: {
        session_id: currentSessionId.value,
        text,
      },
    }));

    nextTick(() => {
      // Scroll handled by view component
    });
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
    if (!msg.audioUrl && msg.audioBlob) {
      msg.audioUrl = URL.createObjectURL(msg.audioBlob);
    }
    if (msg.audioUrl) {
      const audio = new Audio(msg.audioUrl);
      audio.play().catch(() => {});
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
    connect,
    disconnect,
    sendMessage,
    sendAudio,
    sendMessageWithAudio,
    playMessageAudio,
    speakText,
    stopSpeaking,
    pauseAudio,
    resumeAudio,
    togglePause,
    toggleTts,
    addTemporaryMessage,
    sendEndSession,
    clearMessages,
  };
});