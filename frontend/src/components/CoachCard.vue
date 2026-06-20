<template>
  <div class="coach-card">
    <div class="coach-header">
      <div class="coach-meta">
        <span class="scene-name">{{ card.scene_name }}</span>
        <span class="duration">{{ formatDuration(card.duration_seconds) }}</span>
      </div>
      <div class="score-block" v-if="!card.chat_only && card.overall_score != null">
        <span class="score-value">{{ card.overall_score }}</span>
        <span class="score-label">综合分</span>
        <span v-if="card.score_delta !== null" class="score-delta" :class="deltaClass">
          {{ card.score_delta >= 0 ? '+' : '' }}{{ card.score_delta }}
        </span>
      </div>
    </div>

    <div v-if="card.strengths.length" class="insight-section strength">
      <h3>{{ card.chat_only ? '💬 今天聊得怎么样' : '👍 今天做得好的' }}</h3>
      <p class="insight-text">{{ card.strengths[0].text }}</p>
      <p v-if="card.strengths[0].detail" class="insight-detail">{{ card.strengths[0].detail }}</p>
    </div>

    <div v-if="card.improvements.length" class="insight-section improvement">
      <h3>💡 可以更好的</h3>
      <ul class="improvement-list">
        <li v-for="(item, idx) in card.improvements" :key="idx">
          <span class="insight-text">{{ item.text }}</span>
          <span v-if="item.detail" class="insight-detail">{{ item.detail }}</span>
        </li>
      </ul>
    </div>

    <div v-if="nextOptions.length" class="next-practice">
      <h3>{{ card.chat_only ? '还想聊吗？' : '明天练什么？' }}</h3>
      <div class="next-buttons">
        <button
          v-for="opt in nextOptions"
          :key="opt.kind"
          class="btn-next"
          :class="opt.kind"
          @click="$emit('start-practice', opt.scene_id)"
        >
          <span class="btn-label">{{ opt.label }}</span>
          <span class="btn-reason">{{ opt.reason }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { CoachCard, NextPracticeOption } from '@/api/summary';

const props = defineProps<{
  card: CoachCard;
  nextOptions?: NextPracticeOption[];
}>();

defineEmits<{
  'start-practice': [sceneId: number];
}>();

const nextOptions = computed(() => props.nextOptions ?? []);

const deltaClass = computed(() => {
  if (props.card.score_delta === null) return '';
  return props.card.score_delta >= 0 ? 'delta-up' : 'delta-down';
});

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}分${s.toString().padStart(2, '0')}秒`;
}
</script>

<style scoped>
.coach-card {
  background: var(--bg-secondary);
  border-radius: var(--radius);
  padding: 24px;
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.coach-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.coach-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.scene-name {
  font-size: 1.1rem;
  font-weight: 700;
}

.duration {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.score-block {
  text-align: right;
}

.score-value {
  display: block;
  font-size: 2rem;
  font-weight: 800;
  color: var(--accent-primary);
  line-height: 1;
}

.score-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.score-delta {
  display: inline-block;
  margin-top: 4px;
  font-size: 0.8rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 12px;
}

.delta-up {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}

.delta-down {
  background: rgba(248, 113, 113, 0.15);
  color: #f87171;
}

.insight-section h3 {
  font-size: 0.95rem;
  margin-bottom: 8px;
}

.insight-text {
  font-size: 0.92rem;
  line-height: 1.5;
}

.insight-detail {
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin-top: 4px;
}

.improvement-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.next-practice h3 {
  font-size: 0.95rem;
  margin-bottom: 12px;
}

.next-buttons {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.btn-next {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 14px 16px;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  text-align: left;
  transition: opacity 0.15s;
}

.btn-next:hover {
  opacity: 0.9;
}

.btn-next.consolidate {
  background: linear-gradient(135deg, var(--accent-primary), #6366f1);
  color: #0f172a;
}

.btn-next.explore {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--bg-card);
}

.btn-label {
  font-weight: 700;
  font-size: 0.95rem;
}

.btn-reason {
  font-size: 0.8rem;
  opacity: 0.85;
}
</style>
