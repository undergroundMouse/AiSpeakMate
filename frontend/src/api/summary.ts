import apiClient from './client';

// --- Radar Scores ---
export interface RadarScores {
  fluency: number;
  vocabulary: number;
  grammar: number;
  pronunciation: number;
  interaction: number;
}

// --- Highlight ---
export interface Highlight {
  title: string;
  description: string;
  example_sentence?: string;
}

// --- Practice Suggestion (V1.1) ---
export interface PracticeSuggestion {
  type: string;
  target: string;
  suggested_exercise_id: string | null;
}

// --- Pronunciation Error ---
export interface PronunciationErrorItem {
  utterance_id: string;
  sentence: string;
  score: number;
  detail_url: string;
}

// --- Grammar Error ---
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

// --- Coach Card (light coach loop) ---
export interface CoachCardInsight {
  type: 'strength' | 'improvement';
  text: string;
  detail?: string | null;
}

export interface CoachCard {
  scene_name: string;
  duration_seconds: number;
  overall_score: number | null;
  strengths: CoachCardInsight[];
  improvements: CoachCardInsight[];
  score_delta: number | null;
  chat_only?: boolean;
}

export interface NextPracticeOption {
  kind: 'consolidate' | 'explore';
  scene_id: number;
  scene_name: string;
  label: string;
  reason: string;
}

export interface NextPracticeResponse {
  options: NextPracticeOption[];
}

// --- Session Summary (V1.1: radar_scores) ---
export interface SessionSummary {
  id: string;
  session_id: string;
  scene_name: string | null;
  duration_seconds: number;
  radar_scores: RadarScores;
  highlights: Highlight[];
  top_pronunciation_errors: PronunciationErrorItem[];
  top_grammar_errors: GrammarErrorItem[];
  practice_suggestions: PracticeSuggestion[];
  share_image_url: string | null;
  coach_card?: CoachCard | null;
  next_practice_options?: NextPracticeOption[];
  created_at: string;
}

// --- Progress Snapshot ---
export interface ProgressSnapshot {
  snapshot_date: string;
  total_score: number;
  dimension_scores: Record<string, number>;
  session_count: number;
  total_duration_seconds: number;
}

// --- Weakness Record ---
export interface WeaknessRecord {
  period_start: string;
  period_end: string;
  category: string;
  item: string;
  error_count: number;
  trend: string | null;
}

// --- User Progress ---
export interface ProgressProvenance {
  pronunciation: 'iflytek_ise' | 'text_analysis' | 'none';
  fluency: 'iflytek_ise' | 'text_analysis' | 'none';
  grammar: 'evaluation' | 'none';
  vocabulary: 'heuristic' | 'none';
  interaction: 'heuristic' | 'none';
  strengths: 'computed' | 'none';
}

export interface DimensionAvailable {
  pronunciation: boolean;
  fluency: boolean;
  grammar: boolean;
  vocabulary: boolean;
  interaction: boolean;
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
  data_provenance?: ProgressProvenance;
  dimension_available?: DimensionAvailable;
}

// --- Achievement (V1.1) ---
export interface AchievementInfo {
  id: string;
  title: string;
  description: string;
  current_progress: number;
  target: number;
  unlocked_at: string | null;
  icon_url: string | null;
  icon?: string | null;
}

export interface AchievementList {
  user_id: string;
  achievements: AchievementInfo[];
}

// --- Trend ---
export interface TrendPoint {
  date: string;
  score: number;
  dimension: string | null;
}

export interface ForecastPoint {
  date: string;
  score: number;
  confidence_interval_lower: number;
  confidence_interval_upper: number;
}

export interface ProgressTrend {
  dimension: string;
  granularity: string;
  data_points: TrendPoint[];
  forecast: ForecastPoint[];
}

export interface TrendParams {
  start_date: string;
  end_date: string;
  dimension?: string;
  granularity?: string;
  include_forecast?: boolean;
}

// --- Weakness Distribution (V1.1) ---
export interface WeaknessDistItem {
  category: string;
  item: string;
  error_count: number;
  trend: string | null;
  suggested_exercise_id: string | null;
}

export interface WeaknessDistResponse {
  user_id: string;
  period: string;
  weakness_matrix: WeaknessDistItem[];
}

export interface WeaknessDistParams {
  start_date: string;
  end_date: string;
  category?: string;
}

// --- Review Plan ---
export interface ReviewPlanItem {
  type: string;
  target: string;
  exercise_ids: string[];
  estimated_minutes: number;
}

export interface ReviewPlan {
  plan_id: string;
  generated_at: string;
  items: ReviewPlanItem[];
}

export const summaryApi = {
  getSessionSummary(sessionId: string) {
    return apiClient
      .get<SessionSummary>(`/sessions/${sessionId}/summary`)
      .then((res) => res.data);
  },

  getNextPractice(userId: string) {
    return apiClient
      .get<NextPracticeResponse>(`/users/${userId}/next-practice`)
      .then((res) => res.data);
  },

  getProgress(userId: string) {
    return apiClient
      .get<UserProgress>(`/users/${userId}/progress`)
      .then((res) => res.data);
  },

  getAchievements(userId: string) {
    return apiClient
      .get<AchievementList>(`/users/${userId}/achievements`)
      .then((res) => res.data);
  },

  getProgressTrend(userId: string, params: TrendParams) {
    return apiClient
      .get<ProgressTrend>(`/users/${userId}/progress/trend`, { params })
      .then((res) => res.data);
  },

  getWeaknessDistribution(userId: string, params: WeaknessDistParams) {
    return apiClient
      .get<WeaknessDistResponse>(`/users/${userId}/progress/weakness-distribution`, { params })
      .then((res) => res.data);
  },

  /** V1.1: Get personalized review plan */
  getReviewPlan(userId: string) {
    return apiClient
      .get<ReviewPlan>(`/users/${userId}/review-plan`)
      .then((res) => res.data);
  },
};
