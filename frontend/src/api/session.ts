import apiClient from './client';

export type SessionMode = 'immersive' | 'practice';

export interface SessionCreate {
  scene_id: number;
  custom_scene_id?: string;
  difficulty?: string;
  mode?: SessionMode;
}

export interface SessionStartResponse {
  session_id: string;
  scene_id: number | null;
  custom_scene_id?: string | null;
  difficulty: string;
  mode: SessionMode;
  status: string;
  started_at: string;
}

export interface SessionItem {
  session_id: string;
  scene_id: number | null;
  scene_name: string | null;
  date: string;
  duration_seconds: number;
  total_score: number;
}

export interface SessionListParams {
  status?: string;
  scene_id?: number;
  page?: number;
  page_size?: number;
}

export interface SessionListResponse {
  data: SessionItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface UtteranceItem {
  utterance_id: string;
  speaker: string;
  text: string;
  sequence: number;
}

export interface EndSessionResponse {
  session_id: string;
  status: string;
  duration_seconds: number;
}

export const sessionApi = {
  create(data: SessionCreate) {
    return apiClient.post<SessionStartResponse>('/sessions/start', data).then((res) => res.data);
  },

  list(params?: SessionListParams) {
    return apiClient.get<SessionListResponse>('/sessions', { params }).then((res) => res.data);
  },

  /** V1.1: List sessions for a specific user with page-based pagination */
  listByUser(userId: string, params?: SessionListParams) {
    return apiClient
      .get<SessionListResponse>(`/users/${userId}/sessions`, { params })
      .then((res) => res.data);
  },

  getById(id: string) {
    return apiClient.get<SessionItem>(`/sessions/${id}`).then((res) => res.data);
  },

  end(id: string) {
    return apiClient.post<EndSessionResponse>(`/sessions/${id}/end`).then((res) => res.data);
  },

  getMessages(id: string) {
    return apiClient.get<UtteranceItem[]>(`/sessions/${id}/messages`).then((res) => res.data);
  },

  /** V1.1: Delete audio data for a session (privacy compliance) */
  deleteAudio(id: string) {
    return apiClient.delete(`/sessions/${id}/audio`).then((res) => res.data);
  },
};
