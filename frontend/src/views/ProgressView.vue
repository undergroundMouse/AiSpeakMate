<template>
  <div class="progress-view">
    <header class="page-header">
      <router-link to="/scenes" class="back-link">&larr; 场景列表</router-link>
      <h1>学习进度</h1>
      <div v-if="progress" class="rating-badge" :class="ratingClass">
        {{ progress.overall_rating }}
      </div>
    </header>

    <!-- Loading / Error -->
    <p v-if="loading" class="status">加载中...</p>
    <p v-if="errorMsg" class="status error">{{ errorMsg }}</p>

    <div v-if="progress && !loading" class="content">
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
      <div v-if="hasDimensionScores" class="section">
        <h2>维度分析</h2>
        <div class="dimension-list">
          <div
            v-for="(score, dim) in progress.snapshots[progress.snapshots.length - 1].dimension_scores"
            :key="dim"
            class="dim-row"
          >
            <span class="dim-name">{{ dimLabels[dim] || dim }}</span>
            <div class="dim-bar-wrap">
              <div class="dim-bar" :style="{ width: (score / 100 * 100) + '%' }"></div>
            </div>
            <span class="dim-value">{{ score }}</span>
          </div>
        </div>
      </div>

      <!-- Strengths -->
      <div v-if="progress.strengths?.length" class="section">
        <h2>优势</h2>
        <ul class="list">
          <li v-for="(s, i) in progress.strengths" :key="i">
            {{ typeof s === 'string' ? s : (s as any).label || (s as any).name || JSON.stringify(s) }}
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
            <span class="weakness-cat">{{ w.category }}</span>
            <span class="weakness-trend" :class="getTrendClass(w.trend)">
              {{ w.trend === 'improving' ? '↑ 改善中' : w.trend === 'declining' ? '↓ 下降' : '— 稳定' }}
            </span>
          </div>
          <p class="weakness-item">{{ w.item }}</p>
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
            :key="a.achievement_key"
            class="achieve-card"
            :class="{ locked: !a.unlocked_at }"
          >
            <div class="achieve-icon">{{ a.icon || '🏆' }}</div>
            <h3 class="achieve-title">{{ a.title }}</h3>
            <p class="achieve-desc">{{ a.description }}</p>
            <div v-if="!a.unlocked_at" class="achieve-progress">
              <div class="ap-bar-wrap">
                <div class="ap-bar" :style="{ width: a.progress + '%' }"></div>
              </div>
              <span>{{ Math.round(a.progress) }}%</span>
            </div>
            <span v-else class="unlock-date">{{ formatDate(a.unlocked_at) }}</span>
          </div>
        </div>
        <p v-if="achievements" class="locked-total">
          还有 {{ achievements.total_locked }} 项成就等待解锁
        </p>
      </div>
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

const router = useRouter();
const auth = useAuthStore();

const loading = ref(false);
const errorMsg = ref('');
const progress = ref<UserProgress | null>(null);

const achievementsLoading = ref(false);
const achievements = ref<AchievementList | null>(null);

const ratingClass = computed(() => {
  const r = progress.value?.overall_rating || '';
  if (r.includes('A')) return 'rating-a';
  if (r.includes('B')) return 'rating-b';
  if (r.includes('C')) return 'rating-c';
  return 'rating-d';
});

const hasDimensionScores = computed(() => {
  const snaps = progress.value?.snapshots;
  if (!snaps?.length) return false;
  const last = snaps[snaps.length - 1];
  return last.dimension_scores && Object.keys(last.dimension_scores).length > 0;
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
  loading.value = true;
  errorMsg.value = '';
  try {
    progress.value = await summaryApi.getProgress();
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '加载进度失败';
  } finally {
    loading.value = false;
  }

  achievementsLoading.value = true;
  try {
    achievements.value = await summaryApi.getAchievements();
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
.rating-badge {
  padding: 6px 16px;
  border-radius: 20px;
  font-weight: 800;
  font-size: 1.1rem;
}
.rating-a { background: #16a34a; color: #fff; }
.rating-b { background: var(--accent-primary); color: #0f172a; }
.rating-c { background: var(--accent-warning); color: #0f172a; }
.rating-d { background: var(--accent-danger); color: #fff; }

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
  flex: 0 0 70px;
  font-size: 0.88rem;
  color: var(--text-secondary);
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

@media (max-width: 600px) {
  .stats-row { grid-template-columns: repeat(3, 1fr); }
  .achievements-grid { grid-template-columns: 1fr 1fr; }
}
</style>