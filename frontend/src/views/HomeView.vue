<template>
  <div class="home-page">
    <!-- Hero -->
    <div v-if="!auth.isAuthenticated" class="hero-section">
      <h1>🎓 随时随地练习口语</h1>
      <p class="subtitle">AI 驱动的英语口语学习助手 — 场景对话、实时纠错、发音评测</p>
    </div>

    <!-- Loading -->
    <p v-if="loading" style="text-align:center;color:var(--text-secondary);padding:40px 0">加载场景中...</p>

    <!-- Error -->
    <p v-if="errorMsg" style="text-align:center;color:var(--accent-danger);padding:20px 0">{{ errorMsg }}</p>

    <!-- Scene sections -->
    <div v-if="!loading && !errorMsg">
      <!-- Search -->
      <input v-model="searchQuery" class="search-bar" type="text" placeholder="🔍 搜索场景..." @input="onSearch" />

      <!-- Random challenge -->
      <button class="btn-random-home" :disabled="randomLoading" @click="goToRandomScene">
        {{ randomLoading ? '🎲 匹配中...' : '🎲 随机挑战' }}
      </button>

      <!-- Categories -->
      <div v-for="cat in filteredCategories" :key="cat.category_id" style="margin-bottom:8px">
        <h2 class="section-title">{{ cat.category_name }}</h2>
        <div class="scene-grid">
          <div v-for="scene in cat.scenes" :key="scene.scene_id" class="scene-card" @click="goToScene(scene.scene_id)">
            <div class="card-header">
              <span class="card-icon">{{ sceneIcon(scene.name) }}</span>
              <h3>{{ scene.name }}</h3>
            </div>
            <div class="difficulty-tags" v-if="scene.difficulty_levels?.length">
              <span v-for="lvl in scene.difficulty_levels" :key="lvl" class="diff" :class="lvl">{{ DIFF_MAP[lvl] || lvl }}</span>
            </div>
            <p class="desc">{{ scene.description }}</p>
            <div class="tags" v-if="scene.tags?.length">
              <span v-for="tag in scene.tags" :key="tag" class="tag">{{ tag }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <p v-if="totalScenes === 0 && !loading" style="text-align:center;color:var(--text-secondary);padding:40px 0">
        暂无可用场景
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useChatStore } from '@/stores/chat';
import { useSceneStore } from '@/stores/scene';
import { sceneApi, type CategoryWithScenes } from '@/api/scene';
import { sessionApi } from '@/api/session';

const DIFF_MAP: Record<string, string> = {
  beginner: '初级', intermediate: '中级', advanced: '高级',
};

const auth = useAuthStore();
const router = useRouter();
const sceneStore = useSceneStore();
const chatStore = useChatStore();

const loading = ref(false);
const errorMsg = ref('');
const searchQuery = ref('');
const randomLoading = ref(false);

const totalScenes = computed(() =>
  sceneStore.categories.flatMap(c => c.scenes).length
);

const filteredCategories = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return sceneStore.categories;
  const results: CategoryWithScenes[] = [];
  for (const cat of sceneStore.categories) {
    const matched = cat.scenes.filter(s =>
      s.name.toLowerCase().includes(q) ||
      s.description?.toLowerCase().includes(q) ||
      s.tags?.some(t => t.toLowerCase().includes(q))
    );
    if (matched.length) results.push({ ...cat, scenes: matched });
  }
  return results;
});

function sceneIcon(name: string): string {
  const n = name.toLowerCase();
  if (n.includes('coffee') || n.includes('咖啡')) return '☕';
  if (n.includes('restaurant') || n.includes('餐厅')) return '🍽️';
  if (n.includes('shop') || n.includes('购物') || n.includes('clothes')) return '🛍️';
  if (n.includes('airport') || n.includes('机场')) return '✈️';
  if (n.includes('hotel') || n.includes('酒店')) return '🏨';
  if (n.includes('direction') || n.includes('问路')) return '🗺️';
  if (n.includes('interview') || n.includes('面试')) return '💼';
  if (n.includes('meeting') || n.includes('会议')) return '📊';
  return '🎯';
}

let debounce: ReturnType<typeof setTimeout>;
function onSearch() { clearTimeout(debounce); debounce = setTimeout(() => {}, 200); }

async function loadScenes() {
  loading.value = true; errorMsg.value = '';
  try { await sceneStore.fetchScenes(); }
  catch { errorMsg.value = '加载场景失败'; }
  finally { loading.value = false; }
}

function goToScene(id: number) {
  if (!auth.isAuthenticated) { showAuth(); return; }
  router.push(`/scenes/${id}`);
}

function showAuth() { router.push('/'); /* Auth modal is in App.vue */ }

async function goToRandomScene() {
  if (!auth.isAuthenticated) { showAuth(); return; }
  randomLoading.value = true;
  try {
    const scene = await sceneApi.getRandom();
    router.push(`/scenes/${scene.scene_id}`);
  } catch { errorMsg.value = '获取随机场景失败'; }
  finally { randomLoading.value = false; }
}

onMounted(() => { loadScenes(); });
</script>
