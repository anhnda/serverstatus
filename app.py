from flask import Flask, render_template, jsonify, request
import psutil
import subprocess
import json
import urllib.request
import urllib.error

import psycopg2
import psycopg2.extras

from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # allow all origins


def get_gpu_stats():
    try:
        output = subprocess.check_output([
            'nvidia-smi',
            '--query-gpu=utilization.gpu,fan.speed,temperature.gpu,memory.total,memory.used',
            '--format=csv,noheader,nounits'
        ]).decode('utf-8').strip()

        if not output or ',' not in output:
            return 0, 0, 0, 0, 0

        usage, fan, temp, mem_total, mem_used = output.split(', ')
        return int(usage), int(fan), int(temp), int(mem_total), int(mem_used)
    except Exception:
        return 0, 0, 0, 0, 0


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/monitor')
def monitor():
    return render_template('dashboard.html')


@app.route('/stats')
def stats():
    cpu_usage = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    mem_usage = memory.percent
    mem_total = memory.total // (1024 * 1024)  # MB

    temps = psutil.sensors_temperatures()
    cpu_temp = temps['coretemp'][0].current if 'coretemp' in temps and temps['coretemp'] else 0

    fans = psutil.sensors_fans()
    fan_speed = 0
    if fans:
        for fan_list in fans.values():
            for fan in fan_list:
                if hasattr(fan, 'current') and fan.current > 0:
                    fan_speed = fan.current
                    break

    gpu_usage, gpu_fan, gpu_temp, gpu_mem_total, gpu_mem_used = get_gpu_stats()
    gpu_mem_usage = (gpu_mem_used / gpu_mem_total * 100) if gpu_mem_total > 0 else 0

    return jsonify({
        'cpu': cpu_usage,
        'memory': mem_usage,
        'memory_total': mem_total,
        'cpu_fan': fan_speed if fan_speed > 0 else "Firmware-controlled or not reporting",
        'cpu_temp': cpu_temp,
        'gpu': gpu_usage,
        'gpu_fan': gpu_fan,
        'gpu_temp': gpu_temp,
        'gpu_memory_usage': gpu_mem_usage,
        'gpu_memory_total': gpu_mem_total
    })


# ============================================================
# n8n / DigestPapers config editor
# ============================================================
#
# The frontend (pconfig.html) collects Postgres connection info in a popup,
# caches it in localStorage, and sends it on every request via X-PG-* headers.
# Nothing is hardcoded here. The app just proxies read/write to the `config`
# table (see schema.sql).

# Schema for validating incoming config. Order = order rendered by frontend.
CONFIG_SCHEMA = {
    'keywordQuery':      'string',
    'fields':            'string',
    'KEYWORD_MIN_SCORE': 'int',
    'AUTHOR_MIN_SCORE':  'int',
    'daysBack':          'int',
    'venueWhitelist':    'list_str',   # add/remove rows
    'orConfs':           'list_str',   # add/remove rows
    'topics':            'list_str',   # add/remove rows (author topic droplist)
    'authors':           'list_author',  # add/remove rows + edit
}

# Defaults mirror the original "Load Config" node — used to seed if a key is
# missing, so /api/config never returns a half-empty form.
DEFAULTS = {
    'keywordQuery': ("explainable AI OR integrated gradients OR feature attribution "
                     "OR model quantization OR post-training quantization OR neural network efficiency"),
    'fields': "title,abstract,authors,year,openAccessPdf,externalIds,url,publicationDate,venue",
    'KEYWORD_MIN_SCORE': 7,
    'AUTHOR_MIN_SCORE': 4,
    'daysBack': 400,
    'venueWhitelist': ["ICML", "NeurIPS", "ICLR", "AAAI", "CVPR", "EMNLP", "ACL"],
    'orConfs': ["ICML", "ICLR", "NeurIPS"],
    'topics': ["xai", "quant"],
    'authors': [],
}


def _pg_conn():
    """Build a psycopg2 connection from X-PG-* request headers."""
    h = request.headers
    host = h.get('X-PG-Host')
    port = h.get('X-PG-Port', '5432')
    db = h.get('X-PG-Db')
    user = h.get('X-PG-User')
    pwd = h.get('X-PG-Pass', '')
    if not (host and db and user):
        raise ValueError("Missing Postgres connection info (host/db/user).")
    return psycopg2.connect(
        host=host, port=int(port), dbname=db, user=user, password=pwd,
        connect_timeout=5,
    )


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
          key        TEXT PRIMARY KEY,
          value      JSONB NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)


def _validate(cfg):
    """Return (clean_dict, error_str_or_None)."""
    clean = {}
    for key, kind in CONFIG_SCHEMA.items():
        if key not in cfg:
            clean[key] = DEFAULTS[key]
            continue
        v = cfg[key]
        try:
            if kind == 'string':
                clean[key] = str(v)
            elif kind == 'int':
                clean[key] = int(v)
            elif kind == 'list_str':
                if not isinstance(v, list):
                    return None, f"{key} must be a list"
                clean[key] = [str(x).strip() for x in v if str(x).strip() != ""]
            elif kind == 'list_author':
                if not isinstance(v, list):
                    return None, f"{key} must be a list"
                rows = []
                for a in v:
                    if not isinstance(a, dict):
                        return None, "each author must be an object"
                    name = str(a.get('name', '')).strip()
                    if not name:
                        continue  # skip empty rows silently
                    rows.append({
                        'name': name,
                        'topic': str(a.get('topic', '')).strip(),
                        'arxiv_name': str(a.get('arxiv_name', '')).strip(),
                        'ss_id': str(a.get('ss_id', '')).strip(),
                    })
                clean[key] = rows
        except (ValueError, TypeError) as e:
            return None, f"{key}: {e}"
    return clean, None


@app.route('/pconfig')
def pconfig():
    return render_template('pconfig.html')


@app.route('/api/config', methods=['GET'])
def api_config_get():
    """Read all config rows. Missing keys fall back to DEFAULTS."""
    try:
        conn = _pg_conn()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f"DB connect failed: {e}"}), 502

    try:
        with conn, conn.cursor() as cur:
            _ensure_table(cur)
            cur.execute("SELECT key, value FROM config;")
            rows = {k: v for k, v in cur.fetchall()}
        out = {}
        for key in CONFIG_SCHEMA:
            out[key] = rows[key] if key in rows else DEFAULTS[key]
        return jsonify(out)
    except Exception as e:
        return jsonify({'error': f"Read failed: {e}"}), 500
    finally:
        conn.close()


@app.route('/api/config', methods=['POST'])
def api_config_post():
    """Upsert all config keys in one transaction."""
    payload = request.get_json(silent=True) or {}
    clean, err = _validate(payload)
    if err:
        return jsonify({'error': err}), 400

    try:
        conn = _pg_conn()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f"DB connect failed: {e}"}), 502

    try:
        with conn, conn.cursor() as cur:
            _ensure_table(cur)
            for key, val in clean.items():
                cur.execute(
                    """INSERT INTO config(key, value, updated_at)
                       VALUES (%s, %s, now())
                       ON CONFLICT (key)
                       DO UPDATE SET value = EXCLUDED.value, updated_at = now();""",
                    (key, json.dumps(val)),
                )
        return jsonify({'ok': True, 'saved': list(clean.keys())})
    except Exception as e:
        return jsonify({'error': f"Write failed: {e}"}), 500
    finally:
        conn.close()


@app.route('/api/config/test', methods=['GET'])
def api_config_test():
    """Ping the DB with the supplied connection info — used by the popup."""
    try:
        conn = _pg_conn()
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': f"Connect failed: {e}"}), 502
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        conn.close()


# ============================================================
# secrets (API keys / provider / model / webhook)
# ============================================================
#
# Stored in a separate `secrets` table (see schema_secrets.sql). n8n reads
# these at runtime via Load Config, so editing here overwrites what the
# workflow uses on its next run — no n8n restart, no hardcoded keys.

# Which keys hold a real secret (masked on GET) vs. plain settings (shown).
SECRET_KEYS = {'SS_API_KEY', 'LLM_API_KEY', 'DISCORD_WEBHOOK'}
SETTING_KEYS = {'LLM_PROVIDER', 'LLM_BASE_URL', 'LLM_MODEL'}
ALL_SECRET_ROWS = SECRET_KEYS | SETTING_KEYS

# Known providers -> default base URL + models list endpoint.
PROVIDERS = {
    'deepseek': {'base': 'https://api.deepseek.com', 'models': 'https://api.deepseek.com/models'},
    'openai':   {'base': 'https://api.openai.com/v1', 'models': 'https://api.openai.com/v1/models'},
}


def _mask(val):
    """Show only the tail of a secret so the UI can confirm it's set."""
    if not val:
        return ''
    if len(val) <= 8:
        return '••••'
    return '••••' + val[-4:]


def _ensure_secrets_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS secrets (
          key        TEXT PRIMARY KEY,
          value      TEXT NOT NULL DEFAULT '',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)


@app.route('/api/secrets', methods=['GET'])
def api_secrets_get():
    """Return settings in clear, secrets masked (+ an 'is_set' flag)."""
    try:
        conn = _pg_conn()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f"DB connect failed: {e}"}), 502
    try:
        with conn, conn.cursor() as cur:
            _ensure_secrets_table(cur)
            cur.execute("SELECT key, value FROM secrets;")
            rows = {k: v for k, v in cur.fetchall()}
        out = {}
        for key in ALL_SECRET_ROWS:
            v = rows.get(key, '')
            if key in SECRET_KEYS:
                out[key] = {'is_set': bool(v), 'masked': _mask(v)}
            else:
                out[key] = v
        return jsonify(out)
    except Exception as e:
        return jsonify({'error': f"Read failed: {e}"}), 500
    finally:
        conn.close()


@app.route('/api/secrets', methods=['POST'])
def api_secrets_post():
    """Overwrite secrets. A secret key is only written when a non-empty value
    is sent — an empty string means 'leave the stored key unchanged', so the
    masked form never wipes a key by accident. Send '__CLEAR__' to blank it."""
    payload = request.get_json(silent=True) or {}
    try:
        conn = _pg_conn()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f"DB connect failed: {e}"}), 502
    try:
        written = []
        with conn, conn.cursor() as cur:
            _ensure_secrets_table(cur)
            for key in ALL_SECRET_ROWS:
                if key not in payload:
                    continue
                val = payload[key]
                if key in SECRET_KEYS:
                    if val == '' or val is None:
                        continue          # keep existing
                    if val == '__CLEAR__':
                        val = ''
                val = str(val)
                cur.execute(
                    """INSERT INTO secrets(key, value, updated_at)
                       VALUES (%s, %s, now())
                       ON CONFLICT (key)
                       DO UPDATE SET value = EXCLUDED.value, updated_at = now();""",
                    (key, val),
                )
                written.append(key)
        return jsonify({'ok': True, 'saved': written})
    except Exception as e:
        return jsonify({'error': f"Write failed: {e}"}), 500
    finally:
        conn.close()


@app.route('/api/llm/models', methods=['POST'])
def api_llm_models():
    """Retrieve the model list from the chosen provider.

    Body: { provider, api_key?, base_url? }
    If api_key is omitted/empty, fall back to the stored LLM_API_KEY so the
    user can refresh models without re-typing the key."""
    body = request.get_json(silent=True) or {}
    provider = (body.get('provider') or 'deepseek').lower()
    if provider not in PROVIDERS:
        return jsonify({'error': f"Unknown provider '{provider}'"}), 400

    api_key = (body.get('api_key') or '').strip()
    base_url = (body.get('base_url') or '').strip()

    # fall back to stored key if none supplied
    if not api_key:
        try:
            conn = _pg_conn()
            with conn, conn.cursor() as cur:
                _ensure_secrets_table(cur)
                cur.execute("SELECT value FROM secrets WHERE key='LLM_API_KEY';")
                r = cur.fetchone()
                api_key = r[0] if r else ''
            conn.close()
        except Exception:
            api_key = ''
    if not api_key:
        return jsonify({'error': 'No API key provided or stored.'}), 400

    models_url = PROVIDERS[provider]['models']
    # allow an override base_url to redirect the models endpoint too
    if base_url:
        models_url = base_url.rstrip('/') + ('/v1/models' if provider == 'openai' and '/v1' not in base_url else '/models')

    req = urllib.request.Request(models_url, headers={
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'ignore')[:200]
        return jsonify({'error': f"Provider returned {e.code}: {detail}"}), 502
    except Exception as e:
        return jsonify({'error': f"Request failed: {e}"}), 502

    # OpenAI-compatible: { data: [ { id: ... }, ... ] }
    items = data.get('data', data if isinstance(data, list) else [])
    models = sorted({m.get('id') for m in items if isinstance(m, dict) and m.get('id')})
    # keep chat-capable ids first for openai (drop embeddings/whisper/tts/etc.)
    if provider == 'openai':
        chatish = [m for m in models if any(t in m for t in ('gpt', 'o1', 'o3', 'o4', 'chat'))]
        models = chatish or models
    return jsonify({'ok': True, 'provider': provider,
                    'base_url': base_url or PROVIDERS[provider]['base'],
                    'models': models})


if __name__ == '__main__':
    # threaded=True so one slow DB connect can't block the whole server
    # (a single blocked request behind Cloudflare surfaces as 502).
    # host=0.0.0.0 so the reverse proxy / other containers can reach it.
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
