<template>
  <div id="app-root" :class="themeClass">
    <!-- Navbar -->
    <nav class="navbar">
      <router-link to="/" class="navbar-brand">🎓 AiSpeakMate</router-link>
      <div class="navbar-right">
        <!-- Settings button -->
        <button class="btn-sm btn-outline-sm" @click="showSettings = true" title="设置">⚙️</button>

        <!-- Authenticated: user badge + logout -->
        <template v-if="auth.isAuthenticated">
          <div class="user-badge">
            <div class="user-avatar">{{ auth.username.charAt(0).toUpperCase() }}</div>
            <span>{{ auth.username }}</span>
          </div>
          <router-link to="/progress" class="btn-sm btn-outline-sm">📊 进度</router-link>
          <button class="btn-sm btn-outline-sm" @click="auth.logout()">退出</button>
        </template>

        <!-- Not authenticated: login button -->
        <template v-else>
          <button class="btn-sm btn-primary-sm" @click="showAuth = true">登录 / 注册</button>
        </template>
      </div>
    </nav>

    <!-- Main content -->
    <router-view :key="$route.fullPath" />

    <!-- Login/Register Modal -->
    <div v-if="showAuth" class="modal-overlay" @click.self="showAuth = false">
      <div class="modal-box">
        <div style="display:flex;gap:0;margin-bottom:16px;border-bottom:2px solid var(--bg-card)">
          <button @click="authTab='login'" :style="{flex:1,padding:'8px',background:'none',color:authTab==='login'?'var(--accent-primary)':'var(--text-secondary)',borderBottom:authTab==='login'?'2px solid var(--accent-primary)':'2px solid transparent',marginBottom:'-2px',fontSize:'0.95rem'}">登录</button>
          <button @click="authTab='register'" :style="{flex:1,padding:'8px',background:'none',color:authTab==='register'?'var(--accent-primary)':'var(--text-secondary)',borderBottom:authTab==='register'?'2px solid var(--accent-primary)':'2px solid transparent',marginBottom:'-2px',fontSize:'0.95rem'}">注册</button>
        </div>

        <form v-if="authTab==='login'" @submit.prevent="doLogin">
          <input v-model="loginForm.email" type="email" placeholder="邮箱" required />
          <input v-model="loginForm.password" type="password" placeholder="密码" required />
          <p v-if="authError" style="color:var(--accent-danger);font-size:0.82rem;margin-bottom:8px">{{ authError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn-cancel" @click="showAuth=false">取消</button>
            <button type="submit" class="btn-confirm" :disabled="authLoading">{{ authLoading?'登录中...':'登录' }}</button>
          </div>
        </form>

        <form v-else @submit.prevent="doRegister">
          <input v-model="regForm.username" type="text" placeholder="用户名" required />
          <input v-model="regForm.email" type="email" placeholder="邮箱" required />
          <input v-model="regForm.password" type="password" placeholder="密码（至少6位）" required minlength="6" />
          <p v-if="authError" style="color:var(--accent-danger);font-size:0.82rem;margin-bottom:8px">{{ authError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn-cancel" @click="showAuth=false">取消</button>
            <button type="submit" class="btn-confirm" :disabled="authLoading">{{ authLoading?'注册中...':'注册' }}</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Settings Modal -->
    <div v-if="showSettings" class="modal-overlay" @click.self="showSettings = false">
      <div class="modal-box" style="max-width:440px">
        <h3>⚙️ 设置</h3>

        <!-- Theme -->
        <h4 style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:8px">主题颜色</h4>
        <div class="theme-presets">
          <div v-for="t in themes" :key="t.key" class="theme-dot" :class="[t.key, { active: currentTheme === t.key }]" :title="t.label" @click="setTheme(t.key)"></div>
        </div>

        <!-- Custom theme -->
        <h4 style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:8px;margin-top:14px">自定义主题</h4>
        <div class="color-row">
          <label>背景色</label>
          <input type="color" v-model="customBg" @change="applyCustomTheme" />
        </div>
        <div class="color-row">
          <label>强调色</label>
          <input type="color" v-model="customAccent" @change="applyCustomTheme" />
        </div>

        <!-- TTS Voice -->
        <h4 style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:8px;margin-top:16px">AI 语音</h4>
        <div v-for="v in voices" :key="v.key" class="voice-option" :class="{ active: ttsVoice === v.key }" @click="ttsVoice = v.key; saveVoice()">
          {{ v.label }}
        </div>

        <div class="modal-actions">
          <button class="btn-cancel" @click="showSettings=false">关闭</button>
          <button class="btn-confirm" @click="showSettings=false">完成</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useChatStore } from '@/stores/chat';

const auth = useAuthStore();
const chatStore = useChatStore();
const router = useRouter();

// Auth modal
const showAuth = ref(false);
const authTab = ref<'login' | 'register'>('login');
const authLoading = ref(false);
const authError = ref('');
const loginForm = reactive({ email: '', password: '' });
const regForm = reactive({ username: '', email: '', password: '' });

async function doLogin() {
  authError.value = ''; authLoading.value = true;
  try { await auth.login(loginForm.email, loginForm.password); showAuth.value = false; }
  catch (e: any) { authError.value = e?.response?.data?.detail || '登录失败'; }
  finally { authLoading.value = false; }
}
async function doRegister() {
  authError.value = '';
  if (regForm.password.length < 6) { authError.value = '密码至少6位'; return; }
  authLoading.value = true;
  try { await auth.register(regForm.username, regForm.email, regForm.password); showAuth.value = false; }
  catch (e: any) { authError.value = e?.response?.data?.detail || '注册失败'; }
  finally { authLoading.value = false; }
}

// Settings
const showSettings = ref(false);

// Theme
const themes = [
  { key: 'default', label: '默认' }, { key: 'ocean', label: '海洋' },
  { key: 'sunset', label: '日落' }, { key: 'forest', label: '森林' },
  { key: 'rose', label: '玫瑰' }, { key: 'midnight', label: '午夜' }, { key: 'light', label: '纯白' },
];
const currentTheme = ref(localStorage.getItem('theme') || 'default');
const themeClass = ref(currentTheme.value === 'default' ? '' : `theme-${currentTheme.value}`);
const customBg = ref('#0f172a');
const customAccent = ref('#38bdf8');

function setTheme(key: string) {
  currentTheme.value = key;
  if (key === 'default') {
    themeClass.value = '';
    document.documentElement.classList.remove(...Array.from(document.documentElement.classList).filter(c => c.startsWith('theme-')));
  } else {
    themeClass.value = `theme-${key}`;
    // Remove other theme classes
    document.documentElement.classList.remove(...themes.filter(t => t.key !== key).map(t => `theme-${t.key}`));
    document.documentElement.classList.add(`theme-${key}`);
  }
  localStorage.setItem('theme', key);
}

function applyCustomTheme() {
  document.documentElement.style.setProperty('--bg-primary', customBg.value);
  document.documentElement.style.setProperty('--accent-primary', customAccent.value);
  localStorage.setItem('customTheme', JSON.stringify({ bg: customBg.value, accent: customAccent.value }));
}

// Load custom theme on init
const savedCustom = localStorage.getItem('customTheme');
if (savedCustom) {
  try {
    const c = JSON.parse(savedCustom);
    customBg.value = c.bg;
    customAccent.value = c.accent;
    document.documentElement.style.setProperty('--bg-primary', c.bg);
    document.documentElement.style.setProperty('--accent-primary', c.accent);
  } catch {}
}

// TTS Voice
const ttsVoice = ref(localStorage.getItem('ttsVoice') || 'en-US-female');
const voices = [
  { key: 'en-US-female', label: '🔊 Jenny (美式女声)' },
  { key: 'en-US-male', label: '🔊 Guy (美式男声)' },
  { key: 'en-GB-female', label: '🔊 Sonia (英式女声)' },
  { key: 'en-GB-male', label: '🔊 Ryan (英式男声)' },
];
function saveVoice() {
  localStorage.setItem('ttsVoice', ttsVoice.value);
}

// Init
if (currentTheme.value !== 'default') {
  document.documentElement.classList.add(`theme-${currentTheme.value}`);
}
</script>
