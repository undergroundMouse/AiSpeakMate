import { defineStore } from 'pinia';
import { ref } from 'vue';
import { sceneApi, type SceneItem, type SceneDetail } from '@/api/scene';

export const useSceneStore = defineStore('scene', () => {
  const scenes = ref<SceneItem[]>([]);
  const currentScene = ref<SceneDetail | null>(null);
  const loading = ref(false);

  async function fetchScenes(category?: string, difficulty?: string, search?: string) {
    loading.value = true;
    try {
      scenes.value = await sceneApi.list({ category, difficulty, search });
    } finally {
      loading.value = false;
    }
  }

  async function fetchSceneDetail(id: string) {
    loading.value = true;
    try {
      currentScene.value = await sceneApi.getById(id);
    } finally {
      loading.value = false;
    }
  }

  return { scenes, currentScene, loading, fetchScenes, fetchSceneDetail };
});