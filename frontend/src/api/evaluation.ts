import apiClient from './client';

// --- Phoneme Score ---
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

// --- Word Score ---
export interface WordScore {
  word: string;
  score: number;
  phonemes: PhonemeScore[] | null;
}

// --- Prosody ---
export interface Prosody {
  intonation_score: number | null;
  rhythm_score: number | null;
  stress_errors: Record<string, unknown>[] | null;
}

// --- Pronunciation Evaluate (V1.1) ---
export interface PronunciationEvaluateResult {
  overall_score: number;
  pronunciation_score: number | null;
  fluency_score: number | null;
  completeness_score: number | null;
  words: WordScore[] | null;
  prosody: Prosody | null;
  advice: string | null;
  reference_audio_url: string | null;
}

// --- Pronunciation Detail ---
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

// --- Grammar Correction ---
export interface GrammarErrorOut {
  utterance_id: string;
  original: string;
  error_type: string;
  error_span: Record<string, number>;
  correction: string;
  corrected_sentence: string | null;
  explanation: string | null;
  severity: string;
}

export interface GrammarCorrectResult {
  original: string;
  errors: GrammarErrorOut[];
  corrected_text: string | null;
  optimization_suggestions: Record<string, unknown>[];
}

export interface GrammarReportResult {
  session_id: string;
  errors: GrammarErrorOut[];
  optimization_suggestions: Record<string, unknown>[];
  total_errors: number;
  total_suggestions: number;
}

export const evaluationApi = {
  /** V1.1: Evaluate pronunciation for a single sentence */
  evaluatePronunciation(audio: File, referenceText: string, language = 'en-US', detailLevel = 'full') {
    const formData = new FormData();
    formData.append('audio', audio);
    formData.append('reference_text', referenceText);
    formData.append('language', language);
    formData.append('detail_level', detailLevel);
    return apiClient
      .post<PronunciationEvaluateResult>('/pronunciation/evaluate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000,
      })
      .then((res) => res.data);
  },

  getPronunciationDetail(sessionId: string, utteranceId: string) {
    return apiClient
      .get<PronunciationDetail>(`/sessions/${sessionId}/pronunciation/${utteranceId}`)
      .then((res) => res.data);
  },

  /** V1.1: Get grammar error report for a session */
  getGrammarReport(sessionId: string) {
    return apiClient
      .get<GrammarReportResult>(`/sessions/${sessionId}/grammar-report`)
      .then((res) => res.data);
  },

  /** V1.1: Instant grammar correction */
  correctGrammar(text: string, mode: 'light' | 'full' = 'full') {
    return apiClient
      .post<GrammarCorrectResult>('/grammar/correct', { text, mode })
      .then((res) => res.data);
  },
};
