import apiClient from './client';

export interface SessionCreate {
  scene_id: number;
  custom_scene_id?: string;
}

export interface SessionItem {
  session_id: string;
  scene_id: number | null;
  custom_scene_id: string | null;
  difficulty: string;
  status: string;
  started_at: string;
  ended_at?: string | null;
  scene_name?: string | null;
  utterance_count?: number;
  duration_seconds?: number;
}

export interface SessionListParams {
  status?: string;
  skip?: number;
  limit?: number;
}

export interface SessionListResponse {
  total: number;
  sessions: SessionItem[];
}

export const sessionApi = {
  create(data: SessionCreate) {
    return apiClient.post<SessionItem>('/sessions/start', data).then((res) => res.data);
  },

  list(params?: SessionListParams) {
    return apiClient.get<SessionListResponse>('/sessions', { params }).then((res) => res.data);
  },

  getById(id: string) {
    return apiClient.get<SessionItem>(`/sessions/${id}`).then((res) => res.data);
  },

  end(id: string) {
    return apiClient.post(`/sessions/${id}/end`).then((res) => res.data);
  },

  getMessages(id: string) {
    return apiClient.get(`/sessions/${id}/messages`).then((res) => res.data);
  },
};