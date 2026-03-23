-- ハートビート用: エージェントの最終活動時刻
ALTER TABLE agents ADD COLUMN last_seen TIMESTAMPTZ;

-- レビュー割り当ての処理状態
ALTER TABLE review_assignments ADD COLUMN status TEXT DEFAULT 'pending'
  CHECK (status IN ('pending', 'completed'));

-- 管理者からの停止シグナル用
CREATE TABLE conference_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 初期値: 'active'（デーモン稼働可能）
INSERT INTO conference_config (key, value) VALUES ('status', 'active');

ALTER TABLE conference_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all for conference_config" ON conference_config FOR ALL USING (true);
