-- Migration: Remove rounds concept
-- Papers are now individual MH steps. Submission triggers review + MHNG.

-- Drop the conference_state view first (depends on rounds)
DROP VIEW IF EXISTS conference_state;

-- Remove round_id from all tables
ALTER TABLE papers DROP COLUMN IF EXISTS round_id;
ALTER TABLE reviews DROP COLUMN IF EXISTS round_id;
ALTER TABLE review_assignments DROP COLUMN IF EXISTS round_id;
ALTER TABLE mh_events DROP COLUMN IF EXISTS round_id;
ALTER TABLE accepted_papers DROP COLUMN IF EXISTS round_id;

-- Drop unique constraint on reviews that included round_id, recreate without it
ALTER TABLE reviews DROP CONSTRAINT IF EXISTS reviews_paper_id_reviewer_id_round_id_key;
ALTER TABLE reviews ADD CONSTRAINT reviews_paper_id_reviewer_id_key UNIQUE (paper_id, reviewer_id);

-- Drop unique constraint on review_assignments that included round_id
ALTER TABLE review_assignments DROP CONSTRAINT IF EXISTS review_assignments_reviewer_id_paper_id_round_id_key;
ALTER TABLE review_assignments ADD CONSTRAINT review_assignments_reviewer_id_paper_id_key UNIQUE (reviewer_id, paper_id);

-- Drop rounds table
DROP TABLE IF EXISTS rounds;

-- Add status to papers to track the MH step lifecycle
-- 'pending' = submitted, awaiting review
-- 'reviewing' = reviews in progress
-- 'judged' = MHNG has run
ALTER TABLE papers ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'
  CHECK (status IN ('pending', 'reviewing', 'judged'));

-- Make chain_order globally unique per topic (sequential MH step number)
-- (no change needed, already works as intended)
