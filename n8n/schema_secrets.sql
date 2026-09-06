-- ============================================================
-- DigestPapers secrets table (API keys / provider / model / webhook)
-- Separate from `config` so a UI read of config never leaks a key.
-- Run inside the n8n Postgres:
--   docker exec -i n8n-postgres-1 psql -U n8n -d n8n < schema_secrets.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS secrets (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed the known keys with empty/default values (edit from the dashboard).
--   SS_API_KEY       : Semantic Scholar API key (sent as x-api-key header)
--   LLM_PROVIDER     : "deepseek" | "openai"
--   LLM_BASE_URL     : chat/completions base, e.g. https://api.deepseek.com
--   LLM_API_KEY      : provider API key (Bearer)
--   LLM_MODEL        : model id, e.g. deepseek-chat / gpt-4o-mini
--   DISCORD_WEBHOOK  : full webhook URL
INSERT INTO secrets(key, value) VALUES
  ('SS_API_KEY',      ''),
  ('LLM_PROVIDER',    'deepseek'),
  ('LLM_BASE_URL',    'https://api.deepseek.com'),
  ('LLM_API_KEY',     ''),
  ('LLM_MODEL',       'deepseek-chat'),
  ('DISCORD_WEBHOOK', '')
ON CONFLICT (key) DO NOTHING;
