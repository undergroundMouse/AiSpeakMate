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
        <span class="scene-icon">{{ scene.icon || '🎯' }}</span>
        <div>
          <h1>{{ scene.title }}</h1>
          <span class="difficulty" :class="scene.difficulty">
            {{ DIFFICULTY_MAP[scene.difficulty] || scene.difficulty }}
          </span>
          <span class="category-badge">{{ scene.category }}</span>
        </div>
      </div>

      <p class="description">{{ scene.description }}</p>

      <div v-if="scene.suggested_phrases?.length" class="phrases">
        <h3>建议句型</h3>
        <ul>
          <li v-for="(phrase, idx) in scene.suggested_phrases" :key="idx">{{ phrase }}</li>
        </ul>
      </div>

      <div class="meta-row">
        <span v-if="scene.duration_minutes">预计时长：{{ scene.duration_minutes }} 分钟</span>
        <span v-if="scene.tags.length" class="tags">
          <span v-for="tag in scene.tags" :key="tag" class="tag">{{ tag }}</span>
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

async function loadDetail() {
  errorMsg.value = '';
  const id = route.params.id as string;
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
    const session = await sessionApi.create({ scene_id: scene.value.id });
    router.push(`/chat/${session.id}`);
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
.category-badge {
  font-size: 0.75rem;
  background: var(--accent-primary);
  color: #0f172a;
  padding: 2px 10px;
  border-radius: 20px;
}

.description {
  color: var(--text-secondary);
  line-height: 1.65;
  margin-bottom: 20px;
}

.phrases {
  margin-bottom: 20px;
  padding: 16px;
  background: var(--bg-primary);
  border-radius: 8px;
}
.phrases h3 {
  font-size: 0.95rem;
  margin-bottom: 8px;
  color: var(--accent-primary);
}
.phrases ul {
  list-style: disc;
  padding-left: 20px;
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.7;
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
.tags {
  display: flex;
  gap: 6px;
}
.tag {
  background: var(--bg-card);
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 0.75rem;
  color: var(--accent-primary);
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