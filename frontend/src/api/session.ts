import apiClient from './client';

export interface SessionCreate {
  scene_id: string;
}

export interface SessionItem {
  id: string;
  scene_id: string;
  scene_title: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  message_count: number;
  duration_seconds: number;
}

export interface SessionListParams {
  status?: string;
  skip?: number;
  limit?: number;
}

export const sessionApi = {
  create(data: SessionCreate) {
    return apiClient.post<SessionItem>('/sessions', data).then((res) => res.data);
  },

  list(params?: SessionListParams) {
    return apiClient.get<SessionItem[]>('/sessions', { params }).then((res) => res.data);
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