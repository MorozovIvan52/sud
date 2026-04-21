# ocr_llm_pipeline.py — PDF/сканы → OCR (Tesseract) → LLM → структурированные данные.
# Интеграция с llm_court_parser и опционально Yandex Vision.

import asyncio
import glob
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from llm_court_parser import SupremeLLMParser, grade_result, create_supreme_llm_excel
except ImportError:
    SupremeLLMParser = None  # type: ignore
    grade_result = None  # type: ignore
    create_supreme_llm_excel = None  # type: ignore

try:
    from ocr_preprocessing import extract_text_from_file, clean_text, enhance_image
    _HAS_OCR_PREPROCESSING = True
except ImportError:
    _HAS_OCR_PREPROCESSING = False
    clean_text = lambda x: x  # noqa: E731
    enhance_image = lambda x: x  # noqa: E731

try:
    from postprocessing import validate_and_enrich
    _HAS_POSTPROCESSING = True
except ImportError:
    _HAS_POSTPROCESSING = False
    validate_and_enrich = lambda x: x  # noqa: E731

try:
    from supreme_error_handler import SupremeErrorHandler
    _HAS_ERROR_HANDLER = True
except ImportError:
    SupremeErrorHandler = None  # type: ignore
    _HAS_ERROR_HANDLER = False

try:
    from anti_hallucination import SupremeAntiHallucination
    _HAS_ANTI_HALLUCINATION = True
except ImportError:
    SupremeAntiHallucination = None  # type: ignore
    _HAS_ANTI_HALLUCINATION = False


def _parse_date(value: Any) -> Optional[str]:
    """Нормализация даты в YYYY-MM-DD."""
    if value is None:
        return None
    if isinstance(value, date):
        d = value.date() if hasattr(value, "date") and callable(getattr(value, "date")) else value
        return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(s[:10], fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s[:10] if len(s) >= 10 else s


async def _run_in_executor(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args))


def _extract_text_pdf(file_path: str) -> str:
    """PDF → список изображений → Tesseract OCR (sync). С улучшением качества при наличии ocr_preprocessing."""
    try:
        import pdf2image
        images = pdf2image.convert_from_path(file_path, dpi=300)
        text_parts = []
        for img in images:
            if _HAS_OCR_PREPROCESSING:
                from ocr_preprocessing import enhance_image
                img = enhance_image(img)
            try:
                import pytesseract
                text_parts.append(pytesseract.image_to_string(img, lang="rus+eng" if _HAS_OCR_PREPROCESSING else "rus"))
            except Exception as e:
                logger.debug("tesseract page: %s", e)
        text = "\n".join(text_parts) if text_parts else ""
        return clean_text(text) if _HAS_OCR_PREPROCESSING and text else text
    except ImportError as e:
        logger.debug("pdf2image/pytesseract: %s", e)
        return ""
    except Exception as e:
        logger.debug("PDF extract: %s", e)
        return ""


def _extract_text_image(file_path: str) -> str:
    """Одно изображение → Tesseract OCR (sync). С улучшением при наличии ocr_preprocessing."""
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(file_path)
        if _HAS_OCR_PREPROCESSING:
            from ocr_preprocessing import enhance_image
            img = enhance_image(img)
        text = pytesseract.image_to_string(img, lang="rus+eng" if _HAS_OCR_PREPROCESSING else "rus") or ""
        return clean_text(text) if _HAS_OCR_PREPROCESSING and text else text
    except ImportError as e:
        logger.debug("PIL/pytesseract: %s", e)
        return ""
    except Exception as e:
        logger.debug("Image extract: %s", e)
        return ""


class SupremeDocumentPipeline:
    """Полный пайплайн: PDF/изображение → OCR → LLM → валидированный JSON."""

    def __init__(
        self,
        llm_parser: Optional[Any] = None,
        gigachat_credentials: Optional[str] = None,
        use_advanced_prompt: bool = False,
        use_error_handler: bool = True,
        use_anti_hallucination: bool = True,
    ):
        if llm_parser is not None:
            self.llm_parser = llm_parser
        elif SupremeLLMParser:
            self.llm_parser = SupremeLLMParser(
                credentials=gigachat_credentials,
                use_advanced_prompt=use_advanced_prompt,
            )
        else:
            self.llm_parser = None
        self.error_handler = None
        if use_error_handler and _HAS_ERROR_HANDLER and self.llm_parser:
            self.error_handler = SupremeErrorHandler(
                self.llm_parser,
                max_retries=3,
                timeout_seconds=30.0,
                cache_size=1000,
            )
        self.anti_hallucination = None
        if use_anti_hallucination and _HAS_ANTI_HALLUCINATION and self.llm_parser:
            self.anti_hallucination = SupremeAntiHallucination(llm_parser=self.llm_parser)

    async def extract_text(self, file_path: str) -> str:
        """PDF или изображение → текст (Tesseract OCR). При необходимости — Yandex Vision fallback."""
        path = Path(file_path)
        if not path.exists():
            return ""
        suf = path.suffix.lower()
        if suf == ".pdf":
            text = await _run_in_executor(_extract_text_pdf, str(path))
        elif suf in (".jpg", ".jpeg", ".png", ".tiff", ".bmp"):
            text = await _run_in_executor(_extract_text_image, str(path))
        else:
            # попробуем как изображение
            text = await _run_in_executor(_extract_text_image, str(path))
        if not text.strip():
            logger.debug("OCR returned empty for %s", file_path)
        return text or ""

    def post_process(self, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация + нормализация дат и court_section; при наличии postprocessing — validate_and_enrich."""
        if "error" in llm_result:
            return llm_result
        if llm_result.get("decision_date"):
            llm_result["decision_date"] = _parse_date(llm_result["decision_date"]) or llm_result["decision_date"]
        if llm_result.get("court_name") and "участок" in str(llm_result.get("court_name", "")).lower():
            match = re.search(r"№\s*(\d+)", llm_result["court_name"])
            if match and llm_result.get("court_section") is None:
                try:
                    llm_result["court_section"] = int(match.group(1))
                except (TypeError, ValueError):
                    pass
        if _HAS_POSTPROCESSING:
            return validate_and_enrich(llm_result)
        return llm_result

    async def process_document(self, file_path: str, doc_type: str = "universal") -> Dict[str, Any]:
        """PDF/изображение → текст → LLM(doc_type) или safe_parse_document → пост-обработка → anti-hallucination."""
        text = await self.extract_text(file_path)
        if not text.strip():
            return {"error": "Не удалось извлечь текст (OCR)", "confidence": 0.0}
        if not self.llm_parser:
            return {"error": "LLM парсер не настроен (llm_court_parser)", "confidence": 0.0}
        if self.error_handler:
            llm_result = await self.error_handler.safe_parse_document(text, doc_type)
        else:
            loop = asyncio.get_event_loop()
            llm_result = await loop.run_in_executor(
                None, lambda: self.llm_parser.parse_document(text, doc_type)
            )
        llm_result = self.post_process(llm_result)
        if getattr(self, "anti_hallucination", None) and "error" not in llm_result:
            try:
                validation = await self.anti_hallucination.detect_hallucinations(llm_result, original_text=text)
                llm_result["final_confidence"] = validation.get("final_confidence", llm_result.get("confidence"))
                llm_result["grade"] = validation.get("grade")
                llm_result["hallucination_risk"] = validation.get("hallucination_risk", False)
                llm_result["hallucination_checks"] = validation.get("hallucination_checks", [])
                llm_result["confidence"] = validation.get("final_confidence", llm_result.get("confidence"))
            except Exception as e:
                logger.debug("anti_hallucination: %s", e)
        return llm_result


async def batch_parse_documents(
    folder_path: str,
    pipeline: Optional[SupremeDocumentPipeline] = None,
    concurrency: int = 10,
    output_excel: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Пакетная обработка: все PDF в папке → список результатов, опционально экспорт в Excel."""
    files = glob.glob(str(Path(folder_path) / "*.pdf"))
    if not files:
        files = []
        for ext in ("*.jpg", "*.jpeg", "*.png"):
            files.extend(glob.glob(str(Path(folder_path) / ext)))
    if not files:
        return []

    if pipeline is None:
        pipeline = SupremeDocumentPipeline()

    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(file: str) -> Dict[str, Any]:
        async with semaphore:
            return await pipeline.process_document(file)

    results = await asyncio.gather(*[process_one(f) for f in files], return_exceptions=True)
    out = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.warning("batch file %s: %s", files[i], r)
            out.append({"error": str(r), "file": files[i], "confidence": 0.0})
        else:
            if isinstance(r, dict) and "file" not in r:
                r["file"] = files[i]
            out.append(r)

    if output_excel and out:
        try:
            if create_supreme_llm_excel and grade_result:
                for r in out:
                    if isinstance(r, dict) and "grade" not in r:
                        r["grade"] = grade_result(r)
                create_supreme_llm_excel(out, output_excel)
            else:
                import pandas as pd
                pd.DataFrame(out).to_excel(output_excel, index=False)
            logger.info("Saved to %s", output_excel)
        except Exception as e:
            logger.warning("Excel export: %s", e)

    return out


async def batch_parse_with_recovery(
    excel_path: str,
    pipeline: Optional["SupremeDocumentPipeline"] = None,
    output_excel: Optional[str] = None,
    concurrency: int = 15,
    text_column: str = "document_text",
    doc_type_column: Optional[str] = "doc_type",
    id_column: Optional[str] = "id",
) -> List[Dict[str, Any]]:
    """Батч из Excel (колонки document_text, doc_type, id) с градацией и восстановлением ошибок."""
    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas required for batch_parse_with_recovery")
        return []
    df = pd.read_excel(excel_path)
    if df.empty or text_column not in df.columns:
        return []
    if pipeline is None:
        pipeline = SupremeDocumentPipeline()
    semaphore = asyncio.Semaphore(concurrency)

    async def safe_parse_row(row: Any) -> Dict[str, Any]:
        async with semaphore:
            try:
                text = str(row.get(text_column, "") or "").strip()
                doc_type = str(row.get(doc_type_column, "universal") or "universal").strip()
                if not text:
                    return {"row_id": row.get(id_column), "error": "Пустой текст", "grade": "MANUAL", "confidence": 0.0}
                if getattr(pipeline, "error_handler", None):
                    result = await pipeline.error_handler.safe_parse_document(text, doc_type)
                else:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, lambda: pipeline.llm_parser.parse_document(text, doc_type=doc_type))
                result = pipeline.post_process(result)
                result["row_id"] = row.get(id_column)
                result["grade"] = grade_result(result) if grade_result else "MANUAL"
                return result
            except Exception as e:
                return {"row_id": row.get(id_column), "error": str(e), "grade": "MANUAL", "confidence": 0.0}

    tasks = [safe_parse_row(row) for _, row in df.iterrows()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            out.append({"row_id": df.iloc[i].get(id_column) if id_column in df.columns else i, "error": str(r), "grade": "MANUAL", "confidence": 0.0})
        else:
            out.append(r)
    if output_excel and out:
        try:
            if create_supreme_llm_excel:
                create_supreme_llm_excel(out, output_excel)
            else:
                pd.DataFrame(out).to_excel(output_excel, index=False)
            logger.info("batch_parse_with_recovery saved to %s", output_excel)
        except Exception as e:
            logger.warning("Excel export: %s", e)
    success_rate = sum(1 for r in out if (r.get("confidence") or 0) > 0.8) / len(out) if out else 0
    logger.info("Batch success rate: %.1f%%", success_rate * 100)
    return out
