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

      <!-- Random challenge + Custom scene -->
      <div style="display:flex;gap:10px;justify-content:center;margin-bottom:20px;flex-wrap:wrap">
        <button class="btn-random-home" :disabled="randomLoading" @click="goToRandomScene" style="margin:0">
          {{ randomLoading ? '🎲 匹配中...' : '🎲 随机挑战' }}
        </button>
        <button class="btn-random-home" style="background:linear-gradient(135deg, var(--accent-primary), #6366f1);margin:0" @click="showCustomScene = true">
          ✨ 自定义场景
        </button>
      </div>

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

      <!-- Custom scenes -->
      <div v-if="customScenes.length > 0" style="margin-bottom:8px">
        <h2 class="section-title">自定义场景</h2>
        <div class="scene-grid">
          <div v-for="scene in customScenes" :key="scene.scene_id" class="scene-card" @click="startCustomFromList(scene)">
            <div class="card-header">
              <span class="card-icon">✨</span>
              <h3>{{ scene.name }}</h3>
            </div>
            <div class="difficulty-tags">
              <span v-for="lvl in scene.difficulty_levels" :key="lvl" class="diff" :class="lvl">{{ DIFF_MAP[lvl] || lvl }}</span>
            </div>
            <p class="desc">{{ scene.description }}</p>
            <div class="tags">
              <span class="tag">自定义</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <p v-if="totalScenes === 0 && !loading" style="text-align:center;color:var(--text-secondary);padding:40px 0">
        暂无可用场景
      </p>
    </div>

    <!-- Custom scene modal -->
    <div v-if="showCustomScene" class="modal-overlay" @click.self="showCustomScene=false">
      <div class="modal-box" style="max-width:500px">
        <h3>✨ 自定义场景</h3>
        <p style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:12px">描述你想要练习的场景，AI 将自动生成角色、开场白、词汇和句式</p>
        <input v-model="customTopic" placeholder="主题，如：在药店买药" style="width:100%;margin-bottom:8px" />
        <input v-model="customRole" placeholder="AI角色，如：药剂师 (可选)" style="width:100%;margin-bottom:8px" />
        <textarea v-model="customDesc" placeholder="详细描述，如：我感冒了需要买药，告诉药剂师我的症状，询问该吃什么药 (可选)" style="width:100%;height:70px;margin-bottom:12px;padding:8px;border-radius:8px;border:1px solid var(--bg-card);background:var(--bg-primary);color:var(--text-primary);font-size:0.88rem;resize:vertical;font-family:inherit"></textarea>
        <p v-if="customError" style="color:var(--accent-danger);font-size:0.8rem;margin-bottom:8px">{{ customError }}</p>
        <div class="modal-actions">
          <button class="btn-cancel" @click="showCustomScene=false">取消</button>
          <button class="btn-confirm" :disabled="customLoading || !customTopic.trim()" @click="createCustomScene">
            {{ customLoading ? 'AI 生成中...' : '生成场景' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Generated scene preview -->
    <div v-if="customSceneData" class="modal-overlay" @click.self="customSceneData=null">
      <div class="modal-box" style="max-width:520px;max-height:70vh;overflow-y:auto">
        <h3>✨ {{ customSceneData.topic }}</h3>
        <div style="margin:12px 0;padding:10px;background:var(--bg-primary);border-radius:8px">
          <p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:4px">AI 角色：</p>
          <p style="font-size:0.9rem">{{ customSceneData.role_prompt }}</p>
        </div>
        <div style="margin:12px 0;padding:10px;background:var(--bg-primary);border-radius:8px;border-left:3px solid var(--accent-primary)">
          <p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:4px">开场白：</p>
          <p style="font-size:0.95rem;font-style:italic">"{{ customSceneData.opening_line }}"</p>
        </div>
        <div v-if="customSceneData.vocab_list?.length" style="margin-bottom:10px">
          <h4 style="font-size:0.8rem;color:var(--text-secondary)">词汇</h4>
          <div style="display:flex;flex-wrap:wrap;gap:4px">
            <span v-for="v in customSceneData.vocab_list" :key="v.word" style="padding:2px 8px;background:var(--bg-card);border-radius:4px;font-size:0.78rem">{{ v.word }} ({{ v.translation }})</span>
          </div>
        </div>
        <div v-if="customSceneData.sentence_patterns?.length" style="margin-bottom:10px">
          <h4 style="font-size:0.8rem;color:var(--text-secondary)">句式</h4>
          <div v-for="(p,i) in customSceneData.sentence_patterns" :key="i" style="font-size:0.82rem;padding:3px 0;color:var(--text-primary)">{{ p.pattern }} <span style="color:var(--text-secondary)">({{ p.translation }})</span></div>
        </div>
        <div class="modal-actions">
          <button class="btn-cancel" @click="customSceneData=null">关闭</button>
          <button class="btn-confirm" @click="startCustomScene">开始练习</button>
        </div>
      </div>
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

// Custom scene
const showCustomScene = ref(false);
const customTopic = ref('');
const customRole = ref('');
const customDesc = ref('');
const customLoading = ref(false);
const customError = ref('');
const customSceneData = ref<any>(null);
const customScenes = ref<any[]>([]); // User-generated scenes displayed in the list

async function createCustomScene() {
  if (!auth.isAuthenticated) { customError.value = '请先登录'; return; }
  customError.value = ''; customLoading.value = true;
  try {
    const res = await sceneApi.createCustom({
      topic: customTopic.value,
      role: customRole.value || undefined,
      description: customDesc.value || undefined,
      difficulty: 'intermediate',
    });
    customSceneData.value = res;
    // Add to custom scenes list for display
    const newScene = {
      scene_id: `custom_${Date.now()}`,
      name: res.topic,
      description: res.role_prompt,
      difficulty_levels: ['intermediate'],
      tags: ['custom'],
      _custom: true,
      _data: res,
    };
    customScenes.value.push(newScene);
    showCustomScene.value = false;
  } catch (e: any) {
    customError.value = e?.response?.data?.detail || '场景生成失败';
  } finally { customLoading.value = false; }
}

async function startCustomFromList(scene: any) {
  if (!auth.isAuthenticated) return;
  customSceneData.value = scene._data;
  await startCustomScene();
}
async function startCustomScene() {
  if (!customSceneData.value) return;
  try {
    const session = await sessionApi.create({ scene_id: 1 });
    chatStore.sceneId = session.scene_id;
    // Store custom scene data for ChatView
    sessionStorage.setItem('customScene', JSON.stringify(customSceneData.value));
    router.push(`/chat/${session.session_id}`);
  } catch (e: any) {
    customError.value = '创建会话失败';
  }
}

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
