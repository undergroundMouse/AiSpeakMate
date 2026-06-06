import apiClient from './client';

export interface RadarScores {
  fluency: number;
  vocabulary: number;
  grammar: number;
  pronunciation: number;
  interaction: number;
}

export interface Highlight {
  title: string;
  description: string;
  example_sentence?: string;
}

export interface PracticeSuggestion {
  title: string;
  description: string;
  resource_type?: string;
  resource_url?: string;
}

export interface SessionSummary {
  id: string;
  session_id: string;
  radar: RadarScores;
  highlights: Highlight[];
  practice_suggestions: PracticeSuggestion[];
  share_image_url: string | null;
  created_at: string;
}

export interface ProgressSnapshot {
  snapshot_date: string;
  total_score: number;
  dimension_scores: Record<string, number>;
  session_count: number;
  total_duration_seconds: number;
}

export interface WeaknessRecord {
  period_start: string;
  period_end: string;
  category: string;
  item: string;
  error_count: number;
  trend: string | null;
}

export interface UserProgress {
  user_id: string;
  overall_rating: string;
  total_score: number;
  total_sessions: number;
  total_hours: number;
  snapshots: ProgressSnapshot[];
  weaknesses: WeaknessRecord[];
  strengths: Record<string, unknown>[];
}

export interface AchievementInfo {
  achievement_key: string;
  title: string;
  description: string;
  icon: string | null;
  unlocked_at: string | null;
  progress: number;
}

export interface AchievementList {
  user_id: string;
  achievements: AchievementInfo[];
  total_locked: number;
}

export const summaryApi = {
  getSessionSummary(sessionId: string) {
    return apiClient
      .get<SessionSummary>(`/sessions/${sessionId}/summary`)
      .then((res) => res.data);
  },

  getProgress() {
    return apiClient.get<UserProgress>('/progress').then((res) => res.data);
  },

  getAchievements() {
    return apiClient.get<AchievementList>('/achievements').then((res) => res.data);
  },
};