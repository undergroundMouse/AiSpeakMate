import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
    },
    {
      path: '/scenes',
      name: 'scenes',
      component: () => import('@/views/SceneListView.vue'),
    },
    {
      path: '/scenes/:id',
      name: 'scene-detail',
      component: () => import('@/views/SceneDetailView.vue'),
    },
    {
      path: '/chat/:sessionId',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
    },
    {
      path: '/summary/:sessionId',
      name: 'summary',
      component: () => import('@/views/SummaryView.vue'),
    },
    {
      path: '/progress',
      name: 'progress',
      component: () => import('@/views/ProgressView.vue'),
    },
  ],
});

export default router;