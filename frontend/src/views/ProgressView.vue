<template>
  <div class="progress-view">
    <header class="page-header">
      <router-link to="/" class="back-link">&larr; 首页</router-link>
      <h1>学习进度</h1>
    </header>

    <!-- Loading / Error -->
    <p v-if="loading" class="status">加载中...</p>
    <p v-if="errorMsg" class="status error">{{ errorMsg }}</p>

    <div
      v-if="progress && !loading && showPronunciationHint"
      class="info-banner"
    >
      发音与流利度分数需在对话中开启纠音，并配置讯飞开放平台（语音评测 ISE）后才会基于真实音频评测；未配置时可能显示文本估算或无数据。
    </div>

    <div v-if="progress && !loading" class="content">
      <!-- New user: no completed sessions yet -->
      <div v-if="progress.total_sessions === 0 && !progress.snapshots?.length" class="empty-state">
        <div class="empty-icon">📊</div>
        <h2>暂无学习数据</h2>
        <p>完成你的第一次对话练习后，这里将展示你的学习进度、评分趋势和能力分析。</p>
        <router-link to="/" class="btn-start-practice">开始练习</router-link>
      </div>

      <!-- Has data -->
      <template v-else>
      <!-- Overall stats -->
      <div class="stats-row">
        <div class="stat-card">
          <span class="stat-value">{{ progress.total_score }}</span>
          <span class="stat-label">总分</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ progress.total_sessions }}</span>
          <span class="stat-label">会话数</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ formatHours(progress.total_hours) }}</span>
          <span class="stat-label">练习时长</span>
        </div>
      </div>

      <!-- Progress timeline chart -->
      <div v-if="progress.snapshots?.length" class="section">
        <h2>进步趋势</h2>
        <div class="chart-container">
          <div class="chart-y">
            <span>100</span>
            <span>75</span>
            <span>50</span>
            <span>25</span>
            <span>0</span>
          </div>
          <div class="chart-area">
            <!-- Grid lines -->
            <div class="chart-grid">
              <div class="grid-line" v-for="i in 5" :key="i"></div>
            </div>
            <!-- Bars -->
            <div class="bars-row">
              <div
                v-for="(snap, idx) in progress.snapshots"
                :key="idx"
                class="bar-column"
                :title="`${snap.snapshot_date}: ${snap.total_score}分`"
              >
                <div
                  class="bar"
                  :style="{ height: (snap.total_score / 100 * 100) + '%' }"
                ></div>
                <span class="bar-label">{{ formatDate(snap.snapshot_date) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Dimension breakdown -->
      <div v-if="visibleDimensions.length" class="section">
        <h2>维度分析</h2>
        <div class="dimension-list">
          <div
            v-for="entry in visibleDimensions"
            :key="entry.key"
            class="dim-row"
          >
            <span class="dim-name">
              {{ dimLabels[entry.key] || entry.key }}
              <span v-if="entry.badge" class="dim-badge">{{ entry.badge }}</span>
            </span>
            <div v-if="entry.available" class="dim-bar-wrap">
              <div class="dim-bar" :style="{ width: entry.score + '%' }"></div>
            </div>
            <span v-else class="dim-unavailable">暂无数据</span>
            <span v-if="entry.available" class="dim-value">{{ entry.score }}</span>
          </div>
        </div>
      </div>

      <!-- Strengths -->
      <div v-if="progress.strengths?.length" class="section">
        <h2>优势</h2>
        <ul class="list">
          <li v-for="(s, i) in progress.strengths" :key="i">
            {{ typeof s === 'string' ? s : (s as any).area || (s as any).label || (s as any).name || JSON.stringify(s) }}
            <span v-if="(s as any).score"> ({{ (s as any).score }}分)</span>
          </li>
        </ul>
      </div>

      <!-- Weaknesses with trend -->
      <div v-if="progress.weaknesses?.length" class="section">
        <h2>薄弱点</h2>
        <div
          v-for="(w, idx) in progress.weaknesses"
          :key="idx"
          class="weakness-card"
        >
          <div class="weakness-header">
            <span class="weakness-cat">{{ categoryLabels[w.category] || w.category }}</span>
            <span class="weakness-trend" :class="getTrendClass(w.trend)">
              {{ w.trend === 'improving' ? '↑ 改善中' : w.trend === 'declining' ? '↓ 下降' : '— 稳定' }}
            </span>
          </div>
          <p class="weakness-item">{{ w.category === 'grammar' ? (grammarItemLabels[w.item] || w.item) : w.item }}</p>
          <span class="weakness-count">{{ w.error_count }} 次</span>
        </div>
      </div>

      <!-- Achievements -->
      <div class="section">
        <h2>成就</h2>
        <p v-if="achievementsLoading">加载中...</p>
        <div v-else-if="achievements" class="achievements-grid">
          <div
            v-for="a in achievements.achievements"
            :key="a.id"
            class="achieve-card"
            :class="{ locked: !a.unlocked_at }"
          >
            <img v-if="a.icon_url" :src="a.icon_url" class="achieve-icon-img" alt="" />
            <div v-else class="achieve-icon">{{ a.icon || '🏆' }}</div>
            <h3 class="achieve-title">{{ a.title }}</h3>
            <p class="achieve-desc">{{ a.description }}</p>
            <div v-if="!a.unlocked_at" class="achieve-progress">
              <div class="ap-bar-wrap">
                <div class="ap-bar" :style="{ width: (a.current_progress / a.target * 100) + '%' }"></div>
              </div>
              <span>{{ a.current_progress }}/{{ a.target }}</span>
            </div>
            <span v-else class="unlock-date">{{ formatDate(a.unlocked_at) }}</span>
          </div>
        </div>
        <p v-if="achievements" class="locked-total">
          还有 {{ (achievements?.achievements || []).filter(a => !a.unlocked_at).length }} 项成就等待解锁
        </p>
      </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { summaryApi, type UserProgress, type AchievementList } from '@/api/summary';

const dimLabels: Record<string, string> = {
  fluency: '流利度',
  vocabulary: '词汇量',
  grammar: '语法',
  pronunciation: '发音',
  interaction: '互动',
};

const categoryLabels: Record<string, string> = {
  pronunciation: '发音',
  grammar: '语法',
};

const grammarItemLabels: Record<string, string> = {
  past_tense: '过去时',
  present_perfect: '现在完成时',
  future_tense: '将来时',
  preposition: '介词',
  article: '冠词',
  plural: '复数',
  subject_verb: '主谓一致',
  word_order: '语序',
  modal_verb: '情态动词',
  conditional: '条件句',
  passive_voice: '被动语态',
  comparative: '比较级',
  pronoun: '代词',
};

const router = useRouter();
const auth = useAuthStore();

const loading = ref(false);
const errorMsg = ref('');
const progress = ref<UserProgress | null>(null);

const achievementsLoading = ref(false);
const achievements = ref<AchievementList | null>(null);

const hasDimensionScores = computed(() => visibleDimensions.value.length > 0);

const showPronunciationHint = computed(() => {
  const p = progress.value?.data_provenance;
  if (!p) return false;
  return p.pronunciation === 'none' || p.pronunciation === 'text_analysis';
});

function provenanceBadge(dim: string): string {
  const p = progress.value?.data_provenance;
  if (!p) return '';
  const sourceMap: Record<string, string | undefined> = {
    pronunciation: p.pronunciation,
    fluency: p.fluency,
    grammar: p.grammar,
    vocabulary: p.vocabulary,
    interaction: p.interaction,
  };
  const source = sourceMap[dim];
  if (source === 'text_analysis') return '基于文本估算';
  if (source === 'heuristic') return '参考指标';
  if (source === 'none') return '';
  return '';
}

const visibleDimensions = computed(() => {
  const snaps = progress.value?.snapshots;
  if (!snaps?.length) return [];
  const scores = snaps[snaps.length - 1].dimension_scores || {};
  const available = progress.value?.dimension_available;

  return Object.entries(scores).map(([key, score]) => {
    const isAvailable = available?.[key as keyof typeof available] !== false;
    return {
      key,
      score: Number(score),
      available: isAvailable,
      badge: isAvailable ? provenanceBadge(key) : '暂无数据',
    };
  });
});

function formatHours(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)} 分钟`;
  return `${hours.toFixed(1)} 小时`;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function getTrendClass(trend: string | null): string {
  if (trend === 'improving') return 'trend-up';
  if (trend === 'declining') return 'trend-down';
  return 'trend-stable';
}

async function loadData() {
  const userId = auth.user?.user_id;
  if (!userId) {
    errorMsg.value = '用户未登录';
    return;
  }

  loading.value = true;
  errorMsg.value = '';
  try {
    progress.value = await summaryApi.getProgress(userId);
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.message || e?.response?.data?.detail || '加载进度失败';
  } finally {
    loading.value = false;
  }

  achievementsLoading.value = true;
  try {
    achievements.value = await summaryApi.getAchievements(userId);
  } catch {
    // achievements optional
  } finally {
    achievementsLoading.value = false;
  }
}

onMounted(() => {
  if (!auth.isAuthenticated) {
    router.push('/');
    return;
  }
  loadData();
});
</script>

<style scoped>
.progress-view {
  max-width: 900px;
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
  flex: 1;
}

.status {
  text-align: center;
  color: var(--text-secondary);
  padding: 60px 0;
}
.error { color: var(--accent-danger); }

.info-banner {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 8px;
  background: rgba(56, 189, 248, 0.1);
  border: 1px solid rgba(56, 189, 248, 0.25);
  color: var(--text-secondary);
  font-size: 0.85rem;
  line-height: 1.5;
}

.content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Stats row */
.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.stat-card {
  background: var(--bg-secondary);
  border-radius: var(--radius);
  padding: 24px 16px;
  text-align: center;
  box-shadow: var(--shadow);
}
.stat-value {
  display: block;
  font-size: 2rem;
  font-weight: 700;
  color: var(--accent-primary);
}
.stat-label {
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-top: 4px;
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

/* Chart */
.chart-container {
  display: flex;
  gap: 8px;
  height: 180px;
}
.chart-y {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  font-size: 0.7rem;
  color: var(--text-secondary);
  padding: 0 4px;
}
.chart-area {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
}
.chart-grid {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.grid-line {
  border-top: 1px dashed var(--bg-card);
  height: 0;
}
.bars-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  height: 100%;
  position: relative;
  z-index: 1;
  padding-top: 8px;
}
.bar-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  height: 100%;
  justify-content: flex-end;
}
.bar {
  width: 24px;
  max-width: 60%;
  border-radius: 4px 4px 0 0;
  background: var(--accent-primary);
  transition: height 0.4s;
  min-height: 2px;
}
.bar-label {
  font-size: 0.65rem;
  color: var(--text-secondary);
  margin-top: 4px;
  white-space: nowrap;
}

/* Dimensions */
.dimension-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dim-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dim-name {
  flex: 0 0 110px;
  font-size: 0.88rem;
  color: var(--text-secondary);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.dim-badge {
  font-size: 0.68rem;
  color: var(--accent-warning);
  line-height: 1.2;
}
.dim-unavailable {
  flex: 1;
  font-size: 0.82rem;
  color: var(--text-secondary);
  font-style: italic;
}
.dim-bar-wrap {
  flex: 1;
  height: 10px;
  border-radius: 5px;
  background: var(--bg-card);
  overflow: hidden;
}
.dim-bar {
  height: 100%;
  border-radius: 5px;
  background: linear-gradient(90deg, var(--accent-primary), var(--accent-success));
  transition: width 0.4s;
}
.dim-value {
  flex: 0 0 36px;
  text-align: right;
  font-weight: 700;
  font-size: 0.9rem;
}

/* Strengths */
.list {
  list-style: disc;
  padding-left: 20px;
  color: var(--text-secondary);
  line-height: 1.8;
}

/* Weaknesses */
.weakness-card {
  padding: 12px;
  background: var(--bg-card);
  border-radius: 8px;
  margin-bottom: 8px;
}
.weakness-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.weakness-cat {
  font-weight: 600;
  font-size: 0.85rem;
}
.weakness-trend {
  font-size: 0.78rem;
  padding: 2px 8px;
  border-radius: 4px;
}
.trend-up { background: rgba(22, 163, 74, 0.15); color: #16a34a; }
.trend-down { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.trend-stable { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }
.weakness-item {
  font-size: 0.9rem;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.weakness-count {
  font-size: 0.78rem;
  color: var(--accent-warning);
}

/* Achievements */
.achievements-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}
.achieve-card {
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 18px;
  text-align: center;
  transition: opacity 0.3s;
}
.achieve-card.locked {
  opacity: 0.55;
}
.achieve-icon {
  font-size: 2rem;
  margin-bottom: 8px;
}
.achieve-title {
  font-size: 0.9rem;
  margin-bottom: 4px;
}
.achieve-desc {
  font-size: 0.78rem;
  color: var(--text-secondary);
  margin-bottom: 8px;
  line-height: 1.4;
}
.achieve-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.75rem;
  color: var(--text-secondary);
}
.ap-bar-wrap {
  flex: 1;
  height: 5px;
  border-radius: 3px;
  background: var(--bg-secondary);
  overflow: hidden;
}
.ap-bar {
  height: 100%;
  border-radius: 3px;
  background: var(--accent-primary);
}
.unlock-date {
  font-size: 0.72rem;
  color: var(--accent-success);
}
.locked-total {
  text-align: center;
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin-top: 12px;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
}
.empty-icon {
  font-size: 3.5rem;
  margin-bottom: 16px;
}
.empty-state h2 {
  font-size: 1.3rem;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.empty-state p {
  font-size: 0.9rem;
  color: var(--text-secondary);
  max-width: 400px;
  margin: 0 auto 24px;
  line-height: 1.6;
}
.btn-start-practice {
  display: inline-block;
  padding: 10px 28px;
  background: var(--accent-primary);
  color: #0f172a;
  border-radius: 8px;
  font-weight: 700;
  font-size: 0.95rem;
  text-decoration: none;
  transition: opacity 0.2s;
}
.btn-start-practice:hover { opacity: 0.85; }

@media (max-width: 600px) {
  .stats-row { grid-template-columns: repeat(3, 1fr); }
  .achievements-grid { grid-template-columns: 1fr 1fr; }
}
</style>