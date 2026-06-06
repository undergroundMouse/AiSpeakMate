<template>
  <div class="home">
    <div class="hero">
      <h1>AiSpeakMate</h1>
      <p class="subtitle">AI 语言学习助手 — 随时随地练习口语</p>
    </div>

    <!-- Authenticated: welcome + navigation -->
    <div v-if="auth.isAuthenticated" class="dashboard">
      <p class="welcome">欢迎回来，{{ auth.username }}</p>
      <div class="dashboard-links">
        <router-link to="/scenes" class="btn btn-primary">开始练习</router-link>
        <router-link to="/progress" class="btn btn-secondary">我的进度</router-link>
      </div>
      <button class="btn-link" @click="auth.logout()">退出登录</button>
    </div>

    <!-- Not authenticated: login / register tabs -->
    <div v-else class="auth-card">
      <div class="tabs">
        <button :class="{ active: tab === 'login' }" @click="tab = 'login'">登录</button>
        <button :class="{ active: tab === 'register' }" @click="tab = 'register'">注册</button>
      </div>

      <!-- Login form -->
      <form v-if="tab === 'login'" @submit.prevent="doLogin" class="auth-form">
        <input v-model="loginForm.email" type="email" placeholder="邮箱" required />
        <input v-model="loginForm.password" type="password" placeholder="密码" required />
        <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
        <button type="submit" class="btn btn-primary" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>

      <!-- Register form -->
      <form v-else @submit.prevent="doRegister" class="auth-form">
        <input v-model="regForm.username" type="text" placeholder="用户名" required />
        <input v-model="regForm.email" type="email" placeholder="邮箱" required />
        <input v-model="regForm.password" type="password" placeholder="密码（至少6位）" required minlength="6" />
        <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
        <button type="submit" class="btn btn-primary" :disabled="loading">
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const router = useRouter();
const tab = ref<'login' | 'register'>('login');
const loading = ref(false);
const errorMsg = ref('');

const loginForm = reactive({ email: '', password: '' });
const regForm = reactive({ username: '', email: '', password: '' });

async function doLogin() {
  errorMsg.value = '';
  loading.value = true;
  try {
    await auth.login(loginForm.email, loginForm.password);
    router.push('/scenes');
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '登录失败，请检查邮箱和密码';
  } finally {
    loading.value = false;
  }
}

async function doRegister() {
  errorMsg.value = '';
  if (regForm.password.length < 6) {
    errorMsg.value = '密码至少6位';
    return;
  }
  loading.value = true;
  try {
    await auth.register(regForm.username, regForm.email, regForm.password);
    router.push('/scenes');
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '注册失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
}
.hero {
  text-align: center;
  margin-bottom: 32px;
}
.hero h1 {
  font-size: 2.5rem;
  color: var(--accent-primary);
}
.subtitle {
  color: var(--text-secondary);
  margin-top: 8px;
}

/* Dashboard */
.dashboard {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}
.welcome {
  font-size: 1.2rem;
}
.dashboard-links {
  display: flex;
  gap: 12px;
}

/* Auth card */
.auth-card {
  background: var(--bg-secondary);
  padding: 32px;
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  width: 100%;
  max-width: 400px;
}
.tabs {
  display: flex;
  margin-bottom: 24px;
  border-bottom: 2px solid var(--bg-card);
}
.tabs button {
  flex: 1;
  padding: 10px;
  background: none;
  color: var(--text-secondary);
  font-size: 1rem;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.2s;
}
.tabs button.active {
  color: var(--accent-primary);
  border-bottom-color: var(--accent-primary);
}
.auth-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.auth-form input {
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--bg-card);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 1rem;
}
.auth-form input:focus {
  border-color: var(--accent-primary);
  outline: none;
}
.error {
  color: var(--accent-danger);
  font-size: 0.9rem;
}

/* Buttons */
.btn {
  display: inline-block;
  padding: 12px 28px;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  text-align: center;
  transition: all 0.2s;
}
.btn-primary {
  background: var(--accent-primary);
  color: #0f172a;
}
.btn-primary:hover {
  opacity: 0.85;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-secondary {
  background: var(--bg-card);
  color: var(--text-primary);
}
.btn-secondary:hover {
  background: #475569;
}
.btn-link {
  background: none;
  color: var(--text-secondary);
  font-size: 0.9rem;
  text-decoration: underline;
}
</style>