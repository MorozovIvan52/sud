"""
Формирование выходного файла: XLSX и CSV с 45 полями.
Лист «Ошибки»: Номер строки | Исходный адрес | Тип ошибки | Рекомендация.
"""
import csv
from pathlib import Path
from typing import Any, List

from batch_processing.schemas.debtor_result import DEBTOR_RESULT_COLUMNS
from batch_processing.constants import get_error_code, get_recommendation, ERROR_LABELS


def _clean_result_row(r: dict) -> dict:
    """Убирает служебные поля _error_code, _original_address из строки для Excel."""
    out = {k: v for k, v in r.items() if k in DEBTOR_RESULT_COLUMNS}
    return out


def generate_xlsx(
    results: list[dict[str, str]],
    output_path: Path,
    *,
    sheet_results: str = "Результаты",
    sheet_stats: str = "Статистика",
    sheet_notes: str = "Примечания",
    sheet_errors: str = "Ошибки",
) -> Path:
    """
    Экспорт в XLSX: листы «Результаты», «Статистика», «Примечания», «Ошибки».
    """
    import pandas as pd

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    clean_results = [_clean_result_row(r) for r in results]
    df = pd.DataFrame(clean_results, columns=DEBTOR_RESULT_COLUMNS)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_results, index=False)

        # Статистика
        total = len(results)
        ok = sum(1 for r in results if r.get("Наименование суда"))
        err = total - ok
        stats = [
            {"Показатель": "Всего записей", "Значение": total},
            {"Показатель": "Успешно", "Значение": ok},
            {"Показатель": "Ошибки/пусто", "Значение": err},
        ]
        pd.DataFrame(stats).to_excel(writer, sheet_name=sheet_stats, index=False)

        # Примечания (краткий список ERROR)
        notes = [
            {"Строка": i + 1, "Тип производства": r.get("Тип производства", "")}
            for i, r in enumerate(results)
            if "ERROR" in str(r.get("Тип производства", ""))
        ]
        pd.DataFrame(notes).to_excel(writer, sheet_name=sheet_notes, index=False)

        # Ошибки (полная структура: Номер строки | Исходный адрес | Тип ошибки | Рекомендация)
        errors: List[dict] = []
        for i, r in enumerate(results):
            if "ERROR" not in str(r.get("Тип производства", "")):
                continue
            code = r.get("_error_code") or get_error_code(str(r.get("Тип производства", "")))
            errors.append({
                "Номер строки": i + 1,
                "Исходный адрес": r.get("_original_address", r.get("Нормализованный адрес", "")),
                "Тип ошибки": ERROR_LABELS.get(code, code),
                "Рекомендация": get_recommendation(code),
            })
        pd.DataFrame(errors).to_excel(writer, sheet_name=sheet_errors, index=False)

    return output_path


def generate_csv(
    results: list[dict[str, str]],
    output_path: Path,
    *,
    delimiter: str = ";",
    encoding: str = "utf-8-sig",
) -> Path:
    """Экспорт в CSV с разделителем ;."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding=encoding, newline="") as f:
        w = csv.DictWriter(f, fieldnames=DEBTOR_RESULT_COLUMNS, delimiter=delimiter)
        w.writeheader()
        for r in results:
            row = {col: (r.get(col) or "") for col in DEBTOR_RESULT_COLUMNS}
            w.writerow(row)

    return output_path
