<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-box api-config-modal">
      <h3>🔑 API 配置</h3>
      <p class="api-hint">配置第三方服务密钥，保存后立即生效。密钥保存在浏览器本地并同步到当前会话。</p>

      <!-- LLM -->
      <section class="api-section">
        <div class="section-head">
          <h4>LLM 对话</h4>
          <span class="badge" :class="status.llm ? 'ok' : 'pending'">
            {{ status.llm ? '已配置' : '未配置' }}
          </span>
        </div>
        <label class="field">
          <span>服务商</span>
          <select v-model="llmForm.provider">
            <option v-for="p in LLM_PROVIDERS" :key="p.key" :value="p.key">{{ p.label }}</option>
          </select>
        </label>
        <label class="field">
          <span>API Key</span>
          <input v-model="llmForm.api_key" type="password" placeholder="LLM API Key" autocomplete="off" />
        </label>
        <label class="field">
          <span>模型（可选）</span>
          <input v-model="llmForm.model" type="text" placeholder="留空使用默认模型" />
        </label>
        <div class="section-actions">
          <button type="button" class="btn-save" :disabled="saving.llm" @click="saveLlm">
            {{ saving.llm ? '保存中...' : '保存 LLM' }}
          </button>
          <span v-if="messages.llm" class="msg" :class="messageClass.llm">{{ messages.llm }}</span>
        </div>
      </section>

      <!-- iFlytek TTS -->
      <section class="api-section">
        <div class="section-head">
          <h4>讯飞开放平台（发音评测 ISE）</h4>
          <span class="badge" :class="status.iflytek_tts ? 'ok' : 'pending'">
            {{ status.iflytek_tts ? '已配置' : '未配置' }}
          </span>
        </div>
        <p class="section-note">AI 朗读已使用浏览器自带语音。此处密钥仅用于发音评测（ISE），需在讯飞控制台开通「语音评测（流式版）」。</p>
        <label class="field">
          <span>App ID</span>
          <input v-model="iflytekForm.app_id" type="text" placeholder="讯飞 App ID" />
        </label>
        <label class="field">
          <span>API Key</span>
          <input v-model="iflytekForm.api_key" type="password" placeholder="讯飞 API Key" autocomplete="off" />
        </label>
        <label class="field">
          <span>API Secret</span>
          <input v-model="iflytekForm.api_secret" type="password" placeholder="讯飞 API Secret" autocomplete="off" />
        </label>
        <div class="section-actions">
          <button type="button" class="btn-save" :disabled="saving.iflytek" @click="saveIflytek">
            {{ saving.iflytek ? '保存中...' : '保存讯飞配置' }}
          </button>
          <span v-if="messages.iflytek" class="msg" :class="messageClass.iflytek">{{ messages.iflytek }}</span>
        </div>
      </section>

      <div class="modal-actions">
        <button type="button" class="btn-cancel" @click="$emit('close')">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, onMounted } from 'vue';
import {
  LLM_PROVIDERS,
  loadApiConfigCache,
  updateApiConfigCache,
  settingsApi,
} from '@/api/settings';

defineEmits<{ close: [] }>();

const llmForm = reactive({ provider: 'deepseek', api_key: '', model: '' });
const iflytekForm = reactive({ app_id: '', api_key: '', api_secret: '' });

const status = reactive({ llm: false, iflytek_tts: false, iflytek_ise: false });
const saving = reactive({ llm: false, iflytek: false });
const messages = reactive({ llm: '', iflytek: '' });
const messageClass = reactive({ llm: '', iflytek: '' });

function loadFormsFromCache() {
  const cache = loadApiConfigCache();
  if (cache.llm) {
    llmForm.provider = cache.llm.provider || 'deepseek';
    llmForm.api_key = cache.llm.api_key || '';
    llmForm.model = cache.llm.model || '';
  }
  if (cache.iflytek) {
    iflytekForm.app_id = cache.iflytek.app_id || '';
    iflytekForm.api_key = cache.iflytek.api_key || '';
    iflytekForm.api_secret = cache.iflytek.api_secret || '';
  }
}

async function refreshStatus() {
  try {
    const res = await settingsApi.getApisStatus();
    status.llm = res.llm.configured;
    status.iflytek_tts = res.iflytek_tts.configured;
    status.iflytek_ise = res.iflytek_ise.configured;
  } catch {
    // ignore when not authenticated
  }
}

async function saveLlm() {
  if (!llmForm.api_key.trim()) {
    messages.llm = '请填写 API Key';
    messageClass.llm = 'error';
    return;
  }
  saving.llm = true;
  messages.llm = '';
  try {
    const payload = {
      provider: llmForm.provider,
      api_key: llmForm.api_key.trim(),
      model: llmForm.model.trim(),
    };
    const res = await settingsApi.saveLlm(payload);
    updateApiConfigCache({ llm: payload });
    status.llm = res.configured;
    messages.llm = res.configured ? '已保存' : '保存失败';
    messageClass.llm = res.configured ? 'ok' : 'error';
  } catch (e: any) {
    messages.llm = e?.response?.data?.detail || '保存失败';
    messageClass.llm = 'error';
  } finally {
    saving.llm = false;
  }
}

async function saveIflytek() {
  if (!iflytekForm.app_id.trim() || !iflytekForm.api_key.trim() || !iflytekForm.api_secret.trim()) {
    messages.iflytek = '请填写完整密钥';
    messageClass.iflytek = 'error';
    return;
  }
  saving.iflytek = true;
  messages.iflytek = '';
  try {
    const payload = {
      app_id: iflytekForm.app_id.trim(),
      api_key: iflytekForm.api_key.trim(),
      api_secret: iflytekForm.api_secret.trim(),
    };
    const res = await settingsApi.saveIflytekTts(payload);
    updateApiConfigCache({ iflytek: payload });
    status.iflytek_tts = res.configured;
    messages.iflytek = res.configured ? '已保存' : '保存失败';
    messageClass.iflytek = res.configured ? 'ok' : 'error';
  } catch (e: any) {
    messages.iflytek = e?.response?.data?.detail || '保存失败';
    messageClass.iflytek = 'error';
  } finally {
    saving.iflytek = false;
  }
}

onMounted(() => {
  loadFormsFromCache();
  refreshStatus();
});
</script>

<style scoped>
.api-config-modal {
  max-width: 480px;
  max-height: 90vh;
  overflow-y: auto;
}

.api-hint {
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin-bottom: 16px;
  line-height: 1.5;
}

.api-section {
  padding: 14px 0;
  border-top: 1px solid var(--bg-card);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-head h4 {
  font-size: 0.92rem;
  color: var(--text-primary);
}

.section-note {
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: -4px 0 12px;
}

.badge {
  font-size: 0.72rem;
  padding: 2px 8px;
  border-radius: 4px;
}

.badge.ok {
  background: rgba(22, 163, 74, 0.15);
  color: #16a34a;
}

.badge.pending {
  background: rgba(148, 163, 184, 0.15);
  color: var(--text-secondary);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}

.btn-save {
  padding: 7px 14px;
  border-radius: 6px;
  background: var(--accent-primary);
  color: #0f172a;
  font-weight: 600;
  font-size: 0.85rem;
}

.btn-save:disabled {
  opacity: 0.6;
}

.msg.ok {
  font-size: 0.8rem;
  color: var(--accent-success);
}

.msg.error {
  font-size: 0.8rem;
  color: var(--accent-danger);
}
</style>
