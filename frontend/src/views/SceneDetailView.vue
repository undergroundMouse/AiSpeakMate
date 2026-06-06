<template>
  <div class="scene-detail">
    <header class="page-header">
      <router-link to="/scenes" class="back-link">&larr; 返回场景列表</router-link>
    </header>

    <!-- Loading -->
    <p v-if="sceneStore.loading" class="status">加载中...</p>

    <!-- Error -->
    <p v-if="errorMsg" class="status error">{{ errorMsg }}</p>

    <!-- Detail -->
    <div v-if="scene && !sceneStore.loading" class="detail-card">
      <div class="scene-info">
        <span class="scene-icon">{{ sceneIcon }}</span>
        <div>
          <h1>{{ scene.name }}</h1>
          <span v-if="difficultyLabel" class="difficulty" :class="difficultyClass">
            {{ difficultyLabel }}
          </span>
        </div>
      </div>

      <div class="intro-section">
        <p class="opening-line">"{{ scene.opening_line }}"</p>
        <p class="role-prompt">{{ scene.role_prompt }}</p>
      </div>

      <!-- Vocabulary section -->
      <div v-if="scene.vocab_list?.length" class="section vocab-section">
        <h3>核心词汇</h3>
        <ul class="vocab-list">
          <li v-for="(v, idx) in scene.vocab_list" :key="idx" class="vocab-item">
            <span class="vocab-word">{{ v.word }}</span>
            <span v-if="v.phonetic" class="vocab-phonetic">{{ v.phonetic }}</span>
            <span v-if="v.translation" class="vocab-translation">{{ v.translation }}</span>
          </li>
        </ul>
      </div>

      <!-- Sentence patterns section -->
      <div v-if="scene.sentence_patterns?.length" class="section patterns-section">
        <h3>句式模板</h3>
        <ul class="patterns-list">
          <li v-for="(p, idx) in scene.sentence_patterns" :key="idx" class="pattern-item">
            <p class="pattern-text">{{ p.pattern }}</p>
            <p v-if="p.translation" class="pattern-translation">{{ p.translation }}</p>
            <p v-if="p.example" class="pattern-example">例：{{ p.example }}</p>
          </li>
        </ul>
      </div>

      <div class="meta-row">
        <span v-if="scene.suggested_duration_minutes">
          预计时长：{{ scene.suggested_duration_minutes }} 分钟
        </span>
        <span v-if="difficultyLabel" class="meta-diff">
          难度：{{ difficultyLabel }}
        </span>
      </div>

      <button
        class="btn btn-start"
        :disabled="starting"
        @click="startSession"
      >
        {{ starting ? '创建会话中...' : '开始练习' }}
      </button>

      <p v-if="startError" class="start-error">{{ startError }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useSceneStore } from '@/stores/scene';
import { useAuthStore } from '@/stores/auth';
import { sessionApi } from '@/api/session';

const DIFFICULTY_MAP: Record<string, string> = {
  beginner: '初级',
  intermediate: '中级',
  advanced: '高级',
};

const route = useRoute();
const router = useRouter();
const sceneStore = useSceneStore();
const auth = useAuthStore();

const errorMsg = ref('');
const starting = ref(false);
const startError = ref('');

const scene = computed(() => sceneStore.currentScene);

const sceneIcon = computed(() => {
  const name = scene.value?.name || '';
  if (name.includes('餐厅') || name.includes('Restaurant')) return '🍽️';
  if (name.includes('酒店') || name.includes('Hotel')) return '🏨';
  if (name.includes('机场') || name.includes('Airport')) return '✈️';
  if (name.includes('医院') || name.includes('Hospital')) return '🏥';
  if (name.includes('购物') || name.includes('Shopping')) return '🛍️';
  if (name.includes('面试') || name.includes('Interview')) return '💼';
  if (name.includes('演讲') || name.includes('Presentation')) return '🎤';
  if (name.includes('日常') || name.includes('Daily')) return '💬';
  return '🎯';
});

const difficultyLevel = computed(() => {
  const settings = scene.value?.difficulty_settings;
  if (!settings) return null;
  return settings.level || null;
});

const difficultyLabel = computed(() => {
  const level = difficultyLevel.value;
  if (!level) return '';
  return DIFFICULTY_MAP[level] || level;
});

const difficultyClass = computed(() => difficultyLevel.value || '');

async function loadDetail() {
  errorMsg.value = '';
  const id = Number(route.params.id);
  if (isNaN(id)) {
    errorMsg.value = '无效的场景 ID';
    return;
  }
  try {
    await sceneStore.fetchSceneDetail(id);
  } catch (e: any) {
    errorMsg.value = '加载场景详情失败';
  }
}

async function startSession() {
  if (!scene.value) return;
  startError.value = '';
  starting.value = true;
  try {
    const session = await sessionApi.create({ scene_id: scene.value.scene_id });
    router.push(`/chat/${session.session_id}`);
  } catch (e: any) {
    startError.value = e?.response?.data?.detail || '创建会话失败，请稍后重试';
  } finally {
    starting.value = false;
  }
}

onMounted(() => {
  if (!auth.isAuthenticated) {
    router.push('/');
    return;
  }
  loadDetail();
});
</script>

<style scoped>
.scene-detail {
  max-width: 700px;
  margin: 0 auto;
  padding: 24px;
}
.page-header {
  margin-bottom: 24px;
}
.back-link {
  color: var(--text-secondary);
  font-size: 0.95rem;
}
.status {
  text-align: center;
  color: var(--text-secondary);
  padding: 60px 0;
}
.error {
  color: var(--accent-danger);
}

.detail-card {
  background: var(--bg-secondary);
  border-radius: var(--radius);
  padding: 32px;
  box-shadow: var(--shadow);
}
.scene-info {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}
.scene-icon {
  font-size: 2.5rem;
}
.scene-info h1 {
  font-size: 1.5rem;
  margin-bottom: 6px;
}
.difficulty {
  font-size: 0.75rem;
  padding: 2px 10px;
  border-radius: 20px;
  background: var(--bg-card);
  text-transform: uppercase;
  margin-right: 8px;
}
.difficulty.beginner { color: var(--accent-success); }
.difficulty.intermediate { color: var(--accent-warning); }
.difficulty.advanced { color: var(--accent-danger); }

.intro-section {
  margin-bottom: 20px;
  padding: 16px;
  background: var(--bg-primary);
  border-radius: 8px;
}
.opening-line {
  font-style: italic;
  font-size: 1.05rem;
  color: var(--accent-primary);
  margin-bottom: 10px;
}
.role-prompt {
  color: var(--text-secondary);
  font-size: 0.92rem;
  line-height: 1.6;
}

.section {
  margin-bottom: 20px;
  padding: 16px;
  background: var(--bg-primary);
  border-radius: 8px;
}
.section h3 {
  font-size: 0.95rem;
  margin-bottom: 10px;
  color: var(--accent-primary);
}

.vocab-list {
  list-style: none;
  padding: 0;
}
.vocab-item {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px solid var(--border-color, #334155);
  font-size: 0.9rem;
}
.vocab-item:last-child {
  border-bottom: none;
}
.vocab-word {
  font-weight: 600;
  min-width: 80px;
  color: var(--text-primary);
}
.vocab-phonetic {
  color: var(--text-secondary);
  font-size: 0.82rem;
}
.vocab-translation {
  color: var(--text-secondary);
  margin-left: auto;
}

.patterns-list {
  list-style: none;
  padding: 0;
}
.pattern-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color, #334155);
}
.pattern-item:last-child {
  border-bottom: none;
}
.pattern-text {
  font-weight: 600;
  color: var(--text-primary);
}
.pattern-translation {
  color: var(--text-secondary);
  font-size: 0.85rem;
  margin-top: 2px;
}
.pattern-example {
  color: var(--accent-primary);
  font-size: 0.82rem;
  margin-top: 2px;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 0.85rem;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.meta-diff {
  background: var(--bg-card);
  padding: 2px 10px;
  border-radius: 10px;
}

.btn-start {
  width: 100%;
  padding: 14px;
  font-size: 1.1rem;
  font-weight: 700;
  background: var(--accent-primary);
  color: #0f172a;
  border-radius: 10px;
  transition: opacity 0.2s;
}
.btn-start:hover { opacity: 0.85; }
.btn-start:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.start-error {
  margin-top: 10px;
  color: var(--accent-danger);
  font-size: 0.9rem;
  text-align: center;
}
</style>
