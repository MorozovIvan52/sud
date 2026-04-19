"""
Схема входящего запроса для пакетной обработки.
"""
from typing import Optional
from pydantic import BaseModel, Field


class DebtorInput(BaseModel):
    """Одна строка входного файла (обязательные поля: ФИО, адрес)."""

    fio: str = Field(..., min_length=1, description="ФИО должника")
    address: str = Field(..., min_length=1, description="Адрес регистрации")
    passport: Optional[str] = Field(None, description="Серия и номер паспорта")
    debt_amount: Optional[float] = Field(None, ge=0, description="Сумма задолженности (для госпошлины)")
    contract_date: Optional[str] = Field(None, description="Дата договора")
    lat: Optional[float] = Field(None, ge=-90, le=90, description="Широта (если есть)")
    lng: Optional[float] = Field(None, ge=-180, le=180, description="Долгота (если есть)")


class BatchRequest(BaseModel):
    """Запрос на пакетную обработку."""

    debtors: list[DebtorInput] = Field(..., min_length=1, max_length=100_000)
