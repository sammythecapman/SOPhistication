#!/usr/bin/env sh
set -e
echo "→ Initializing DB schema..."
python -c "import db; db.init_db(); print('   DB schema ready')"
echo "→ Starting gunicorn on :${PORT:-8080}"
exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 8 --timeout 300 app:app
