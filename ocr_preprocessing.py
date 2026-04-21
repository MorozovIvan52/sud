# ocr_preprocessing.py — улучшение качества OCR для судебных документов (контраст, резкость, очистка текста).

import re
from pathlib import Path
try:
    from PIL import Image, ImageEnhance
except ImportError:
    Image = None  # type: ignore
    ImageEnhance = None  # type: ignore

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


def enhance_image(img: "Image.Image") -> "Image.Image":
    """Улучшение контраста и резкости для OCR."""
    if ImageEnhance is None or img is None:
        return img
    try:
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)
    except Exception as e:
        logger.debug("enhance_image: %s", e)
    return img


def clean_text(text: str) -> str:
    """Очистка мусора OCR: лишние символы, множественные пробелы, короткие строки."""
    if not text:
        return ""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = re.sub(r"[^\w\s№§\-\.\,\d]", " ", line)
        line = re.sub(r"\s+", " ", line.strip())
        if len(line) > 3:
            cleaned.append(line)
    return "\n".join(cleaned) if cleaned else " ".join(cleaned)


def extract_text_from_file(file_path: str, dpi: int = 300, lang: str = "rus+eng") -> str:
    """PDF или изображение → текст для LLM (с улучшением качества и очисткой)."""
    path = Path(file_path)
    if not path.exists():
        return ""
    suf = path.suffix.lower()
    text = ""
    try:
        if suf == ".pdf":
            import pdf2image
            images = pdf2image.convert_from_path(file_path, dpi=dpi)
            for img in images:
                img = enhance_image(img)
                try:
                    import pytesseract
                    text += pytesseract.image_to_string(img, lang=lang) + "\n"
                except Exception as e:
                    logger.debug("tesseract pdf page: %s", e)
        else:
            if Image is None:
                return ""
            img = Image.open(file_path)
            img = enhance_image(img)
            try:
                import pytesseract
                text = pytesseract.image_to_string(img, lang=lang)
            except Exception as e:
                logger.debug("tesseract image: %s", e)
    except ImportError as e:
        logger.debug("pdf2image/pytesseract/PIL: %s", e)
        return ""
    except Exception as e:
        logger.debug("extract_text_from_file: %s", e)
        return ""
    return clean_text(text) if text else ""
