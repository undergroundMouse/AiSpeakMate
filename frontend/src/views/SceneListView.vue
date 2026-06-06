<template>
  <div class="scene-list">
    <header class="page-header">
      <router-link to="/" class="back-link">&larr; 首页</router-link>
      <h1>选择练习场景</h1>
    </header>

    <!-- Search & filter -->
    <div class="toolbar">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索场景..."
        class="search-input"
        @input="onSearch"
      />
      <select v-model="categoryFilter" @change="loadScenes" class="filter-select">
        <option value="">全部分类</option>
        <option value="daily">日常</option>
        <option value="business">商务</option>
        <option value="travel">旅行</option>
        <option value="academic">学术</option>
      </select>
      <select v-model="difficultyFilter" @change="loadScenes" class="filter-select">
        <option value="">全部难度</option>
        <option value="beginner">初级</option>
        <option value="intermediate">中级</option>
        <option value="advanced">高级</option>
      </select>
    </div>

    <!-- Loading -->
    <p v-if="sceneStore.loading" class="status">加载中...</p>

    <!-- Error -->
    <p v-if="errorMsg" class="status error">{{ errorMsg }}</p>

    <!-- Empty -->
    <p v-if="!sceneStore.loading && !errorMsg && sceneStore.scenes.length === 0" class="status">
      暂无场景数据
    </p>

    <!-- Scene cards -->
    <div v-if="sceneStore.scenes.length > 0" class="grid">
      <div
        v-for="scene in sceneStore.scenes"
        :key="scene.id"
        class="scene-card"
        @click="goToScene(scene.id)"
      >
        <div class="card-header">
          <span class="icon">{{ scene.icon || '🎯' }}</span>
          <span class="difficulty" :class="scene.difficulty">
            {{ DIFFICULTY_MAP[scene.difficulty] || scene.difficulty }}
          </span>
        </div>
        <h3>{{ scene.title }}</h3>
        <p class="desc">{{ scene.description }}</p>
        <div class="card-meta">
          <span>{{ scene.category }}</span>
          <span v-if="scene.duration_minutes">{{ scene.duration_minutes }} 分钟</span>
        </div>
        <div v-if="scene.tags.length > 0" class="tags">
          <span v-for="tag in scene.tags" :key="tag" class="tag">{{ tag }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useSceneStore } from '@/stores/scene';
import { useAuthStore } from '@/stores/auth';

const DIFFICULTY_MAP: Record<string, string> = {
  beginner: '初级',
  intermediate: '中级',
  advanced: '高级',
};

const sceneStore = useSceneStore();
const auth = useAuthStore();
const router = useRouter();

const searchQuery = ref('');
const categoryFilter = ref('');
const difficultyFilter = ref('');
const errorMsg = ref('');

let debounceTimer: ReturnType<typeof setTimeout>;

function onSearch() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    loadScenes();
  }, 350);
}

async function loadScenes() {
  errorMsg.value = '';
  try {
    await sceneStore.fetchScenes(
      categoryFilter.value || undefined,
      difficultyFilter.value || undefined,
      searchQuery.value || undefined,
    );
  } catch (e: any) {
    errorMsg.value = '加载场景失败，请刷新页面重试';
  }
}

function goToScene(id: string) {
  if (!auth.isAuthenticated) {
    router.push('/');
    return;
  }
  router.push(`/scenes/${id}`);
}

onMounted(() => {
  if (!auth.isAuthenticated) {
    router.push('/');
    return;
  }
  loadScenes();
});
</script>

<style scoped>
.scene-list {
  max-width: 1000px;
  margin: 0 auto;
  padding: 24px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}
.back-link {
  font-size: 0.95rem;
  color: var(--text-secondary);
}
.page-header h1 {
  font-size: 1.5rem;
}

/* Toolbar */
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.search-input {
  flex: 1;
  min-width: 200px;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--bg-card);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 0.95rem;
}
.search-input:focus {
  border-color: var(--accent-primary);
  outline: none;
}
.filter-select {
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--bg-card);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 0.9rem;
}

.status {
  text-align: center;
  color: var(--text-secondary);
  padding: 40px 0;
}
.error {
  color: var(--accent-danger);
}

/* Grid */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.scene-card {
  background: var(--bg-secondary);
  border-radius: var(--radius);
  padding: 20px;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  box-shadow: var(--shadow);
}
.scene-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 30px rgba(56, 189, 248, 0.15);
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.icon {
  font-size: 1.5rem;
}
.difficulty {
  font-size: 0.75rem;
  padding: 3px 10px;
  border-radius: 20px;
  background: var(--bg-card);
  text-transform: uppercase;
}
.difficulty.beginner { color: var(--accent-success); }
.difficulty.intermediate { color: var(--accent-warning); }
.difficulty.advanced { color: var(--accent-danger); }

.scene-card h3 {
  font-size: 1.1rem;
  margin-bottom: 6px;
}
.desc {
  color: var(--text-secondary);
  font-size: 0.88rem;
  line-height: 1.45;
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-meta {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 0.8rem;
  margin-bottom: 8px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  background: var(--bg-card);
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 0.75rem;
  color: var(--accent-primary);
}
</style>