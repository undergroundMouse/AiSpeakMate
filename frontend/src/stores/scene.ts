import { defineStore } from 'pinia';
import { ref } from 'vue';
import { sceneApi, type CategoryWithScenes, type SceneDetail } from '@/api/scene';

export const useSceneStore = defineStore('scene', () => {
  const categories = ref<CategoryWithScenes[]>([]);
  const currentScene = ref<SceneDetail | null>(null);
  const loading = ref(false);

  async function fetchScenes() {
    loading.value = true;
    try {
      const response = await sceneApi.list();
      categories.value = response.categories;
    } finally {
      loading.value = false;
    }
  }

  async function fetchSceneDetail(id: number) {
    loading.value = true;
    try {
      currentScene.value = await sceneApi.getById(id);
    } finally {
      loading.value = false;
    }
  }

  return { categories, currentScene, loading, fetchScenes, fetchSceneDetail };
});
