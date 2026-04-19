"""
Точка входа: uvicorn main:app --reload
"""
from fastapi import FastAPI
from app.database import engine, Base
from app.api.endpoints import router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Court Boundary Verification System",
    description="Система определения территориальной подсудности",
    version="1.0.0",
)
app.include_router(router, prefix="/api/v1")


@app.get("/")
def read_root():
    return {"message": "Система определения подсудности запущена!", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
