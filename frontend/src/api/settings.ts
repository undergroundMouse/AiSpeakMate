import apiClient from './client';

export const API_CONFIG_CACHE_KEY = 'apiConfigCache';
const LEGACY_IFLYTEK_KEY = 'iflytekApiConfig';

export interface LlmSettings {
  provider: string;
  api_key: string;
  model: string;
}

export interface IflytekTtsSettings {
  app_id: string;
  api_key: string;
  api_secret: string;
}

export interface ApiConfigCache {
  llm?: LlmSettings;
  iflytek?: IflytekTtsSettings;
}

export interface ApisStatus {
  llm: { configured: boolean };
  iflytek_tts: { configured: boolean };
  iflytek_ise: { configured: boolean };
}

export const LLM_PROVIDERS = [
  { key: 'groq', label: 'Groq' },
  { key: 'deepseek', label: 'DeepSeek' },
  { key: 'glm', label: '智谱 GLM' },
  { key: 'moonshot', label: 'Moonshot' },
  { key: 'dashscope', label: '通义 DashScope' },
] as const;

export function loadApiConfigCache(): ApiConfigCache {
  try {
    const raw = localStorage.getItem(API_CONFIG_CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as ApiConfigCache & { speechsuper?: unknown };
      if ('speechsuper' in parsed) {
        delete parsed.speechsuper;
      }
      return parsed;
    }
  } catch {
    // fall through to legacy migration
  }

  try {
    const legacy = localStorage.getItem(LEGACY_IFLYTEK_KEY);
    if (legacy) {
      const saved = JSON.parse(legacy);
      const cache: ApiConfigCache = {
        iflytek: {
          app_id: saved.app_id || '',
          api_key: saved.api_key || '',
          api_secret: saved.api_secret || '',
        },
      };
      saveApiConfigCache(cache);
      localStorage.removeItem(LEGACY_IFLYTEK_KEY);
      return cache;
    }
  } catch {
    // ignore
  }

  return {};
}

export function saveApiConfigCache(cache: ApiConfigCache): void {
  localStorage.setItem(API_CONFIG_CACHE_KEY, JSON.stringify(cache));
}

export function updateApiConfigCache(partial: Partial<ApiConfigCache>): ApiConfigCache {
  const cache = { ...loadApiConfigCache(), ...partial };
  saveApiConfigCache(cache);
  return cache;
}

export const settingsApi = {
  async getApisStatus(): Promise<ApisStatus> {
    const res = await apiClient.get('/settings/apis');
    return res.data;
  },

  async saveLlm(data: LlmSettings): Promise<{ configured: boolean }> {
    const res = await apiClient.put('/settings/llm', data);
    return res.data;
  },

  async saveIflytekTts(data: IflytekTtsSettings): Promise<{ configured: boolean }> {
    const res = await apiClient.put('/settings/iflytek-tts', data);
    return res.data;
  },
};

export async function syncApiConfigFromCache(): Promise<void> {
  const token = localStorage.getItem('access_token');
  if (!token) return;

  const cache = loadApiConfigCache();

  if (cache.llm?.api_key) {
    await settingsApi.saveLlm(cache.llm);
  }
  if (cache.iflytek?.app_id && cache.iflytek?.api_key && cache.iflytek?.api_secret) {
    await settingsApi.saveIflytekTts(cache.iflytek);
  }
}
