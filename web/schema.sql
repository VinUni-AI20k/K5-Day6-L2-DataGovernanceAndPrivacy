-- Append-only: every click is a row (audit trail). Resolution happens at read time.
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL,
  reviewer TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('reviewer','admin')),
  decision TEXT NOT NULL CHECK (decision IN ('approve','reject','edit','escalate','skip')),
  override_value TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_decisions_item ON decisions(item_id, id);
