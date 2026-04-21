#!/bin/sh
# Загрузка тестовых данных при первом запуске (опционально)
python -m scripts.seed_data 2>/dev/null || true
exec "$@"
