import apiClient from './client';

export interface SceneItem {
  id: string;
  title: string;
  description: string;
  icon: string | null;
  difficulty: string;
  category: string;
  duration_minutes: number;
  tags: string[];
  is_custom: boolean;
}

export interface SceneDetail extends SceneItem {
  prompt_template: string;
  suggested_phrases: string[];
  created_at: string;
}

export interface CustomSceneCreate {
  title: string;
  description?: string;
  prompt_template: string;
  icon?: string;
  difficulty?: string;
  category?: string;
  tags?: string[];
}

export interface SceneListParams {
  category?: string;
  difficulty?: string;
  search?: string;
  skip?: number;
  limit?: number;
}

export const sceneApi = {
  list(params?: SceneListParams) {
    return apiClient.get<SceneItem[]>('/scenes', { params }).then((res) => res.data);
  },

  getById(id: string) {
    return apiClient.get<SceneDetail>(`/scenes/${id}`).then((res) => res.data);
  },

  createCustom(data: CustomSceneCreate) {
    return apiClient.post<SceneItem>('/scenes/custom', data).then((res) => res.data);
  },

  deleteCustom(id: string) {
    return apiClient.delete(`/scenes/custom/${id}`).then((res) => res.data);
  },
};