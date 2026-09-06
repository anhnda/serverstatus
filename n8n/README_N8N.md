# DigestPapers — n8n Setup (from empty machine)

A daily paper digest pipeline. n8n runs the workflow, Postgres stores config +
seen papers, a small Flask app (`app.py`) serves a config dashboard at `/pconfig`,
and Cloudflare Tunnel exposes everything over HTTPS.

Everything below assumes a fresh Linux host (Ubuntu). Commands that touch secrets
use placeholders — never commit real values.

---

## 0. Architecture at a glance

```
                        Cloudflare Tunnel (cloudflared, on host)
                          │           │              │
             s1w.xaibk.org  n8n.xaibk.org      s1.xaibk.org
                  │              │                   │
             Flask :5000     n8n :5678            ssh :22
             (app.py,        (docker)
              /pconfig)          │
                  │              │
                  └──────► Postgres :5432 ◄──────┘
                         (docker, 127.0.0.1 only)
```

- **n8n** and **Postgres** run in Docker (compose stack).
- **Flask** (`app.py`) runs on the host, reaches Postgres via `127.0.0.1:5432`.
- **cloudflared** runs on the host and routes public hostnames to local ports.
- The n8n workflow reads all config + API keys from Postgres at runtime (nothing
  hardcoded), so the dashboard can change behaviour without editing the workflow.

---

## 1. Install Docker

```bash
# Docker Engine + compose plugin (Ubuntu)
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# let your user run docker without sudo (re-login afterwards)
sudo usermod -aG docker "$USER"
```

Verify:

```bash
docker --version
docker compose version
```

---

## 2. Project files

Put these in one folder, e.g. `~/n8n/`:

```
~/n8n/
├── docker-compose.yml                    # the stack (Postgres + n8n)
├── .env                                  # secrets (you create this — see below)
├── schema.sql                            # config table + seed
├── schema_secrets.sql                    # secrets table + seed
├── DigestPapers_MultiSource.patched.json # the workflow (import into n8n)
├── app.py                                # Flask config dashboard
├── templates/
│   └── pconfig.html                      # dashboard UI (Flask looks here)
└── n8n_LoadConfig.md                     # notes on how Load Config reads the DB
```

`docker-compose.yml`, `schema.sql`, `schema_secrets.sql`, `app.py`,
`pconfig.html`, and `DigestPapers_MultiSource.patched.json` are all in this
delivery. Move `pconfig.html` into a `templates/` subfolder next to `app.py`.

---

## 3. Create the `.env`

The compose file reads these variables. Create `~/n8n/.env` and fill each value
yourself — do not paste real secrets into any shared file.

```dotenv
# n8n
N8N_ENCRYPTION_KEY=          # 32+ random chars; openssl rand -hex 24
DOMAIN=                      # e.g. n8n.xaibk.org
GENERIC_TIMEZONE=            # e.g. Asia/Ho_Chi_Minh

# Postgres
POSTGRES_USER=               # e.g. n8n
POSTGRES_PASSWORD=           # choose a strong password
POSTGRES_DB=                 # e.g. n8n
```

Generate a good encryption key and password:

```bash
openssl rand -hex 24     # N8N_ENCRYPTION_KEY
openssl rand -base64 18  # POSTGRES_PASSWORD
```

> If you ever change `N8N_ENCRYPTION_KEY` after n8n has stored credentials, those
> credentials become unreadable. Set it once and keep it.

---

## 4. Start the stack

```bash
cd ~/n8n
docker compose up -d
docker compose ps        # both services should be "running"/"healthy"
```

Postgres is published on `127.0.0.1:5432` (localhost only), n8n on
`127.0.0.1:5678`. Neither is exposed to the internet directly — Cloudflare
Tunnel does that (step 8).

---

## 5. Create the database tables

The Postgres container name is usually `n8n-postgres-1` (check with
`docker ps`). Load both schema files — they are idempotent (`IF NOT EXISTS` +
`ON CONFLICT DO NOTHING`), so re-running them is safe.

```bash
# adjust the container name and -U/-d to match your .env values
docker exec -i n8n-postgres-1 psql -U n8n -d n8n < schema.sql
docker exec -i n8n-postgres-1 psql -U n8n -d n8n < schema_secrets.sql
```

This creates and seeds:

- **`config`** — operational settings the workflow reads (`keywordQuery`,
  `fields`, `daysBack`, score thresholds, `venueWhitelist`, `orConfs`, `topics`,
  `authors`). Seeded with the original defaults.
- **`secrets`** — API keys / provider / model / webhook (`SS_API_KEY`,
  `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `DISCORD_WEBHOOK`).
  Seeded empty (fill them from the dashboard in step 7).

### Tables the workflow itself needs

The workflow also uses two tables it does **not** create automatically:

- **`author_cache(name TEXT PRIMARY KEY, ss_id TEXT)`** — caches resolved
  Semantic Scholar author IDs.
- **`papers(...)`** — the "already sent to Discord" store, used for dedup.

Create them if they don't exist yet:

```bash
docker exec -i n8n-postgres-1 psql -U n8n -d n8n <<'SQL'
CREATE TABLE IF NOT EXISTS author_cache (
  name  TEXT PRIMARY KEY,
  ss_id TEXT
);

CREATE TABLE IF NOT EXISTS papers (
  dedup_key           TEXT PRIMARY KEY,
  arxiv_id            TEXT,
  doi                 TEXT,
  semantic_scholar_id TEXT,
  title               TEXT,
  authors             TEXT,
  abstract            TEXT,
  url                 TEXT,
  pdf_url             TEXT,
  published_at        DATE,
  venue               TEXT,
  relevance_score     NUMERIC,
  summary             TEXT,
  reason_relevant     TEXT,
  source              TEXT,
  status              TEXT,
  created_at          TIMESTAMPTZ DEFAULT now()
);
SQL
```

> If your existing `papers`/`author_cache` already have a different shape, keep
> yours — the workflow only relies on the columns it writes. The block above is
> just a safe default for a from-empty setup.

---

## 6. Import the workflow into n8n

1. Open n8n (via the tunnel once step 8 is done, or `http://127.0.0.1:5678`
   locally).
2. **Workflows → Import from File →** `DigestPapers_MultiSource.patched.json`.
3. Open the **Postgres account** credential and confirm it points at the stack
   Postgres: host `postgres`, port `5432`, database/user/password from your
   `.env`. (Inside the n8n container, the DB host is the service name
   `postgres`, not `localhost`.)
4. The head of the flow is
   **Schedule Trigger → Load Config (DB) → Load Config → …**; `Load Config (DB)`
   reads `config` + `secrets` in one query. See `n8n_LoadConfig.md` for details.
5. Leave the workflow **inactive** until you've set the keys (next step), then
   toggle **Active** — it runs daily at 06:00.

---

## 7. Run the Flask dashboard and set keys

The dashboard writes to the `config` and `secrets` tables; n8n picks up changes
on its next run.

```bash
# on the host, in ~/n8n
python3 -m venv .venv && source .venv/bin/activate
pip install flask flask-cors psutil psycopg2-binary
python3 app.py            # serves on 0.0.0.0:5000
```

Then open **`https://s1w.xaibk.org/pconfig`** (or `http://127.0.0.1:5000/pconfig`
locally) and:

1. Click **Connection**, enter Postgres info — Host `localhost`, Port `5432`,
   Database/User/Password from your `.env` — **Test**, then **Save & connect**.
   (Stored in your browser only.)
2. Under **API keys**: paste the Semantic Scholar key, choose the LLM provider
   (DeepSeek/OpenAI), paste the LLM key, click **Retrieve models**, pick a
   model, paste the Discord webhook, then **Save keys**.
3. Edit search settings, venues, topics, and the author list as needed, then
   **Save to database**.

> Run `app.py` under a process manager for production (systemd unit or
> `screen`/`tmux`), so it survives logout. Example systemd unit at the bottom.

---

## 8. Cloudflare Tunnel

`cloudflared` runs on the host and terminates TLS for all three hostnames.
Config lives at `/etc/cloudflared/config.yml`:

```yaml
tunnel: tunnels1
credentials-file: /home/anhnda/.cloudflared/<TUNNEL_ID>.json
protocol: http2
transport-protocol: http2
ingress:
  - hostname: s1.xaibk.org
    service: ssh://localhost:22
  - hostname: s1w.xaibk.org
    service: http://localhost:5000     # Flask dashboard
  - hostname: n8n.xaibk.org
    service: http://localhost:5678     # n8n
  - service: http_status:404
```

Install and run:

```bash
# install cloudflared (Ubuntu)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# (one-time) authenticate + create the tunnel if not already done
cloudflared tunnel login
cloudflared tunnel create tunnels1
# add DNS routes for each hostname
cloudflared tunnel route dns tunnels1 s1w.xaibk.org
cloudflared tunnel route dns tunnels1 n8n.xaibk.org

# run as a service using the config above
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

n8n's compose already sets `N8N_HOST`, `N8N_PROTOCOL=https`, `N8N_PROXY_HOPS=1`,
and SSE push so it works correctly behind Cloudflare.

---

## 9. First run + resets

Trigger the workflow manually once (open it, **Execute Workflow**) to confirm
Discord receives messages.

Handy maintenance queries (container `n8n-postgres-1`, db `n8n`):

```bash
# see what's stored as "already sent"
docker exec -it n8n-postgres-1 psql -U n8n -d n8n \
  -c "SELECT count(*), left(dedup_key,7) src FROM papers GROUP BY 2 ORDER BY 1 DESC;"

# reset the digest so old papers can appear again (does NOT touch author_cache)
docker exec -it n8n-postgres-1 psql -U n8n -d n8n -c "TRUNCATE papers;"

# inspect current config / secrets keys
docker exec -it n8n-postgres-1 psql -U n8n -d n8n -c "SELECT key FROM config ORDER BY key;"
docker exec -it n8n-postgres-1 psql -U n8n -d n8n -c "SELECT key, (value <> '') AS is_set FROM secrets ORDER BY key;"
```

---

## 10. How the pipeline behaves (quick reference)

- Sources: arXiv keyword, Semantic Scholar keyword, SS author papers, arXiv
  author, OpenReview — merged and de-duplicated.
- **Dedup vs DB**: papers already in `papers` (already sent to Discord) are
  dropped, so each run only surfaces new ones.
- **Freshness**: papers with a valid `published_at` inside `daysBack` rank first;
  undated/older papers are kept but only fill a topic when there aren't enough
  fresh ones (so Discord is never empty for a topic that has any candidates).
- **Selection**: top 5 per topic (`xai`, `quant`), followed-authors preferred,
  then by relevance score.
- **Storage**: only the papers actually sent to Discord are written to `papers`.
- **Keys/config**: read live from Postgres each run — edit via the dashboard, no
  workflow edits or n8n restart needed.

---

## Appendix — systemd unit for the Flask dashboard

`/etc/systemd/system/pconfig.service`:

```ini
[Unit]
Description=DigestPapers config dashboard (Flask)
After=network.target docker.service

[Service]
User=anhnda
WorkingDirectory=/home/anhnda/n8n
ExecStart=/home/anhnda/n8n/.venv/bin/python3 /home/anhnda/n8n/app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pconfig
```

---

## Files in this delivery

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Postgres + n8n stack; both bound to `127.0.0.1` |
| `schema.sql` | Creates + seeds the `config` table |
| `schema_secrets.sql` | Creates + seeds the `secrets` table |
| `DigestPapers_MultiSource.patched.json` | The n8n workflow (reads config/keys from DB) |
| `app.py` | Flask dashboard: `/pconfig`, `/api/config`, `/api/secrets`, `/api/llm/models` |
| `pconfig.html` | Dashboard UI (put in `templates/`) |
| `n8n_LoadConfig.md` | Notes on the Load Config nodes |
| `README_N8N.md` | This file |
