-- ============================================================
-- DigestPapers config table
-- Run once inside the n8n Postgres (docker):
--   docker exec -i <n8n_postgres_container> psql -U n8n -d n8n < schema.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS config (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed defaults ONLY if the row does not already exist.
-- These mirror the original "Load Config" node in DigestPapers_MultiSource.json.
INSERT INTO config(key, value) VALUES
  ('keywordQuery',
    '"explainable AI OR integrated gradients OR feature attribution OR model quantization OR post-training quantization OR neural network efficiency"'::jsonb),
  ('fields',
    '"title,abstract,tldr,authors,year,openAccessPdf,externalIds,url,publicationDate,venue"'::jsonb),
  ('KEYWORD_MIN_SCORE', '7'::jsonb),
  ('AUTHOR_MIN_SCORE',  '4'::jsonb),
  ('daysBack',          '400'::jsonb),
  ('venueWhitelist',
    '["ICML","NeurIPS","ICLR","AAAI","CVPR","EMNLP","ACL"]'::jsonb),
  ('orConfs',
    '["ICML","ICLR","NeurIPS"]'::jsonb),
  ('topics',
    '["xai","quant"]'::jsonb),
  ('authors',
    '[
      {"name": "Mukund Sundararajan", "topic": "xai", "arxiv_name": "Mukund Sundararajan", "ss_id": "30740726"},
      {"name": "Scott Lundberg", "topic": "xai", "arxiv_name": "Scott Lundberg", "ss_id": "23451726"},
      {"name": "Su-In Lee", "topic": "xai", "arxiv_name": "Su-In Lee", "ss_id": "2180463"},
      {"name": "Been Kim", "topic": "xai", "arxiv_name": "Been Kim", "ss_id": "2334601045"},
      {"name": "Andrei Kapishnikov", "topic": "xai", "arxiv_name": "Andrei Kapishnikov", "ss_id": "146100421"},
      {"name": "Ankur Taly", "topic": "xai", "arxiv_name": "Ankur Taly", "ss_id": "40511120"},
      {"name": "Dan Alistarh", "topic": "quant", "arxiv_name": "Dan Alistarh", "ss_id": "3311387"},
      {"name": "Elias Frantar", "topic": "quant", "arxiv_name": "Elias Frantar", "ss_id": "1502248377"},
      {"name": "Song Han", "topic": "quant", "arxiv_name": "Song Han", "ss_id": "143840275"},
      {"name": "Guangxuan Xiao", "topic": "quant", "arxiv_name": "Guangxuan Xiao", "ss_id": "2046958974"},
      {"name": "Tijmen Blankevoort", "topic": "quant", "arxiv_name": "Tijmen Blankevoort", "ss_id": "83133279"},
      {"name": "Markus Nagel", "topic": "quant", "arxiv_name": "Markus Nagel", "ss_id": "41229153"}
    ]'::jsonb)
ON CONFLICT (key) DO NOTHING;
