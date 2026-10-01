#!/usr/bin/env bash
# Server status — standalone. Port 5001 so it doesn't clash with the config app (5000).
uwsgi --http :5001 --wsgi-file app.py --callable app --disable-logging
