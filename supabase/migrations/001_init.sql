-- CPC-MS Conference: Database Schema
-- Implements the data model for the AI Scientist Conference

-- Agents (scientists / AI agents participating in the conference)
CREATE TABLE agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT UNIQUE NOT NULL,
  expertise TEXT NOT NULL,  -- θ^k description (kept for display; actual model is local)
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Topics (research targets d)
CREATE TABLE topics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Rounds (iterations of the CPC cycle per topic)
CREATE TABLE rounds (
  id SERIAL PRIMARY KEY,
  topic_id UUID REFERENCES topics(id) NOT NULL,
  phase TEXT CHECK (phase IN ('submission', 'review', 'judgment', 'completed')) DEFAULT 'submission',
  started_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);

-- Papers (w in CPC-MS: external representations / global scientific representations)
CREATE TABLE papers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID REFERENCES agents(id) NOT NULL,
  topic_id UUID REFERENCES topics(id) NOT NULL,
  round_id INT REFERENCES rounds(id) NOT NULL,
  title TEXT NOT NULL,
  abstract TEXT,
  content TEXT NOT NULL,  -- full markdown content
  submitted_at TIMESTAMPTZ DEFAULT now()
);

-- Reviews (reviewer k' evaluates paper w)
-- score represents p(z^{k'}|w): compatibility with reviewer's world model
CREATE TABLE reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id UUID REFERENCES papers(id) NOT NULL,
  reviewer_id UUID REFERENCES agents(id) NOT NULL,
  round_id INT REFERENCES rounds(id) NOT NULL,
  score FLOAT CHECK (score > 0 AND score <= 1) NOT NULL,
  feedback TEXT,
  submitted_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (paper_id, reviewer_id, round_id)  -- one review per reviewer per paper per round
);

-- Review assignments (which reviewers are assigned to which papers)
CREATE TABLE review_assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reviewer_id UUID REFERENCES agents(id) NOT NULL,
  paper_id UUID REFERENCES papers(id) NOT NULL,
  round_id INT REFERENCES rounds(id) NOT NULL,
  current_paper_id UUID REFERENCES papers(id),  -- w_current to also review (NULL if first round)
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (reviewer_id, paper_id, round_id)
);

-- MH Events (full audit trail of every Metropolis-Hastings acceptance decision)
CREATE TABLE mh_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id UUID REFERENCES topics(id) NOT NULL,
  round_id INT REFERENCES rounds(id) NOT NULL,
  paper_new_id UUID REFERENCES papers(id) NOT NULL,
  paper_current_id UUID REFERENCES papers(id),  -- NULL for first proposal in first round
  score_new_agg FLOAT NOT NULL,       -- Σ log(score_new_i)
  score_current_agg FLOAT,            -- Σ log(score_current_i), NULL if first
  alpha FLOAT NOT NULL,               -- min(1, exp(score_new_agg - score_current_agg))
  u_draw FLOAT NOT NULL,              -- uniform random draw
  accepted BOOLEAN NOT NULL,          -- u_draw < alpha
  chain_order INT NOT NULL,           -- position in the sequential chain
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Accepted Papers (w_current per topic: the current "consensus" paper)
CREATE TABLE accepted_papers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id UUID REFERENCES topics(id) NOT NULL,
  paper_id UUID REFERENCES papers(id) NOT NULL,
  round_id INT REFERENCES rounds(id) NOT NULL,
  accepted_at TIMESTAMPTZ DEFAULT now()
);

-- Row Level Security: allow all operations with anon key for camp setting
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE rounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE mh_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE accepted_papers ENABLE ROW LEVEL SECURITY;

-- Permissive policies for camp use (all authenticated + anon can read/write)
CREATE POLICY "Allow all for agents" ON agents FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for topics" ON topics FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for rounds" ON rounds FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for papers" ON papers FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for reviews" ON reviews FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for review_assignments" ON review_assignments FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for mh_events" ON mh_events FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for accepted_papers" ON accepted_papers FOR ALL USING (true) WITH CHECK (true);

-- Useful views
CREATE VIEW conference_state AS
SELECT
  r.id AS round_id,
  r.phase,
  r.started_at,
  r.completed_at,
  t.id AS topic_id,
  t.name AS topic_name,
  t.description AS topic_description,
  (SELECT COUNT(*) FROM papers p WHERE p.round_id = r.id) AS paper_count,
  (SELECT COUNT(*) FROM reviews rv WHERE rv.round_id = r.id) AS review_count
FROM rounds r
JOIN topics t ON r.topic_id = t.id
ORDER BY r.id DESC;
