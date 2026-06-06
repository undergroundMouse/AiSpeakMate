import apiClient from './client';

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  username: string;
  email: string;
}

export const authApi = {
  register(data: RegisterRequest): Promise<AuthResponse> {
    return apiClient.post('/auth/register', data).then((res) => res.data);
  },

  login(data: LoginRequest): Promise<AuthResponse> {
    return apiClient.post('/auth/login', data).then((res) => res.data);
  },

  me() {
    return apiClient.get('/auth/me').then((res) => res.data);
  },
};