FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir celery redis psycopg2-binary
RUN python -m spacy download ru_core_news_sm

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "court_locator.api:app", "--host", "0.0.0.0", "--port", "8000"]
