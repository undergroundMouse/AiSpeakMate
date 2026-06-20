-- Add session mode for immersive vs practice dual-path
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS mode VARCHAR(20) NOT NULL DEFAULT 'practice';
