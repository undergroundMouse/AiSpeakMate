import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { authApi, type AuthResponse } from '@/api/auth';

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('access_token'));
  const user = ref<{ user_id: string; username: string; email: string } | null>(
    null,
  );

  const isAuthenticated = computed(() => !!token.value);
  const username = computed(() => user.value?.username ?? '');

  // Hydrate from localStorage on init
  const storedToken = localStorage.getItem('access_token');
  const storedUser = localStorage.getItem('user');
  if (storedToken && storedUser) {
    try {
      token.value = storedToken;
      user.value = JSON.parse(storedUser);
    } catch {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
    }
  }

  async function login(email: string, password: string): Promise<AuthResponse> {
    const res = await authApi.login({ email, password });
    token.value = res.access_token;
    user.value = { user_id: res.user.id, username: res.user.username, email: res.user.email };
    localStorage.setItem('access_token', res.access_token);
    localStorage.setItem('user', JSON.stringify(user.value));
    return res;
  }

  async function register(
    username: string,
    email: string,
    password: string,
  ): Promise<AuthResponse> {
    const res = await authApi.register({ username, email, password });
    token.value = res.access_token;
    user.value = { user_id: res.user.id, username: res.user.username, email: res.user.email };
    localStorage.setItem('access_token', res.access_token);
    localStorage.setItem('user', JSON.stringify(user.value));
    return res;
  }

  function logout() {
    token.value = null;
    user.value = null;
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
  }

  return { token, user, isAuthenticated, username, login, register, logout };
});