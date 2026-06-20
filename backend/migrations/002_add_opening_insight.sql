-- Add opening_insight for light coach loop (session opening reminder)
ALTER TABLE session_summaries
    ADD COLUMN IF NOT EXISTS opening_insight TEXT;
