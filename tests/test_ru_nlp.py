"""Опциональные тесты spaCy + Natasha (pytest.importorskip)."""

import pytest

spacy = pytest.importorskip("spacy")
pytest.importorskip("natasha")

from court_locator.ru_nlp import (  # noqa: E402
    DEFAULT_SPACY_RU_MODEL,
    get_spacy_nlp,
    natasha_doc,
    spacy_lemmas,
)


def test_spacy_load_and_lemma():
    try:
        nlp = get_spacy_nlp(DEFAULT_SPACY_RU_MODEL)
    except OSError:
        pytest.skip(f"Модель {DEFAULT_SPACY_RU_MODEL} не установлена: python -m spacy download {DEFAULT_SPACY_RU_MODEL}")
    doc = nlp("Нижний Новгород, улица Ленина, дом 10")
    assert len(doc) > 0
    lemmas = spacy_lemmas("улица Ленина")
    assert lemmas, "ожидались леммы"
    assert any("ленин" in x or "ленина" in x for x in lemmas)


def test_natasha_pipeline():
    d = natasha_doc("г. Саров, ул. Гоголя, д. 7", with_syntax=True, with_ner=True)
    tokens = list(d.tokens)
    assert len(tokens) >= 3
