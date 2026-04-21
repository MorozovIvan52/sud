"""
Dashboard API: парсер по № ИП и батч Excel (Supreme).
Запуск: uvicorn dashboard:app --host 0.0.0.0 --port 8001
"""
import asyncio
import tempfile
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse

try:
    from supreme_parser import (
        SupremeParser,
        SupremeCourtResult,
        batch_parse_ip,
        create_supreme_excel,
    )
    _HAS_SUPREME = True
except ImportError:
    _HAS_SUPREME = False

app = FastAPI(title="ПарсерСуд Pro", version="1.0")


@app.get("/health")
async def health():
    return {"status": "ok", "supreme": _HAS_SUPREME}


@app.post("/api/parse_ip")
async def parse_ip(ip_number: str = Query(..., description="Номер исполнительного производства")):
    """Поиск по номеру ИП → суд + статус."""
    if not _HAS_SUPREME:
        raise HTTPException(status_code=503, detail="Supreme parser not available")
    ip_number = (ip_number or "").strip()
    if not ip_number:
        raise HTTPException(status_code=400, detail="ip_number required")
    async with SupremeParser() as parser:
        result = await parser.parse_ip_number(ip_number)
    return result.to_dict()


@app.post("/api/batch_excel")
async def batch_excel(file: UploadFile = File(...)):
    """Загрузка Excel с колонкой ip или ip_number → батч-разбор → JSON результатов."""
    if not _HAS_SUPREME:
        raise HTTPException(status_code=503, detail="Supreme parser not available")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Expected .xlsx or .xls file")
    try:
        import pandas as pd
        content = await file.read()
        df = pd.read_excel(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel: {e}")
    ip_col = None
    for c in df.columns:
        if str(c).strip().lower() in ("ip", "ip_number", "№ ип", "номер ип"):
            ip_col = c
            break
    if ip_col is None:
        raise HTTPException(status_code=400, detail="No column 'ip' or 'ip_number' found")
    ip_list = [str(x).strip() for x in df[ip_col].dropna().unique() if str(x).strip()]
    if not ip_list:
        raise HTTPException(status_code=400, detail="No IP numbers in column")
    results = await batch_parse_ip(ip_list)
    return {
        "results": [r.to_dict() for r in results],
        "count": len(results),
        "accuracy": sum(r.confidence for r in results) / len(results) if results else 0,
    }


@app.post("/api/batch_excel_file")
async def batch_excel_file(file: UploadFile = File(...)):
    """Загрузка Excel с колонкой ip → разбор → возврат Excel-файла с цветами по статусу."""
    if not _HAS_SUPREME:
        raise HTTPException(status_code=503, detail="Supreme parser not available")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Expected .xlsx or .xls file")
    try:
        import pandas as pd
        content = await file.read()
        df = pd.read_excel(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel: {e}")
    ip_col = None
    for c in df.columns:
        if str(c).strip().lower() in ("ip", "ip_number", "№ ип", "номер ип"):
            ip_col = c
            break
    if ip_col is None:
        raise HTTPException(status_code=400, detail="No column 'ip' or 'ip_number' found")
    ip_list = [str(x).strip() for x in df[ip_col].dropna().tolist() if str(x).strip()]
    if not ip_list:
        raise HTTPException(status_code=400, detail="No IP numbers in column")
    results = await batch_parse_ip(ip_list)
    out_path = Path(tempfile.gettempdir()) / f"supreme_{file.filename}"
    create_supreme_excel(results, str(out_path))
    return FileResponse(str(out_path), filename=f"supreme_{file.filename}", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
