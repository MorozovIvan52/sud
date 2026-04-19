"""
Celery-задачи пакетной обработки.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.celery_app import celery_app

CHUNK_SIZE = 1000


@celery_app.task(bind=True, max_retries=3)
def process_batch_file(self, file_path: str, user_id: str = "") -> dict:
    """
    Обработка файла с должниками. Разбиение на чанки по 1000 записей.
    :param file_path: путь к загруженному файлу (CSV/XLSX)
    :param user_id: идентификатор пользователя
    :return: dict с task_id, total, ok, errors, output_path
    """
    try:
        from batch_processing.utils.file_handler import read_file
        from batch_processing.services.pipeline import process_batch
        from batch_processing.services.output_generator import generate_xlsx
        import time

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        debtors = read_file(path)
        if not debtors:
            return {"status": "error", "message": "Файл пуст или не содержит данных"}

        results = []
        for i in range(0, len(debtors), CHUNK_SIZE):
            chunk = debtors[i : i + CHUNK_SIZE]
            chunk_results = process_batch(chunk)
            results.extend(chunk_results)

        out_dir = ROOT / "batch_outputs"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"batch_{int(time.time())}_{user_id or 'anon'}.xlsx"
        generate_xlsx(results, out_path)

        ok = sum(1 for r in results if r.get("Наименование суда"))
        return {
            "status": "ok",
            "total": len(results),
            "ok": ok,
            "errors": len(results) - ok,
            "output_path": str(out_path),
            "download_url": f"/api/v1/download/{out_path.name}",
        }
    except Exception as e:
        self.retry(exc=e)
