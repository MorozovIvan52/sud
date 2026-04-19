"""
Русскоязычный NLP: spaCy и Natasha.

Зависимости: см. requirements.txt (spacy, natasha).
Модель spaCy: ``python -m spacy download ru_core_news_sm`` (или md/lg).

Интеграция: ``LawRuleMatcher`` (court_locator/law_rules.py) использует леммы spaCy и
fuzzy-сопоставление к падежным формам улиц; ``address_parser.address_lemmas`` — тонкая
обёртка для разбора адреса.

Пример::

    from court_locator.ru_nlp import get_spacy_nlp, natasha_doc

    doc = get_spacy_nlp()(\"ул. Ленина, д. 5\")
    for t in doc:
        print(t.text, t.lemma_, t.pos_)

    nd = natasha_doc(\"Москва, Тверская улица, 10\")
    for t in nd.tokens:
        print(t.text, t.pos, t.feats)
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, List

# Имя модели по умолчанию (после ``python -m spacy download ru_core_news_sm``)
DEFAULT_SPACY_RU_MODEL = "ru_core_news_sm"


@lru_cache(maxsize=4)
def get_spacy_nlp(model: str = DEFAULT_SPACY_RU_MODEL) -> Any:
    """Загружает pipeline spaCy (кэш на процесс)."""
    import spacy

    return spacy.load(model)


def spacy_parse(text: str, model: str = DEFAULT_SPACY_RU_MODEL) -> Any:
    """Разбор текста spaCy (Doc)."""
    return get_spacy_nlp(model)(text or "")


def spacy_lemmas(
    text: str,
    *,
    model: str = DEFAULT_SPACY_RU_MODEL,
    skip_punct: bool = True,
    skip_space: bool = True,
) -> List[str]:
    """Список лемм токенов (нижний регистр)."""
    doc = spacy_parse(text, model)
    out: List[str] = []
    for t in doc:
        if skip_space and t.is_space:
            continue
        if skip_punct and t.is_punct:
            continue
        out.append(t.lemma_.lower())
    return out


@lru_cache(maxsize=1)
def _natasha_pipeline() -> dict:
    from natasha import (
        MorphVocab,
        NewsEmbedding,
        NewsMorphTagger,
        NewsNERTagger,
        NewsSyntaxParser,
        Segmenter,
    )

    emb = NewsEmbedding()
    return {
        "segmenter": Segmenter(),
        "morph_vocab": MorphVocab(),
        "morph": NewsMorphTagger(emb),
        "syntax": NewsSyntaxParser(emb),
        "ner": NewsNERTagger(emb),
    }


def natasha_doc(
    text: str,
    *,
    with_syntax: bool = True,
    with_ner: bool = True,
) -> Any:
    """
    Конвейер Natasha: сегментация, морфология, опционально синтаксис и NER.

    Возвращает ``natasha.Doc`` (итерируемый по ``.tokens``, есть ``.sents``).
    """
    from natasha import Doc

    p = _natasha_pipeline()
    doc = Doc(text or "")
    doc.segment(p["segmenter"])
    doc.tag_morph(p["morph"])
    if with_syntax:
        doc.parse_syntax(p["syntax"])
    if with_ner:
        doc.tag_ner(p["ner"])
    return doc


def natasha_morph_vocab() -> Any:
    """MorphVocab Natasha (нормализация форм, словари)."""
    return _natasha_pipeline()["morph_vocab"]


def spacy_lemma_join(text: str, model: str = DEFAULT_SPACY_RU_MODEL) -> str:
    """Строка из лемм токенов через пробел (для сопоставления с regex по улице)."""
    lemmas = spacy_lemmas(text, model=model)
    return " ".join(lemmas)


def try_spacy_lemma_join(text: str, model: str = DEFAULT_SPACY_RU_MODEL) -> str | None:
    """Безопасно: при отсутствии spaCy/модели возвращает None."""
    try:
        return spacy_lemma_join(text, model=model)
    except (OSError, ImportError, LookupError):
        return None


def nlp_match_variants(address: str) -> List[str]:
    """
    Варианты строки адреса для матчинга: исходный текст и строка лемм spaCy.
    Порядок: сначала полный адрес, затем лемматизированная форма.
    """
    addr = (address or "").strip()
    if not addr:
        return []
    seen: set[str] = set()
    out: List[str] = []
    for s in (addr, try_spacy_lemma_join(addr) or ""):
        s = s.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out
