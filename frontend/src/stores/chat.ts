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
    type: 'grammar' | 'pronunciation' | 'vocabulary';
  }>;
  pronunciation_score?: number;
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
  const currentSessionId = ref<string | null>(null);

  let ws: WebSocket | null = null;
  let messageIdCounter = 0;

  function connect(sessionId: string, token: string) {
    if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    currentSessionId.value = sessionId;
    connectionStatus.value = { connected: false, connecting: true, error: null };

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//localhost:8000/api/v1/ws/chat/${sessionId}?token=${token}`;

    ws = new WebSocket(url);

    ws.onopen = () => {
      connectionStatus.value = { connected: true, connecting: false, error: null };
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'assistant_message') {
          // Append or update assistant message
          const lastMsg = messages.value[messages.value.length - 1];
          if (lastMsg && lastMsg.role === 'assistant' && lastMsg.isTemporary) {
            lastMsg.content += data.content;
            lastMsg.isTemporary = data.is_partial ?? true;
            if (!data.is_partial) {
              lastMsg.id = data.message_id || lastMsg.id;
              lastMsg.timestamp = data.timestamp || lastMsg.timestamp;
              lastMsg.corrections = data.corrections;
              lastMsg.pronunciation_score = data.pronunciation_score;
            }
          } else {
            messages.value.push({
              id: data.message_id || `ai-${++messageIdCounter}`,
              role: 'assistant',
              content: data.content,
              timestamp: data.timestamp || new Date().toISOString(),
              isTemporary: data.is_partial ?? true,
              corrections: data.corrections,
              pronunciation_score: data.pronunciation_score,
            });
          }
          isAiSpeaking.value = data.is_partial ?? true;
        } else if (data.type === 'evaluation') {
          // Attach evaluation to last user message
          const lastUserMsg = [...messages.value].reverse().find((m) => m.role === 'user');
          if (lastUserMsg) {
            lastUserMsg.corrections = data.corrections;
            lastUserMsg.pronunciation_score = data.pronunciation_score;
          }
        } else if (data.type === 'session_ended') {
          connectionStatus.value.error = 'Session ended by server.';
          disconnect();
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

    const userMsg: ChatMessage = {
      id: `user-${++messageIdCounter}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };
    messages.value.push(userMsg);

    ws.send(JSON.stringify({ type: 'user_message', content: text }));

    nextTick(() => {
      // Scroll handled by view component
    });
  }

  function sendAudio(audioBlob: Blob) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectionStatus.value.error = 'Not connected to chat server';
      return;
    }
    // Send audio as binary
    ws.send(audioBlob);
  }

  function clearMessages() {
    messages.value = [];
  }

  return {
    messages,
    connectionStatus,
    isRecording,
    isAiSpeaking,
    currentSessionId,
    connect,
    disconnect,
    sendMessage,
    sendAudio,
    clearMessages,
  };
});