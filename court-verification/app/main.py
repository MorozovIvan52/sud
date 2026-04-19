from fastapi import FastAPI
from app.database import engine, Base
from app.api.endpoints import router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Court Verification API", version="1.0.0")
app.include_router(router, prefix="/api/v1", tags=["courts"])


@app.get("/")
def root():
    return {"service": "court-verification", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
