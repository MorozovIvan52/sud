"""
REST API сервиса определения территориальной подсудности.
Только бесплатные источники: БД судов, геокодер Nominatim (при отсутствии YANDEX_GEO_KEY), GeoJSON.

Запуск: uvicorn court_locator.api:app --host 0.0.0.0 --port 8000
Или из корня: python -m uvicorn court_locator.api:app --reload
"""
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

# Корень проекта для импорта parser
_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

try:
    from fastapi import FastAPI, HTTPException, UploadFile, File, Query
    from fastapi.responses import JSONResponse, FileResponse
    from pydantic import BaseModel, Field
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# Глобальный экземпляр локатора (создаётся при старте)
_locator = None
_request_times: List[float] = []  # последние 100 времён ответа по координатам (мс)


def _get_locator():
    global _locator
    if _locator is None:
        from court_locator.main import CourtLocator
        _locator = CourtLocator(use_cache=True)
    return _locator


if HAS_FASTAPI:

    class CoordinatesBody(BaseModel):
        lat: float = Field(..., ge=-90, le=90, description="Широта WGS84")
        lng: float = Field(..., ge=-180, le=180, description="Долгота WGS84")

    class AddressBody(BaseModel):
        address: str = Field(..., min_length=1, description="Текстовый адрес")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _get_locator()
        yield
        if _locator:
            _locator.close()

    app = FastAPI(
        title="API определения территориальной подсудности",
        description="Поиск мирового суда по GPS-координатам (WGS84) или по текстовому адресу. Бесплатные источники: локальная БД, Nominatim (при отсутствии ключа Yandex).",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.post("/api/find-jurisdiction", response_model=dict)
    async def find_jurisdiction(coords: CoordinatesBody) -> dict:
        """
        Определение подсудности по GPS-координатам (приоритетный метод).
        Целевое время отклика: < 100 мс при кеше, < 500 мс с геокодером.
        """
        start = time.perf_counter()
        loc = _get_locator()
        result = loc.locate_court(lat=coords.lat, lng=coords.lng)
        elapsed_ms = (time.perf_counter() - start) * 1000
        _request_times.append(elapsed_ms)
        if len(_request_times) > 100:
            _request_times.pop(0)
        if result is None:
            raise HTTPException(status_code=404, detail="Суд для указанных координат не найден")
        out = {
            "success": True,
            "jurisdiction": result,
            "response_time_ms": round(elapsed_ms, 2),
        }
        return out

    @app.post("/api/find-jurisdiction-by-address", response_model=dict)
    async def find_jurisdiction_by_address(body: AddressBody) -> dict:
        """
        Определение подсудности по текстовому адресу (геокодирование через Yandex или Nominatim).
        Целевое время отклика: < 500 мс.
        """
        start = time.perf_counter()
        loc = _get_locator()
        result = loc.locate_court(address=body.address.strip())
        elapsed_ms = (time.perf_counter() - start) * 1000
        if result is None:
            raise HTTPException(status_code=404, detail="Суд для указанного адреса не найден")
        return {
            "success": True,
            "address": body.address,
            "jurisdiction": result,
            "response_time_ms": round(elapsed_ms, 2),
        }

    @app.get("/api/boundaries", response_class=JSONResponse)
    async def export_boundaries_geojson() -> dict:
        """
        Экспорт границ всех судебных участков в формате GeoJSON FeatureCollection.
        Данные из локальной БД court_districts.
        """
        loc = _get_locator()
        districts = loc.db.get_all_districts()
        features: List[Dict[str, Any]] = []
        for d in districts:
            boundaries = d.get("boundaries")
            if not boundaries:
                continue
            # GeoJSON Polygon: coordinates = [ ring1, ring2... ], ring = [ [lng,lat], ... ]
            if isinstance(boundaries, dict) and boundaries.get("type") == "Polygon":
                geom = boundaries
            elif isinstance(boundaries, list) and boundaries:
                ring = boundaries[0] if isinstance(boundaries[0], (list, tuple)) and len(boundaries[0]) > 2 else boundaries
                geom = {"type": "Polygon", "coordinates": [ring]}
            else:
                continue
            features.append({
                "type": "Feature",
                "properties": {
                    "id": d.get("id"),
                    "district_number": d.get("district_number"),
                    "region": d.get("region"),
                    "address": d.get("address"),
                    "phone": d.get("phone"),
                    "schedule": d.get("schedule"),
                    "judge_name": d.get("judge_name"),
                    "court_name": d.get("court_name"),
                },
                "geometry": geom,
            })
        return {"type": "FeatureCollection", "features": features}

    @app.get("/api/health")
    async def health() -> dict:
        """Проверка доступности сервиса."""
        return {"status": "ok", "service": "court_locator"}

    @app.get("/api/metrics")
    async def metrics() -> dict:
        """Простой мониторинг: последние времена отклика по координатам (мс)."""
        if not _request_times:
            return {"response_times_ms": [], "count": 0}
        return {
            "response_times_ms": [round(t, 2) for t in _request_times[-20:]],
            "count": len(_request_times),
            "last_ms": round(_request_times[-1], 2),
        }

    @app.get("/api/geocode-report")
    async def geocode_report() -> dict:
        """Отчёт по качеству геокодирования: по регионам, источникам, точности."""
        try:
            from court_locator.geocode_quality_monitor import get_monitor
            return get_monitor().generate_report()
        except Exception:
            return {"total": 0, "error": "Мониторинг недоступен"}

    @app.get("/api/nextgis-map")
    async def nextgis_map_tms() -> dict:
        """
        URL TMS для отображения границ судебных участков на карте (NextGIS Map API).
        Источник: api.mapdev.io, Россошанский судебный район (Воронежская обл.).
        """
        from court_locator import config
        return {
            "tms_url": getattr(config, "NEXTGIS_MAP_TMS_URL", ""),
            "source": "https://api.mapdev.io/resource/138",
            "description": "Границы судебных участков (полигональный)",
        }

    @app.post("/api/nextgis-load")
    async def nextgis_load_boundaries() -> dict:
        """
        Загрузить границы судебных участков из NextGIS API в court_districts.
        Ресурс 137 — GeoJSON, 186 участков (Россошанский район и др.).
        """
        try:
            from court_locator.nextgis_source import load_nextgis_to_db
            count = load_nextgis_to_db(clear_before=False)
            return {"success": True, "loaded": count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/nextgis-resources")
    async def nextgis_resources(parent_id: int = 2) -> dict:
        """
        Список ресурсов NextGIS с GeoJSON (postgis_layer, vector_layer).
        parent_id=2 — «Границы участков мировых судей».
        """
        try:
            from court_locator.nextgis_source import discover_geojson_resources, fetch_resource_meta
            resources = discover_geojson_resources(parent_id=parent_id)
            return {"parent_id": parent_id, "resources": resources}
        except Exception as e:
            return {"error": str(e), "resources": []}

    @app.post("/api/nextgis-sync-postgis")
    async def nextgis_sync_postgis() -> dict:
        """
        Синхронизация NextGIS GeoJSON → PostGIS court_districts.
        Требует PG_DSN или NGW_POSTGIS_DSN.
        """
        try:
            from court_locator.nextgis_source import sync_nextgis_to_postgis
            count = sync_nextgis_to_postgis(clear_before=False)
            return {"success": True, "synced": count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Пакетная обработка (45 полей) ---
    @app.post("/api/v1/batch-process")
    async def batch_process(
        file: UploadFile = File(...),
        format: str = Query("json", description="json или xlsx"),
    ) -> dict:
        """
        Пакетная обработка должников. CSV/XLSX с колонками: ФИО, Адрес (обязательно), Паспорт, Сумма, Широта, Долгота.
        format=json — JSON с результатами; format=xlsx — скачивание XLSX.
        """

        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="Загрузите файл CSV или XLSX")

        suf = Path(file.filename).suffix.lower()
        if suf not in (".csv", ".xlsx", ".xls"):
            raise HTTPException(status_code=400, detail="Формат не поддерживается. Используйте CSV или XLSX.")

        import tempfile
        from batch_processing.utils.file_handler import read_file
        from batch_processing.services.pipeline import process_batch
        from batch_processing.services.output_generator import generate_xlsx

        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            debtors = read_file(tmp_path)
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Ошибка чтения файла: {e}")
        finally:
            tmp_path.unlink(missing_ok=True)

        if not debtors:
            raise HTTPException(status_code=400, detail="Файл пуст или не содержит колонок ФИО/Адрес")

        if len(debtors) > 5000:
            raise HTTPException(
                status_code=400,
                detail="Максимум 5000 записей за один запрос. Для больших объёмов используйте Celery.",
            )

        start = time.perf_counter()
        results = process_batch(debtors)
        elapsed = (time.perf_counter() - start) * 1000

        ok_count = sum(1 for r in results if r.get("Наименование суда"))

        if format == "xlsx":
            out_dir = _ROOT / "batch_outputs"
            out_dir.mkdir(exist_ok=True)
            out_path = out_dir / f"batch_{int(time.time())}.xlsx"
            generate_xlsx(results, out_path)
            return FileResponse(
                out_path,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=out_path.name,
            )

        return {
            "success": True,
            "total": len(results),
            "ok": ok_count,
            "errors": len(results) - ok_count,
            "elapsed_ms": round(elapsed, 2),
            "results": results[:100],
        }

    # --- Асинхронная пакетная обработка (Celery) ---
    @app.post("/api/v1/batch-process-async")
    async def batch_process_async(
        file: UploadFile = File(...),
        user_id: str = Query("", description="Идентификатор пользователя"),
    ) -> dict:
        """
        Асинхронная обработка через Celery. Для файлов > 5000 записей.
        Возвращает task_id для отслеживания статуса.
        """
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="Загрузите файл CSV или XLSX")
        suf = Path(file.filename).suffix.lower()
        if suf not in (".csv", ".xlsx", ".xls"):
            raise HTTPException(status_code=400, detail="Формат: CSV или XLSX")
        try:
            from core.tasks import process_batch_file
        except ImportError:
            raise HTTPException(status_code=501, detail="Celery не настроен. Установите celery[redis].")
        upload_dir = _ROOT / "batch_outputs" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{int(time.time())}_{file.filename}"
        content = await file.read()
        file_path.write_bytes(content)
        task = process_batch_file.delay(str(file_path), user_id=user_id)
        return {
            "success": True,
            "task_id": task.id,
            "message": "Задача поставлена в очередь. Проверьте статус: GET /api/v1/task/{task_id}",
            "status_url": f"/api/v1/task/{task.id}",
        }

    @app.get("/api/v1/task/{task_id}")
    async def get_task_status(task_id: str) -> dict:
        """Статус задачи Celery."""
        try:
            from celery.result import AsyncResult
            from core.celery_app import celery_app
        except ImportError:
            raise HTTPException(status_code=501, detail="Celery не настроен")
        result = AsyncResult(task_id, app=celery_app)
        out = {"task_id": task_id, "status": result.status}
        if result.ready():
            if result.successful():
                out["result"] = result.get()
            else:
                out["error"] = str(result.result) if result.result else "Unknown error"
        return out

    # --- Пакетная обработка по GPS (без парсинга адресов) ---
    @app.post("/api/v1/batch-gps-process")
    async def batch_gps_process(
        file: UploadFile = File(...),
        format: str = Query("json", description="json или xlsx"),
    ) -> dict:
        """
        Пакетная обработка по GPS-координатам. Форматы: CSV, XLSX, GeoJSON, KML.
        Обязательные колонки: lat (широта), lon/lng (долгота). Опционально: case_type, debt_amount.
        Без этапа геокодирования — прямой поиск по полигонам.
        """
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="Загрузите файл с координатами")

        suf = Path(file.filename).suffix.lower()
        allowed = (".csv", ".xlsx", ".xls", ".geojson", ".kml", ".json")
        if suf not in allowed and not file.filename.lower().endswith(".geojson"):
            raise HTTPException(
                status_code=400,
                detail=f"Формат не поддерживается. Используйте: CSV, XLSX, GeoJSON, KML.",
            )

        import tempfile
        from batch_processing.utils.file_handler import read_file_gps
        from batch_processing.services.pipeline import process_batch_gps
        from batch_processing.services.output_generator import generate_xlsx

        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            rows = read_file_gps(tmp_path)
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Ошибка чтения файла: {e}")
        finally:
            tmp_path.unlink(missing_ok=True)

        if not rows:
            raise HTTPException(
                status_code=400,
                detail="Файл пуст или не содержит валидных координат (lat, lon в диапазоне WGS84)",
            )

        if len(rows) > 30000:
            raise HTTPException(
                status_code=400,
                detail="Максимум 30 000 записей за один запрос.",
            )

        start = time.perf_counter()
        results = process_batch_gps(rows)
        elapsed = (time.perf_counter() - start) * 1000

        ok_count = sum(1 for r in results if r.get("Наименование суда"))

        if format == "xlsx":
            out_dir = _ROOT / "batch_outputs"
            out_dir.mkdir(exist_ok=True)
            out_path = out_dir / f"batch_gps_{int(time.time())}.xlsx"
            generate_xlsx(results, out_path)
            return FileResponse(
                out_path,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=out_path.name,
            )

        return {
            "success": True,
            "total": len(results),
            "ok": ok_count,
            "errors": len(results) - ok_count,
            "elapsed_ms": round(elapsed, 2),
            "results": results[:100],
        }

else:
    app = None


if __name__ == "__main__":
    if not HAS_FASTAPI:
        raise SystemExit("Установите: pip install fastapi uvicorn")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
