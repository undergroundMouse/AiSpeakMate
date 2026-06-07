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

export interface PronunciationErrorItem {
  utterance_id: string;
  sentence: string;
  score: number;
  detail_url: string;
}

export interface GrammarErrorItem {
  utterance_id: string;
  original: string;
  error_type: string;
  error_span: Record<string, number>;
  correction: string;
  corrected_sentence: string | null;
  explanation: string | null;
  severity: string;
}

export interface ExpressionSuggestionItem {
  original: string;
  suggestion: string;
  reason: string | null;
}

export interface SessionSummary {
  id: string;
  session_id: string;
  scene_name: string | null;
  duration_seconds: number;
  radar: RadarScores;
  highlights: Highlight[];
  top_pronunciation_errors: PronunciationErrorItem[];
  top_grammar_errors: GrammarErrorItem[];
  expression_suggestions: ExpressionSuggestionItem[];
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

export interface TrendPoint {
  date: string;
  score: number;
  dimension: string | null;
}

export interface ProgressTrend {
  points: TrendPoint[];
}

export interface TrendParams {
  start_date: string;
  end_date: string;
  dimension?: string;
  granularity?: string;
}

export interface WeaknessDistItem {
  category: string;
  item: string;
  total_error_count: number;
  trend: string | null;
}

export interface WeaknessDistResponse {
  user_id: string;
  period_start: string;
  period_end: string;
  items: WeaknessDistItem[];
}

export interface WeaknessDistParams {
  start_date: string;
  end_date: string;
  category?: string;
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

  getProgressTrend(params: TrendParams) {
    return apiClient
      .get<ProgressTrend>('/progress/trend', { params })
      .then((res) => res.data);
  },

  getWeaknessDistribution(params: WeaknessDistParams) {
    return apiClient
      .get<WeaknessDistResponse>('/progress/weaknesses/distribution', { params })
      .then((res) => res.data);
  },
};


