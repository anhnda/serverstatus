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
      {"name":"Mukund Sundararajan","topic":"xai","arxiv_name":"Sundararajan_M","ss_id":""},
      {"name":"Scott Lundberg","topic":"xai","arxiv_name":"Lundberg_S","ss_id":""},
      {"name":"Su-In Lee","topic":"xai","arxiv_name":"Lee_S","ss_id":""},
      {"name":"Been Kim","topic":"xai","arxiv_name":"Kim_B","ss_id":""},
      {"name":"Andrei Kapishnikov","topic":"xai","arxiv_name":"Kapishnikov_A","ss_id":""},
      {"name":"Ankur Taly","topic":"xai","arxiv_name":"Taly_A","ss_id":""},
      {"name":"Ruigang Yang","topic":"xai","arxiv_name":"Yang_R","ss_id":""},
      {"name":"Pascal Sturmfels","topic":"xai","arxiv_name":"Sturmfels_P","ss_id":""},
      {"name":"Dan Alistarh","topic":"quant","arxiv_name":"Alistarh_D","ss_id":""},
      {"name":"Elias Frantar","topic":"quant","arxiv_name":"Frantar_E","ss_id":""},
      {"name":"Song Han","topic":"quant","arxiv_name":"Han_S","ss_id":""},
      {"name":"Guangxuan Xiao","topic":"quant","arxiv_name":"Xiao_G","ss_id":""},
      {"name":"Tijmen Blankevoort","topic":"quant","arxiv_name":"Blankevoort_T","ss_id":""},
      {"name":"Markus Nagel","topic":"quant","arxiv_name":"Nagel_M","ss_id":""},
      {"name":"Christopher De Sa","topic":"quant","arxiv_name":"De_Sa_C","ss_id":""},
      {"name":"Hyun Oh Song","topic":"quant","arxiv_name":"Song_H","ss_id":""}
    ]'::jsonb)
ON CONFLICT (key) DO NOTHING;
