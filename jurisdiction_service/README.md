# Jurisdiction Service

Микросервис определения территориальной подсудности судов РФ по адресу и координатам (ГПК РФ ст. 28-30).

## Запуск

```bash
# Сборка и запуск
docker-compose up --build

# API docs
open http://localhost:8000/docs
```

## Первоначальная настройка

1. Создать пользователя и получить JWT:
```bash
curl -X POST http://localhost:8000/api/v1/admin/users \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'
```

2. Загрузить тестовые данные (полигоны):
```bash
cd jurisdiction_service
python -m scripts.seed_data
```

3. Запрос по адресу:
```bash
TOKEN="<access_token из шага 1>"
curl "http://localhost:8000/api/v1/jurisdiction/address?address=г.%20Москва,%20ул.%20Тверская,%20д.%207" \
  -H "Authorization: Bearer $TOKEN"
```

4. Запрос по координатам:
```bash
curl "http://localhost:8000/api/v1/jurisdiction/coordinates?latitude=55.7558&longitude=37.6173" \
  -H "Authorization: Bearer $TOKEN"
```

## Переменные окружения

См. `.env.example`. Ключевые:
- `DATABASE_URL` — PostgreSQL + asyncpg
- `REDIS_URL` — Redis
- `JWT_SECRET_KEY` — секрет для JWT
- `YANDEX_GEO_KEY` — геокодирование
- `DADATA_TOKEN` — опционально, ФИАС

## Тесты

```bash
pytest tests/ -v
```
