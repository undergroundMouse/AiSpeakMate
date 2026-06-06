<template>
  <div class="chat-view">
    <!-- Connection status bar -->
    <header class="chat-header">
      <router-link to="/scenes" class="back-link">&larr; 场景列表</router-link>
      <div class="connection-badge" :class="statusClass">
        <span class="dot"></span>
        {{ statusText }}
      </div>
      <button v-if="chatStore.connectionStatus.connected" class="btn-end" @click="endSession">
        结束对话
      </button>
    </header>

    <!-- Messages area -->
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

    <!-- Input area -->
    <div class="input-area">
      <textarea
        v-model="inputText"
        class="msg-input"
        placeholder="输入你的回答..."
        rows="2"
        :disabled="!chatStore.connectionStatus.connected"
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

async function endSession() {
  chatStore.disconnect();
  const sessionId = route.params.sessionId as string;
  router.push(`/summary/${sessionId}`);
}

onMounted(() => {
  if (!auth.isAuthenticated || !auth.token) {
    router.push('/');
    return;
  }
  const sessionId = route.params.sessionId as string;
  chatStore.connect(sessionId, auth.token, { sceneId: chatStore.sceneId ?? undefined });
});

onUnmounted(() => {
  // Don't disconnect on unmount if user is navigating to summary
  // chatStore.disconnect();
});
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 800px;
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
</style>