<template>
  <div class="pron-detail">
    <header class="page-header">
      <router-link :to="`/summary/${sessionId}`" class="back-link">&larr; 返回总结</router-link>
      <h1>发音详情</h1>
    </header>

    <!-- Loading -->
    <p v-if="loading" class="status">加载中...</p>

    <!-- Error -->
    <p v-if="errorMsg" class="status error">{{ errorMsg }}</p>

    <!-- Content -->
    <div v-if="detail && !loading" class="content">
      <!-- Overall score card -->
      <div class="section score-card">
        <div class="overall-score" :class="scoreClass(detail.overall_score)">
          <span class="score-number">{{ detail.overall_score }}</span>
          <span class="score-label">总分 / 100</span>
        </div>

        <div class="dimension-scores">
          <div class="dim-item" v-if="detail.pronunciation_score != null">
            <span class="dim-name">音准</span>
            <div class="dim-bar-wrap">
              <div class="dim-bar" :style="{ width: detail.pronunciation_score + '%' }"
                   :class="barClass(detail.pronunciation_score)"></div>
            </div>
            <span class="dim-value">{{ detail.pronunciation_score }}</span>
          </div>
          <div class="dim-item" v-if="detail.fluency_score != null">
            <span class="dim-name">流利度</span>
            <div class="dim-bar-wrap">
              <div class="dim-bar" :style="{ width: detail.fluency_score + '%' }"
                   :class="barClass(detail.fluency_score)"></div>
            </div>
            <span class="dim-value">{{ detail.fluency_score }}</span>
          </div>
          <div class="dim-item" v-if="detail.completeness_score != null">
            <span class="dim-name">完整度</span>
            <div class="dim-bar-wrap">
              <div class="dim-bar" :style="{ width: detail.completeness_score + '%' }"
                   :class="barClass(detail.completeness_score)"></div>
            </div>
            <span class="dim-value">{{ detail.completeness_score }}</span>
          </div>
        </div>
      </div>

      <!-- Word-by-word phoneme breakdown -->
      <div v-if="detail.words?.length" class="section">
        <h2>音素逐词对比</h2>
        <p class="section-hint">点击音素查看发音对比 &bull;
          <span class="legend green">绿色 &gt;80</span>
          <span class="legend yellow">黄色 60-80</span>
          <span class="legend red">红色 &lt;60</span>
        </p>

        <div v-for="(word, wi) in detail.words" :key="wi" class="word-card">
          <div class="word-header">
            <span class="word-text">{{ word.word }}</span>
            <span class="word-score-badge" :class="scoreClass(word.score)">
              {{ word.score }}
            </span>
          </div>

          <div v-if="word.phonemes?.length" class="phoneme-row">
            <div
              v-for="(ph, pi) in word.phonemes"
              :key="pi"
              class="phoneme-block"
              :class="{
                'ph-error': ph.is_error,
                'ph-green': ph.phoneme_score >= 80,
                'ph-yellow': ph.phoneme_score >= 60 && ph.phoneme_score < 80,
                'ph-red': ph.phoneme_score < 60,
              }"
              :title="`${ph.phoneme}: ${ph.phoneme_score}分${ph.is_error ? ' — 建议: ' + (ph.suggested_phoneme || ph.phoneme) : ''}`"
            >
              <span class="ph-symbol">{{ ph.phoneme }}</span>
              <span class="ph-score">{{ ph.phoneme_score }}</span>
              <span v-if="ph.is_error && ph.suggested_phoneme" class="ph-suggest">
                → {{ ph.suggested_phoneme }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Prosody -->
      <div v-if="detail.prosody" class="section">
        <h2>韵律分析</h2>
        <div class="prosody-grid">
          <div class="prosody-item" v-if="detail.prosody.intonation_score != null">
            <span class="prosody-label">语调</span>
            <span class="prosody-value" :class="scoreClass(detail.prosody.intonation_score)">
              {{ detail.prosody.intonation_score }}/100
            </span>
          </div>
          <div class="prosody-item" v-if="detail.prosody.rhythm_score != null">
            <span class="prosody-label">节奏</span>
            <span class="prosody-value" :class="scoreClass(detail.prosody.rhythm_score)">
              {{ detail.prosody.rhythm_score }}/100
            </span>
          </div>
        </div>
        <div v-if="detail.prosody.stress_errors?.length" class="stress-errors">
          <h3>重音错误</h3>
          <div v-for="(se, sei) in detail.prosody.stress_errors" :key="sei" class="stress-item">
            <span class="stress-word">{{ (se as any).word || se }}</span>
            <span v-if="(se as any).expected_stress != null">
              期望重音: {{ (se as any).expected_stress }} →
              实际: {{ (se as any).actual_stress }}
            </span>
          </div>
        </div>
      </div>

      <!-- Advice -->
      <div v-if="detail.advice" class="section advice-section">
        <h2>纠音建议</h2>
        <p class="advice-text">{{ detail.advice }}</p>
      </div>

      <!-- Actions -->
      <div class="actions">
        <router-link :to="`/summary/${sessionId}`" class="btn btn-secondary">返回总结</router-link>
        <router-link to="/scenes" class="btn btn-primary">继续练习</router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { evaluationApi, type PronunciationDetail } from '@/api/evaluation';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const sessionId = route.params.sessionId as string;
const utteranceId = route.params.utteranceId as string;

const loading = ref(false);
const errorMsg = ref('');
const detail = ref<PronunciationDetail | null>(null);

function scoreClass(score: number): string {
  if (score >= 80) return 'score-green';
  if (score >= 60) return 'score-yellow';
  return 'score-red';
}

function barClass(score: number): string {
  if (score >= 80) return 'bar-green';
  if (score >= 60) return 'bar-yellow';
  return 'bar-red';
}

async function loadDetail() {
  loading.value = true;
  errorMsg.value = '';
  try {
    detail.value = await evaluationApi.getPronunciationDetail(sessionId, utteranceId);
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '加载发音详情失败';
  } finally {
    loading.value = false;
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
.pron-detail {
  max-width: 720px;
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
  gap: 20px;
}

/* Section */
.section {
  background: var(--bg-secondary);
  border-radius: var(--radius);
  padding: 24px;
  box-shadow: var(--shadow);
}
.section h2 {
  font-size: 1.05rem;
  color: var(--accent-primary);
  margin-bottom: 16px;
}
.section-hint {
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.legend {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 4px;
}
.legend.green { background: rgba(74, 222, 128, 0.15); color: #4ade80; }
.legend.yellow { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.legend.red { background: rgba(248, 113, 113, 0.15); color: #f87171; }

/* Overall score */
.score-card {
  text-align: center;
}
.overall-score {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 32px;
  border-radius: 16px;
  margin-bottom: 20px;
}
.overall-score.score-green { background: rgba(74, 222, 128, 0.12); }
.overall-score.score-yellow { background: rgba(251, 191, 36, 0.12); }
.overall-score.score-red { background: rgba(248, 113, 113, 0.12); }
.score-number {
  font-size: 3rem;
  font-weight: 800;
  line-height: 1;
}
.score-green .score-number { color: #4ade80; }
.score-yellow .score-number { color: #fbbf24; }
.score-red .score-number { color: #f87171; }
.score-label {
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* Dimension scores */
.dimension-scores {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 400px;
  margin: 0 auto;
}
.dim-item {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dim-name {
  flex: 0 0 56px;
  font-size: 0.88rem;
  color: var(--text-secondary);
  text-align: right;
}
.dim-bar-wrap {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: var(--bg-card);
  overflow: hidden;
}
.dim-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s;
}
.dim-bar.bar-green { background: #4ade80; }
.dim-bar.bar-yellow { background: #fbbf24; }
.dim-bar.bar-red { background: #f87171; }
.dim-value {
  flex: 0 0 32px;
  text-align: left;
  font-weight: 700;
  font-size: 0.9rem;
}

/* Word cards */
.word-card {
  padding: 12px;
  background: var(--bg-primary);
  border-radius: 8px;
  margin-bottom: 10px;
}
.word-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.word-text {
  font-weight: 600;
  font-size: 1rem;
}
.word-score-badge {
  padding: 2px 10px;
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 700;
}
.word-score-badge.score-green { background: rgba(74, 222, 128, 0.2); color: #4ade80; }
.word-score-badge.score-yellow { background: rgba(251, 191, 36, 0.2); color: #fbbf24; }
.word-score-badge.score-red { background: rgba(248, 113, 113, 0.2); color: #f87171; }

/* Phoneme blocks */
.phoneme-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.phoneme-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--bg-card);
  min-width: 50px;
  transition: transform 0.15s;
  cursor: default;
}
.phoneme-block:hover {
  transform: scale(1.08);
}
.phoneme-block.ph-green { border: 2px solid rgba(74, 222, 128, 0.4); }
.phoneme-block.ph-yellow { border: 2px solid rgba(251, 191, 36, 0.4); }
.phoneme-block.ph-red { border: 2px solid rgba(248, 113, 113, 0.4); }
.phoneme-block.ph-error {
  background: rgba(248, 113, 113, 0.12);
}
.ph-symbol {
  font-size: 0.85rem;
  font-weight: 600;
  font-family: monospace;
}
.ph-score {
  font-size: 0.7rem;
  color: var(--text-secondary);
  margin-top: 2px;
}
.ph-suggest {
  font-size: 0.65rem;
  color: var(--accent-warning);
  margin-top: 2px;
}

/* Prosody */
.prosody-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 12px;
}
.prosody-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
  background: var(--bg-primary);
  border-radius: 8px;
}
.prosody-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.prosody-value {
  font-size: 1.3rem;
  font-weight: 700;
}
.prosody-value.score-green { color: #4ade80; }
.prosody-value.score-yellow { color: #fbbf24; }
.prosody-value.score-red { color: #f87171; }

.stress-errors {
  margin-top: 12px;
}
.stress-errors h3 {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.stress-item {
  padding: 6px 10px;
  background: rgba(248, 113, 113, 0.08);
  border-radius: 6px;
  margin-bottom: 4px;
  font-size: 0.85rem;
  color: var(--accent-warning);
}

/* Advice */
.advice-text {
  font-size: 0.95rem;
  line-height: 1.7;
  color: var(--text-primary);
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

@media (max-width: 500px) {
  .prosody-grid { grid-template-columns: 1fr; }
}
</style>
