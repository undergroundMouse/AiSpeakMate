import apiClient from './client';

export interface SceneBrief {
  scene_id: number;
  name: string;
  description: string;
  thumbnail_url: string | null;
  difficulty_levels: string[];
  tags: string[];
}

export interface CategoryWithScenes {
  category_id: number;
  category_name: string;
  icon_url: string | null;
  scenes: SceneBrief[];
}

export interface SceneListResponse {
  categories: CategoryWithScenes[];
}

export interface VocabItem {
  word: string;
  phonetic: string | null;
  audio_url: string | null;
  translation: string | null;
}

export interface SentencePatternItem {
  pattern: string;
  translation: string | null;
  example: string | null;
}

export interface SceneDetail {
  scene_id: number;
  name: string;
  role_prompt: string;
  opening_line: string;
  vocab_list: VocabItem[];
  sentence_patterns: SentencePatternItem[];
  difficulty_settings: Record<string, any> | null;
  suggested_duration_minutes: number | null;
}

export interface CustomSceneRequest {
  topic: string;
  role?: string;
  difficulty: string;
  focus_grammar?: string[];
  focus_vocab?: string[];
}

export interface CustomSceneResponse {
  custom_scene_id: string;
  topic: string;
  role_prompt: string;
  opening_line: string;
}

export const sceneApi = {
  list() {
    return apiClient.get<SceneListResponse>('/scenes').then((res) => res.data);
  },

  getById(id: number) {
    return apiClient.get<SceneDetail>(`/scenes/${id}`).then((res) => res.data);
  },

  getRandom(difficulty?: string) {
    return apiClient
      .get<SceneDetail>('/scenes/random', { params: difficulty ? { difficulty } : {} })
      .then((res) => res.data);
  },

  createCustom(data: CustomSceneRequest) {
    return apiClient.post<CustomSceneResponse>('/scenes/custom', data, { timeout: 45000 }).then((res) => res.data);
  },
};
