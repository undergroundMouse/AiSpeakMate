import apiClient from './client';

export interface PhonemeScore {
  word: string;
  word_score: number | null;
  phoneme: string;
  phoneme_score: number;
  is_error: boolean;
  suggested_phoneme: string | null;
  start_time_ms: number | null;
  end_time_ms: number | null;
}

export interface WordScore {
  word: string;
  score: number;
  phonemes: PhonemeScore[] | null;
}

export interface Prosody {
  intonation_score: number | null;
  rhythm_score: number | null;
  stress_errors: Record<string, unknown>[] | null;
}

export interface PronunciationDetail {
  utterance_id: string;
  overall_score: number;
  pronunciation_score: number | null;
  fluency_score: number | null;
  completeness_score: number | null;
  words: WordScore[] | null;
  prosody: Prosody | null;
  advice: string | null;
  evaluated_at: string | null;
}

export const evaluationApi = {
  getPronunciationDetail(sessionId: string, utteranceId: string) {
    return apiClient
      .get<PronunciationDetail>(`/sessions/${sessionId}/pronunciation/${utteranceId}`)
      .then((res) => res.data);
  },
};
