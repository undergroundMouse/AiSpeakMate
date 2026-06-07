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
  const sceneId = ref<number | null>(null);

  let ws: WebSocket | null = null;
  let messageIdCounter = 0;
  let currentInterruptId: string | null = null;

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
          case 'session_started': {
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
            isAiSpeaking.value = !payload.is_final;
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
                type: 'grammar',
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
    sceneId,
    connect,
    disconnect,
    sendMessage,
    sendAudio,
    clearMessages,
  };
});