-- AiSpeakMate Database Schema V1.0
-- PostgreSQL

-- ============================================
-- 1. 扩展
-- ============================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================
-- 2. 用户表
-- ============================================
CREATE TABLE users (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(50)     NOT NULL UNIQUE,
    email           VARCHAR(100)    NOT NULL UNIQUE,
    password_hash   VARCHAR(255)    NOT NULL,
    native_language VARCHAR(10)     NOT NULL DEFAULT 'zh',
    learning_language VARCHAR(10)   NOT NULL DEFAULT 'en',
    level           VARCHAR(20)     NOT NULL DEFAULT 'beginner',
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_username ON users (username);

-- ============================================
-- 3. 场景分类表
-- ============================================
CREATE TABLE scene_categories (
    id          SERIAL          PRIMARY KEY,
    name        VARCHAR(50)     NOT NULL,
    icon_url    TEXT,
    sort_order  INT             NOT NULL DEFAULT 0
);

-- ============================================
-- 4. 预设场景表
-- ============================================
CREATE TABLE scenes (
    id                  SERIAL          PRIMARY KEY,
    category_id         INT             NOT NULL REFERENCES scene_categories(id),
    name                VARCHAR(100)    NOT NULL,
    description         TEXT,
    thumbnail_url       TEXT,
    role_prompt         TEXT            NOT NULL,
    opening_line        TEXT            NOT NULL,
    difficulty_levels   JSONB           NOT NULL DEFAULT '["beginner","intermediate","advanced"]',
    difficulty_settings JSONB,
    tags                JSONB,
    suggested_duration  INT             NOT NULL DEFAULT 300,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scenes_category ON scenes (category_id);

-- ============================================
-- 5. 场景词库表
-- ============================================
CREATE TABLE scene_vocabulary (
    id              SERIAL          PRIMARY KEY,
    scene_id        INT             NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    word            VARCHAR(100)    NOT NULL,
    phonetic        VARCHAR(100),
    translation     VARCHAR(200),
    audio_url       TEXT,
    part_of_speech  VARCHAR(20)
);

CREATE INDEX idx_vocab_scene ON scene_vocabulary (scene_id);

-- ============================================
-- 6. 场景句型表
-- ============================================
CREATE TABLE scene_sentence_patterns (
    id          SERIAL  PRIMARY KEY,
    scene_id    INT     NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    pattern     TEXT    NOT NULL,
    translation TEXT,
    example     TEXT
);

-- ============================================
-- 7. 自定义场景表
-- ============================================
CREATE TABLE custom_scenes (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(100)    NOT NULL,
    topic           TEXT,
    role            VARCHAR(50),
    difficulty      VARCHAR(20),
    focus_grammar   JSONB,
    focus_vocab     JSONB,
    prompt_snapshot TEXT,
    is_temporary    BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- ============================================
-- 8. 练习会话表
-- ============================================
CREATE TABLE sessions (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scene_id        INT             REFERENCES scenes(id),
    custom_scene_id UUID            REFERENCES custom_scenes(id),
    difficulty      VARCHAR(20)     NOT NULL,
    status          VARCHAR(20)     NOT NULL DEFAULT 'active',
    started_at      TIMESTAMP       NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMP,
    duration_seconds INT
);

CREATE INDEX idx_sessions_user ON sessions (user_id, started_at DESC);
CREATE INDEX idx_sessions_status ON sessions (status);

-- ============================================
-- 9. 对话语句表
-- ============================================
CREATE TABLE utterances (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID            NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    speaker         VARCHAR(10)     NOT NULL CHECK (speaker IN ('user', 'ai')),
    text            TEXT            NOT NULL,
    asr_confidence  FLOAT,
    audio_url       TEXT,
    tts_audio_url   TEXT,
    sequence        INT             NOT NULL,
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_utterances_session ON utterances (session_id, sequence);

-- ============================================
-- 10. 句子级发音评测表
-- ============================================
CREATE TABLE pronunciation_evaluations (
    id                  UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    utterance_id        UUID            NOT NULL REFERENCES utterances(id) ON DELETE CASCADE UNIQUE,
    overall_score       SMALLINT        NOT NULL CHECK (overall_score >= 0 AND overall_score <= 100),
    pronunciation_score SMALLINT        CHECK (pronunciation_score >= 0 AND pronunciation_score <= 100),
    fluency_score       SMALLINT        CHECK (fluency_score >= 0 AND fluency_score <= 100),
    completeness_score  SMALLINT        CHECK (completeness_score >= 0 AND completeness_score <= 100),
    prosody_score       SMALLINT        CHECK (prosody_score >= 0 AND prosody_score <= 100),
    advice              TEXT,
    detail_json         JSONB,
    evaluated_at        TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pron_eval_utterance ON pronunciation_evaluations (utterance_id);

-- ============================================
-- 11. 音素级得分表
-- ============================================
CREATE TABLE phoneme_scores (
    id                  BIGSERIAL       PRIMARY KEY,
    evaluation_id       UUID            NOT NULL REFERENCES pronunciation_evaluations(id) ON DELETE CASCADE,
    word                VARCHAR(100)    NOT NULL,
    word_score          SMALLINT        CHECK (word_score >= 0 AND word_score <= 100),
    phoneme             VARCHAR(10)     NOT NULL,
    phoneme_score       SMALLINT        NOT NULL CHECK (phoneme_score >= 0 AND phoneme_score <= 100),
    is_error            BOOLEAN         NOT NULL DEFAULT FALSE,
    suggested_phoneme   VARCHAR(10),
    start_time_ms       INT,
    end_time_ms         INT
);

CREATE INDEX idx_phoneme_evaluation ON phoneme_scores (evaluation_id);
CREATE INDEX idx_phoneme_error ON phoneme_scores (evaluation_id, is_error) WHERE is_error = TRUE;

-- ============================================
-- 12. 语法错误记录表
-- ============================================
CREATE TABLE grammar_errors (
    id                  BIGSERIAL       PRIMARY KEY,
    utterance_id        UUID            NOT NULL REFERENCES utterances(id) ON DELETE CASCADE,
    error_type          VARCHAR(50)     NOT NULL,
    error_span_start    INT             NOT NULL,
    error_span_end      INT             NOT NULL,
    original_text       TEXT            NOT NULL,
    correction          TEXT            NOT NULL,
    corrected_sentence  TEXT,
    explanation         TEXT,
    severity            VARCHAR(20)     NOT NULL DEFAULT 'medium',
    is_expression_issue BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_grammar_utterance ON grammar_errors (utterance_id);

-- ============================================
-- 13. 会话综合总结表
-- ============================================
CREATE TABLE session_summaries (
    id                      UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id              UUID            NOT NULL REFERENCES sessions(id) ON DELETE CASCADE UNIQUE,
    radar_fluency           SMALLINT        CHECK (radar_fluency >= 0 AND radar_fluency <= 100),
    radar_vocabulary        SMALLINT        CHECK (radar_vocabulary >= 0 AND radar_vocabulary <= 100),
    radar_grammar           SMALLINT        CHECK (radar_grammar >= 0 AND radar_grammar <= 100),
    radar_pronunciation     SMALLINT        CHECK (radar_pronunciation >= 0 AND radar_pronunciation <= 100),
    radar_interaction       SMALLINT        CHECK (radar_interaction >= 0 AND radar_interaction <= 100),
    highlights              JSONB,
    practice_suggestions    JSONB,
    share_image_url         TEXT,
    created_at              TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_summary_session ON session_summaries (session_id);

-- ============================================
-- 14. 用户能力快照表
-- ============================================
CREATE TABLE user_progress_snapshots (
    id                      BIGSERIAL       PRIMARY KEY,
    user_id                 UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot_date           DATE            NOT NULL,
    total_score             SMALLINT        NOT NULL CHECK (total_score >= 0 AND total_score <= 100),
    dimension_scores        JSONB           NOT NULL,
    session_count           INT             NOT NULL DEFAULT 0,
    total_duration_seconds  INT             NOT NULL DEFAULT 0
);

CREATE INDEX idx_progress_user_date ON user_progress_snapshots (user_id, snapshot_date DESC);
CREATE UNIQUE INDEX uq_progress_user_date ON user_progress_snapshots (user_id, snapshot_date);

-- ============================================
-- 15. 弱点分布汇总表
-- ============================================
CREATE TABLE user_weakness_records (
    id              BIGSERIAL       PRIMARY KEY,
    user_id         UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period_start    DATE            NOT NULL,
    period_end      DATE            NOT NULL,
    category        VARCHAR(50)     NOT NULL CHECK (category IN ('pronunciation', 'grammar')),
    item            VARCHAR(100)    NOT NULL,
    error_count     INT             NOT NULL,
    trend           VARCHAR(20)     CHECK (trend IN ('improving', 'stable', 'worsening'))
);

CREATE INDEX idx_weakness_user_period ON user_weakness_records (user_id, period_end DESC);
CREATE UNIQUE INDEX uq_weakness_record ON user_weakness_records (user_id, period_start, period_end, category, item);

-- ============================================
-- 16. 成就定义表
-- ============================================
CREATE TABLE achievements (
    id              SERIAL          PRIMARY KEY,
    title           VARCHAR(100)    NOT NULL,
    description     TEXT,
    icon_url        TEXT,
    condition_type  VARCHAR(50)     NOT NULL,
    condition_value INT             NOT NULL
);

-- ============================================
-- 17. 用户成就关联表
-- ============================================
CREATE TABLE user_achievements (
    id              BIGSERIAL       PRIMARY KEY,
    user_id         UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    achievement_id  INT             NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
    achievement_key VARCHAR(50)     NOT NULL DEFAULT '',
    unlocked_at     TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_user_achievement ON user_achievements (user_id, achievement_id);
CREATE INDEX idx_user_achievements ON user_achievements (user_id);

-- ============================================
-- 18. 种子数据：场景分类
-- ============================================
INSERT INTO scene_categories (name, icon_url, sort_order) VALUES
    ('日常生活', NULL, 1),
    ('职场商务', NULL, 2),
    ('旅行出行', NULL, 3),
    ('社交交际', NULL, 4),
    ('学术教育', NULL, 5),
    ('面试求职', NULL, 6),
    ('餐饮美食', NULL, 7),
    ('医疗健康', NULL, 8);

-- ============================================
-- 19. 种子数据：示例场景
-- ============================================
INSERT INTO scenes (category_id, name, description, role_prompt, opening_line, difficulty_levels, tags) VALUES
    (3, '餐厅点餐', '练习在餐厅点餐的常用对话', '你是一位餐厅服务员，语气亲切耐心', '欢迎光临！请问您需要点什么？', '["beginner","intermediate","advanced"]', '["food","restaurant"]'),
    (3, '酒店入住', '练习酒店入住登记的对话', '你是酒店前台接待员，礼貌专业', '您好！请问有预订吗？', '["beginner","intermediate","advanced"]', '["travel","hotel"]'),
    (2, '商务会议', '模拟商务会议场景', '你是会议主持人，正式但友好', '欢迎各位参加今天的会议，我们开始吧', '["intermediate","advanced"]', '["business","meeting"]'),
    (2, '电话沟通', '练习商务电话英语', '你是对方公司代表，直接高效', 'Hello, this is ABC Company. How can I help you?', '["beginner","intermediate","advanced"]', '["business","phone"]'),
    (5, '课堂讨论', '模拟课堂讨论互动', '你是大学教授，鼓励学生发表观点', 'Today we will discuss the topic of climate change', '["intermediate","advanced"]', '["academic","discussion"]'),
    (6, '英语面试', '模拟英语求职面试', '你是HR面试官，专业但不失亲切', 'Please tell me about yourself', '["intermediate","advanced"]', '["interview","job"]');