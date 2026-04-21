"""
Unit-тесты для сервисов.
habr.com/ru/articles/765512/
"""
import pytest

from app.services.address_normalizer import AddressNormalizer
from app.core.exceptions import ValidationError


class TestAddressNormalizer:
    def test_normalize_basic(self):
        n = AddressNormalizer()
        assert "улица" in n.normalize("ул. Тверская, д. 7")
        assert "г. " in n.normalize("гор. Москва")

    def test_normalize_empty_raises(self):
        n = AddressNormalizer()
        with pytest.raises(ValidationError):
            n.normalize("")

    def test_normalize_short_raises(self):
        n = AddressNormalizer()
        with pytest.raises(ValidationError):
            n.normalize("abc")

    def test_hash_address(self):
        h = AddressNormalizer.hash_address("Москва, Тверская 7")
        assert len(h) == 64
        assert h == AddressNormalizer.hash_address("москва, тверская 7")
