<template>
  <div class="summary-view">
    <header class="page-header">
      <router-link to="/scenes" class="back-link">&larr; 场景列表</router-link>
      <h1>对话总结</h1>
    </header>

    <!-- Loading -->
    <p v-if="loading" class="status">正在生成总结...</p>

    <!-- Error -->
    <p v-if="errorMsg" class="status error">{{ errorMsg }}</p>

    <!-- Summary content -->
    <div v-if="summary && !loading" class="content">
      <!-- Radar scores -->
      <div class="section">
        <h2>综合评分</h2>
        <div v-if="summary.radar" class="radar-scores">
          <div class="radar-item">
            <span class="radar-label">流利度</span>
            <div class="radar-bar-wrap">
              <div class="radar-bar" :style="{ width: (summary.radar.fluency / 10 * 100) + '%' }"></div>
            </div>
            <span class="radar-value">{{ summary.radar.fluency }}/10</span>
          </div>
          <div class="radar-item">
            <span class="radar-label">词汇量</span>
            <div class="radar-bar-wrap">
              <div class="radar-bar" :style="{ width: (summary.radar.vocabulary / 10 * 100) + '%' }"></div>
            </div>
            <span class="radar-value">{{ summary.radar.vocabulary }}/10</span>
          </div>
          <div class="radar-item">
            <span class="radar-label">语法</span>
            <div class="radar-bar-wrap">
              <div class="radar-bar" :style="{ width: (summary.radar.grammar / 10 * 100) + '%' }"></div>
            </div>
            <span class="radar-value">{{ summary.radar.grammar }}/10</span>
          </div>
          <div class="radar-item">
            <span class="radar-label">发音</span>
            <div class="radar-bar-wrap">
              <div class="radar-bar" :style="{ width: (summary.radar.pronunciation / 10 * 100) + '%' }"></div>
            </div>
            <span class="radar-value">{{ summary.radar.pronunciation }}/10</span>
          </div>
          <div class="radar-item">
            <span class="radar-label">互动</span>
            <div class="radar-bar-wrap">
              <div class="radar-bar" :style="{ width: (summary.radar.interaction / 10 * 100) + '%' }"></div>
            </div>
            <span class="radar-value">{{ summary.radar.interaction }}/10</span>
          </div>
        </div>
      </div>

      <!-- Highlights -->
      <div v-if="summary.highlights?.length" class="section">
        <h2>会话亮点</h2>
        <div v-for="(hl, idx) in summary.highlights" :key="idx" class="highlight-card">
          <h3>{{ hl.title }}</h3>
          <p class="hl-desc">{{ hl.description }}</p>
          <p v-if="hl.example_sentence" class="hl-example">例：{{ hl.example_sentence }}</p>
        </div>
      </div>

      <!-- Practice suggestions -->
      <div v-if="summary.practice_suggestions?.length" class="section">
        <h2>练习建议</h2>
        <div v-for="(sug, idx) in summary.practice_suggestions" :key="idx" class="suggestion-card">
          <h3>{{ sug.title }}</h3>
          <p class="sg-desc">{{ sug.description }}</p>
          <a v-if="sug.resource_url" :href="sug.resource_url" target="_blank" class="resource-link">
            查看资源 &rarr;
          </a>
        </div>
      </div>

      <!-- Share image -->
      <div v-if="summary.share_image_url" class="section">
        <h2>分享海报</h2>
        <img :src="summary.share_image_url" alt="分享海报" class="share-image" />
      </div>

      <div class="actions">
        <router-link to="/scenes" class="btn btn-primary">继续练习</router-link>
        <router-link to="/progress" class="btn btn-secondary">查看进度</router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { summaryApi, type SessionSummary } from '@/api/summary';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const loading = ref(false);
const errorMsg = ref('');
const summary = ref<SessionSummary | null>(null);

async function loadSummary() {
  const sessionId = route.params.sessionId as string;
  loading.value = true;
  errorMsg.value = '';
  try {
    summary.value = await summaryApi.getSessionSummary(sessionId);
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '加载总结失败';
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  if (!auth.isAuthenticated) {
    router.push('/');
    return;
  }
  loadSummary();
});
</script>

<style scoped>
.summary-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 28px;
}
.back-link {
  color: var(--text-secondary);
  font-size: 0.95rem;
}
.page-header h1 {
  font-size: 1.5rem;
}
.status {
  text-align: center;
  color: var(--text-secondary);
  padding: 60px 0;
}
.error { color: var(--accent-danger); }

.content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Sections */
.section {
  background: var(--bg-secondary);
  border-radius: var(--radius);
  padding: 24px;
  box-shadow: var(--shadow);
}
.section h2 {
  font-size: 1.1rem;
  color: var(--accent-primary);
  margin-bottom: 16px;
}

/* Radar scores */
.radar-scores {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.radar-item {
  display: flex;
  align-items: center;
  gap: 12px;
}
.radar-label {
  flex: 0 0 60px;
  font-size: 0.9rem;
  color: var(--text-secondary);
}
.radar-bar-wrap {
  flex: 1;
  height: 12px;
  border-radius: 6px;
  background: var(--bg-card);
  overflow: hidden;
}
.radar-bar {
  height: 100%;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--accent-primary), var(--accent-success));
  transition: width 0.5s ease;
}
.radar-value {
  flex: 0 0 50px;
  text-align: right;
  font-weight: 700;
  font-size: 0.95rem;
  color: var(--accent-primary);
}

/* Highlights & suggestions */
.highlight-card,
.suggestion-card {
  padding: 14px 0;
  border-bottom: 1px solid var(--bg-card);
}
.highlight-card:last-child,
.suggestion-card:last-child {
  border-bottom: none;
}
.highlight-card h3,
.suggestion-card h3 {
  font-size: 0.95rem;
  margin-bottom: 4px;
}
.hl-desc,
.sg-desc {
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.55;
}
.hl-example {
  margin-top: 6px;
  font-style: italic;
  color: var(--accent-primary);
  font-size: 0.85rem;
}
.resource-link {
  display: inline-block;
  margin-top: 8px;
  font-size: 0.85rem;
  color: var(--accent-primary);
}

/* Share image */
.share-image {
  max-width: 100%;
  border-radius: 8px;
}

/* Actions */
.actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  padding-top: 8px;
}
.btn {
  padding: 12px 28px;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
}
.btn-primary {
  background: var(--accent-primary);
  color: #0f172a;
}
.btn-secondary {
  background: var(--bg-card);
  color: var(--text-primary);
}
.btn:hover { opacity: 0.85; }
</style>