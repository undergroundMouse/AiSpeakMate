<template>
  <div class="chat-view">
    <!-- Connection status bar -->
    <header class="chat-header">
      <router-link to="/scenes" class="back-link">&larr; 场景列表</router-link>
      <div class="connection-badge" :class="statusClass">
        <span class="dot"></span>
        {{ statusText }}
      </div>
      <button
        class="btn-scene-info"
        :class="{ active: showSceneInfo }"
        @click="showSceneInfo = !showSceneInfo"
        title="场景信息"
      >📋</button>
      <button v-if="chatStore.connectionStatus.connected" class="btn-end" @click="endSession">
        结束对话
      </button>
    </header>

    <!-- Messages area -->
    <div class="chat-body" :class="{ 'with-panel': showSceneInfo }">
      <!-- Scene info panel -->
      <div v-if="showSceneInfo && sceneDetail" class="scene-panel">
        <h3>{{ sceneDetail.name }}</h3>
        <div class="panel-section" v-if="sceneDetail.vocab_list?.length">
          <h4>核心词汇</h4>
          <div class="panel-vocab">
            <a v-for="v in sceneDetail.vocab_list" :key="v.word" class="panel-word"
              :href="'https://www.baidu.com/s?wd=' + encodeURIComponent(v.word + ' 英语')"
              target="_blank" rel="noopener"
              :title="'百度搜索: ' + v.word">
              {{ v.word }}<small v-if="v.translation"> ({{ v.translation }})</small>
            </a>
          </div>
        </div>
        <div class="panel-section" v-if="sceneDetail.sentence_patterns?.length">
          <h4>常用句式</h4>
          <div class="panel-patterns">
            <p v-for="(p, i) in sceneDetail.sentence_patterns" :key="i" class="panel-pattern">
              {{ p.pattern }}<br>
              <small v-if="p.translation">{{ p.translation }}</small>
            </p>
          </div>
        </div>
      </div>

      <div ref="messagesContainer" class="messages-area">
      <div v-if="chatStore.messages.length === 0" class="empty-hint">
        <p>开始和 AI 对话练习吧！</p>
        <p class="sub">输入你的第一句话，AI 会扮演场景中的角色与你互动</p>
      </div>

      <div
        v-for="msg in chatStore.messages"
        :key="msg.id"
        class="message-row"
        :class="msg.role"
      >
        <div class="bubble">
          <div class="role-label">{{ msg.role === 'user' ? '你' : 'AI' }}</div>
          <div class="content">{{ msg.content }}</div>

          <!-- Action buttons row -->
          <div class="msg-actions">
            <!-- Speaker button: replay AI TTS (always works regardless of header TTS toggle) -->
            <button
              v-if="msg.role === 'assistant' && !msg.isTemporary"
              class="btn-speaker"
              :title="'播放AI语音'"
              @click="replayTts(msg.content)"
            >🔊</button>
            <!-- Speaker button: play user recording -->
            <button
              v-if="msg.role === 'user' && (msg.audioUrl || msg.audioBlob) && !msg.isTemporary"
              class="btn-speaker"
              :title="'播放我的录音'"
              @click="chatStore.playMessageAudio(msg)"
            >🔊</button>
            <!-- Pause/Resume AI speech -->
            <button
              v-if="msg.role === 'assistant' && !msg.isTemporary"
              class="btn-speaker"
              :title="isPaused ? '继续播放' : '暂停播放'"
              @click="togglePause()"
            >{{ isPaused ? '▶' : '⏸' }}</button>
            <!-- Translate button for AI and user messages -->
            <button
              v-if="!msg.isTemporary"
              class="btn-speaker btn-translate"
              :class="{ active: translations[msg.id] }"
              :disabled="translatingId === msg.id"
              @click="toggleTranslate(msg.id, msg.content)"
              :title="translations[msg.id] ? '隐藏翻译' : '翻译成中文'"
            >
              {{ translatingId === msg.id ? '...' : (translations[msg.id] ? '隐藏' : '译') }}
            </button>
          </div>
          <!-- Translation result -->
          <div v-if="translations[msg.id]" class="translation">
            {{ translations[msg.id] }}
          </div>

          <!-- Corrections for user messages -->
          <div v-if="msg.role === 'user' && msg.corrections?.length" class="corrections">
            <div class="correction-title">修改建议</div>
            <div v-for="(corr, ci) in msg.corrections" :key="ci" class="correction-item">
              <span class="corr-type" :class="corr.type">
                {{ CORRECTION_LABELS[corr.type] || corr.type }}
              </span>
              <span class="corr-original">{{ corr.original }}</span>
              &rarr;
              <span class="corr-corrected">{{ corr.corrected }}</span>
              <p class="corr-explanation">{{ corr.explanation }}</p>
            </div>
          </div>

          <!-- Pronunciation score -->
          <div v-if="msg.role === 'user' && msg.pronunciation_score != null" class="pron-score">
            发音评分：{{ msg.pronunciation_score }}/100
          </div>

          <div v-if="msg.isTemporary" class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    </div>

    </div><!-- end chat-body -->

    <!-- Input area -->
    <div class="input-area">
      <button
        class="btn-mic"
        :class="{ recording: isRecording }"
        :disabled="!chatStore.connectionStatus.connected"
        @click="toggleRecording"
        :title="isRecording ? '停止录音' : '开始录音'"
      >
        <span class="mic-icon">{{ isRecording ? '⏹' : '🎤' }}</span>
      </button>
      <textarea
        v-model="inputText"
        class="msg-input"
        placeholder="输入你的回答..."
        rows="2"
        :disabled="!chatStore.connectionStatus.connected || isRecording"
        @keydown.enter.exact.prevent="sendText"
      ></textarea>
      <button
        class="btn-send"
        :disabled="!inputText.trim() || !chatStore.connectionStatus.connected"
        @click="sendText"
      >
        发送
      </button>
    </div>

    <!-- Recording indicator overlay -->
    <div v-if="isRecording" class="recording-overlay">
      <div class="recording-pulse"></div>
      <span class="recording-text">正在持续录音... 再次点击停止并发送</span>
      <span class="recording-duration">{{ recordingDuration }}s</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useChatStore } from '@/stores/chat';
import { useAuthStore } from '@/stores/auth';
import { useSceneStore } from '@/stores/scene';

const CORRECTION_LABELS: Record<string, string> = {
  grammar: '语法',
  pronunciation: '发音',
  vocabulary: '词汇',
};

const route = useRoute();
const router = useRouter();
const chatStore = useChatStore();
const auth = useAuthStore();
const sceneStore = useSceneStore();

const inputText = ref('');
const messagesContainer = ref<HTMLElement | null>(null);
const showSceneInfo = ref(false);
const sceneDetail = ref<any>(null);
const isPaused = ref(false);

function togglePause() {
  if (isPaused.value) {
    window.speechSynthesis.resume();
    isPaused.value = false;
  } else {
    window.speechSynthesis.pause();
    isPaused.value = true;
  }
}
import { sceneApi } from '@/api/scene';

// Translation state
const translations = ref<Record<string, string>>({});
const translatingId = ref<string | null>(null);
import apiClient from '@/api/client';

function replayTts(text: string) {
  // Always speak regardless of header TTS toggle
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-US';
  utterance.rate = 0.9;
  window.speechSynthesis.speak(utterance);
}

async function toggleTranslate(msgId: string, text: string) {
  // If already translated, toggle off
  if (translations.value[msgId]) {
    delete translations.value[msgId];
    return;
  }
  // Fetch translation
  translatingId.value = msgId;
  try {
    const res = await apiClient.post('/translate', {
      text,
      source_lang: 'en',
      target_lang: 'zh-CN',
    });
    translations.value[msgId] = res.data.translated;
  } catch {
    translations.value[msgId] = '[翻译失败]';
  } finally {
    translatingId.value = null;
  }
}

const statusClass = computed(() => {
  const s = chatStore.connectionStatus;
  if (s.connected) return 'connected';
  if (s.connecting) return 'connecting';
  if (s.error) return 'error';
  return 'disconnected';
});

const statusText = computed(() => {
  const s = chatStore.connectionStatus;
  if (s.connected) return '已连接';
  if (s.connecting) return '连接中...';
  if (s.error) return s.error;
  return '未连接';
});

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
    }
  });
}

watch(
  () => chatStore.messages.length,
  () => scrollToBottom(),
);

function sendText() {
  const text = inputText.value.trim();
  if (!text) return;
  chatStore.sendMessage(text);
  inputText.value = '';
}

// --- Speech Recognition + Audio Capture (browser built-in) ---
const isRecording = ref(false);
const recordingDuration = ref(0);
let recognition: any = null;
let audioRecorder: MediaRecorder | null = null;
let audioChunks: BlobPart[] = [];
let audioStream: MediaStream | null = null;
let recordingTimer: ReturnType<typeof setInterval> | null = null;

const SpeechRecognitionAPI =
  (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

async function toggleRecording() {
  if (isRecording.value) {
    stopRecording();
  } else {
    await startRecording();
  }
}

async function startRecording() {
  // Start audio capture (for playback) in all cases
  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioRecorder = new MediaRecorder(audioStream, { mimeType: 'audio/webm' });
    audioChunks = [];
    audioRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };
    audioRecorder.start(250);
  } catch (err) {
    console.error('Audio capture failed:', err);
  }

  // Accumulated transcripts for continuous mode
  const continuousTranscripts: string[] = [];

  if (SpeechRecognitionAPI) {
    try {
      recognition = new SpeechRecognitionAPI();
      recognition.lang = 'en-US';
      recognition.interimResults = true;
      recognition.continuous = true;
      recognition.maxAlternatives = 1;

      recognition.onresult = (event: any) => {
        // Collect all results since last start
        let transcript = '';
        for (let i = 0; i < event.results.length; i++) {
          if (event.results[i].isFinal) {
            transcript += event.results[i][0].transcript + ' ';
          }
        }
        if (transcript.trim()) {
          continuousTranscripts.push(transcript.trim());
        }
      };

      recognition.onerror = (event: any) => {
        console.error('Speech recognition error:', event.error);
      };

      recognition.onend = () => {
        // In continuous mode, onend fires after each utterance and auto-restarts.
        // Only send text when user manually stopped (isRecording already set to false).
        if (!isRecording.value) {
          const fullText = continuousTranscripts.join(' ').trim();
          if (fullText) {
            stopAudioRecorder();
            const audioBlob = audioChunks.length > 0
              ? new Blob(audioChunks, { type: 'audio/webm' })
              : null;
            if (audioBlob) {
              chatStore.sendMessageWithAudio(fullText, audioBlob);
            } else {
              chatStore.sendMessage(fullText);
            }
          }
          continuousTranscripts.length = 0;
          stopAudioRecorder();
          resetRecordingState();
        }
        // If isRecording is still true, recognition will auto-restart
      };

      recognition.start();
      isRecording.value = true;
      continuousTranscripts.length = 0;
      recordingDuration.value = 0;
      recordingTimer = setInterval(() => { recordingDuration.value++; }, 1000);
    } catch (err) {
      console.error('Speech recognition start failed:', err);
      stopAudioRecorder();
      isRecording.value = false;
    }
  } else {
    // Fallback: audio-only recording
    isRecording.value = true;
    recordingDuration.value = 0;
    recordingTimer = setInterval(() => { recordingDuration.value++; }, 1000);
  }
}

function stopAudioRecorder() {
  if (audioRecorder && audioRecorder.state === 'recording') {
    audioRecorder.stop();
  }
  if (audioStream) {
    audioStream.getTracks().forEach(t => t.stop());
    audioStream = null;
  }
}

function resetRecordingState() {
  isRecording.value = false;
  recordingDuration.value = 0;
  if (recordingTimer) {
    clearInterval(recordingTimer);
    recordingTimer = null;
  }
}

function stopRecording() {
  // Set recording flag false BEFORE stopping recognition
  // so onend handler knows this is a manual stop (not auto-restart)
  isRecording.value = false;
  if (recognition) {
    recognition.stop();
    recognition = null;
  }
  // For fallback mode: stop recorder, send audio
  if (!SpeechRecognitionAPI && audioRecorder && audioRecorder.state === 'recording') {
    audioRecorder.onstop = () => {
      if (audioChunks.length > 0) {
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        chatStore.sendAudio(blob);
      }
      resetRecordingState();
    };
    stopAudioRecorder();
  }
}

async function endSession() {
  const sessionId = route.params.sessionId as string;
  // Send end_session message to server before disconnecting
  if (chatStore.currentSessionId) {
    chatStore.sendEndSession();
  }
  // Navigate to summary — the server will mark session complete
  router.push(`/summary/${sessionId}`);
}

onMounted(() => {
  if (!auth.isAuthenticated || !auth.token) {
    router.push('/');
    return;
  }
  const sessionId = route.params.sessionId as string;
  chatStore.connect(sessionId, auth.token, { sceneId: chatStore.sceneId ?? undefined });
  // Load scene detail for the info panel
  if (chatStore.sceneId) {
    sceneApi.getById(chatStore.sceneId).then(s => { sceneDetail.value = s; }).catch(() => {});
  }
});

onUnmounted(() => {
  // Stop speech recognition or recording if active
  stopRecording();
  // Don't disconnect on unmount if user is navigating to summary
  // chatStore.disconnect();
});
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 1100px;
  margin: 0 auto;
  background: var(--bg-primary);
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--bg-card);
  flex-shrink: 0;
}
.back-link {
  color: var(--text-secondary);
  font-size: 0.9rem;
}
.connection-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  padding: 4px 10px;
  border-radius: 20px;
  background: var(--bg-card);
  margin-left: auto;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.connected .dot { background: var(--accent-success); }
.connecting .dot { background: var(--accent-warning); animation: pulse 0.8s infinite; }
.error .dot { background: var(--accent-danger); }
.disconnected .dot { background: var(--text-secondary); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.btn-scene-info {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--bg-card);
  font-size: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.btn-scene-info:hover { background: var(--accent-warning); }
.btn-scene-info.active { background: var(--accent-warning); color: #0f172a; }

.chat-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.chat-body.with-panel .messages-area {
  flex: 1;
}
.scene-panel {
  width: 260px;
  flex-shrink: 0;
  overflow-y: auto;
  padding: 16px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--bg-card);
}
.scene-panel h3 {
  font-size: 1rem;
  color: var(--accent-primary);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--bg-card);
}
.panel-section { margin-bottom: 14px; }
.panel-section h4 {
  font-size: 0.8rem;
  color: var(--accent-warning);
  margin-bottom: 6px;
}
.panel-vocab {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.panel-word {
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-card);
  font-size: 0.78rem;
  color: var(--text-primary);
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s;
}
.panel-word:hover {
  background: var(--accent-primary);
  color: #0f172a;
}
.panel-word small {
  color: var(--text-secondary);
  font-size: 0.7rem;
}
.panel-pattern {
  font-size: 0.78rem;
  color: var(--text-primary);
  margin-bottom: 6px;
  line-height: 1.4;
}
.panel-pattern small {
  color: var(--text-secondary);
}

.btn-end {
  padding: 6px 14px;
  border-radius: 6px;
  background: var(--accent-danger);
  color: #fff;
  font-size: 0.85rem;
  font-weight: 600;
}
.btn-end:hover { opacity: 0.85; }

/* Messages */
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.empty-hint {
  text-align: center;
  color: var(--text-secondary);
  margin-top: 80px;
}
.empty-hint p { margin-bottom: 8px; }
.empty-hint .sub { font-size: 0.85rem; }

.message-row {
  display: flex;
}
.message-row.user {
  justify-content: flex-end;
}
.message-row.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 75%;
  padding: 12px 18px;
  border-radius: 16px;
  position: relative;
}
.message-row.user .bubble {
  background: var(--accent-primary);
  color: #0f172a;
  border-bottom-right-radius: 4px;
}
.message-row.assistant .bubble {
  background: var(--bg-secondary);
  border-bottom-left-radius: 4px;
}
.role-label {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  margin-bottom: 4px;
  opacity: 0.7;
}
.content {
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Message action buttons */
.msg-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.btn-speaker {
  width: 28px;
  height: 24px;
  padding: 0;
  border-radius: 4px;
  background: rgba(255,255,255,0.1);
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
.btn-speaker:hover {
  background: var(--accent-success);
  color: #0f172a;
}
.message-row.user .btn-speaker {
  background: rgba(0,0,0,0.15);
  color: rgba(0,0,0,0.6);
}
.message-row.user .btn-speaker:hover {
  background: rgba(0,0,0,0.3);
  color: #000;
}

/* Translate button — shares btn-speaker base sizing */
.btn-translate {
  width: 28px;
  height: 24px;
  padding: 0;
  border-radius: 4px;
  background: rgba(255,255,255,0.1);
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
.btn-translate:hover:not(:disabled) {
  background: var(--accent-primary);
  color: #0f172a;
}
.btn-translate.active {
  background: rgba(56,189,248,0.2);
  color: var(--accent-primary);
}
.btn-translate:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.translation {
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(56,189,248,0.08);
  border-left: 2px solid var(--accent-primary);
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* Corrections */
.corrections {
  margin-top: 10px;
  padding: 10px;
  background: rgba(0,0,0,0.15);
  border-radius: 8px;
  font-size: 0.82rem;
}
.correction-title {
  font-weight: 700;
  margin-bottom: 6px;
  color: var(--accent-warning);
}
.correction-item {
  padding: 6px 0;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.correction-item:last-child { border-bottom: none; }
.corr-type {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 700;
  margin-right: 6px;
  background: rgba(0,0,0,0.2);
}
.corr-type.grammar { color: var(--accent-warning); }
.corr-type.pronunciation { color: var(--accent-primary); }
.corr-type.vocabulary { color: var(--accent-success); }
.corr-original {
  text-decoration: line-through;
  opacity: 0.7;
}
.corr-corrected {
  color: var(--accent-success);
  font-weight: 600;
}
.corr-explanation {
  font-size: 0.75rem;
  opacity: 0.65;
  margin-top: 2px;
}

.pron-score {
  margin-top: 8px;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--accent-success);
}

/* Typing indicator */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 6px 0 0;
}
.typing-indicator span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-secondary);
  animation: bounce 1.2s infinite;
}
.typing-indicator span:nth-child(2) { animation-delay: 0.15s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.3s; }

@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

/* Input */
.input-area {
  display: flex;
  gap: 10px;
  padding: 14px 20px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--bg-card);
  flex-shrink: 0;
}
.msg-input {
  flex: 1;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid var(--bg-card);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 0.95rem;
  resize: none;
  font-family: inherit;
}
.msg-input:focus {
  border-color: var(--accent-primary);
  outline: none;
}
.msg-input:disabled {
  opacity: 0.5;
}
.btn-send {
  padding: 0 24px;
  border-radius: 10px;
  background: var(--accent-primary);
  color: #0f172a;
  font-weight: 700;
  font-size: 1rem;
  white-space: nowrap;
}
.btn-send:hover { opacity: 0.85; }
.btn-send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Microphone button */
.btn-mic {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: var(--bg-card);
  border: 2px solid var(--bg-card);
  font-size: 1.2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}
.btn-mic:hover:not(:disabled) { background: var(--bg-primary); border-color: var(--accent-primary); }
.btn-mic.recording {
  background: var(--accent-danger);
  border-color: var(--accent-danger);
  animation: mic-pulse 1.2s infinite;
}
.btn-mic:disabled { opacity: 0.4; cursor: not-allowed; }
@keyframes mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.5); }
  50% { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
}

/* Recording overlay */
.recording-overlay {
  position: fixed;
  bottom: 100px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  background: var(--accent-danger);
  color: #fff;
  border-radius: 30px;
  font-weight: 600;
  font-size: 0.9rem;
  box-shadow: 0 4px 20px rgba(239, 68, 68, 0.3);
  z-index: 100;
}
.recording-pulse {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #fff;
  animation: pulse 0.8s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.3); }
}
.recording-duration {
  font-size: 0.85rem;
  opacity: 0.85;
}
</style>
