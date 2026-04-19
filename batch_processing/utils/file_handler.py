"""
Чтение входных файлов CSV/XLSX для пакетной обработки.
"""
import csv
from pathlib import Path
from typing import Any, Iterator, Optional

# Ожидаемые колонки (могут быть в разном регистре/порядке)
INPUT_COLUMNS = ["fio", "фио", "address", "адрес", "passport", "паспорт", "debt_amount", "сумма", "contract_date", "дата"]


def _normalize_col(name: str) -> str:
    """Нормализация названия колонки для сопоставления."""
    n = (name or "").strip().lower()
    mapping = {
        "фио": "fio",
        "ф.и.о": "fio",
        "адрес": "address",
        "адрес регистрации": "address",
        "паспорт": "passport",
        "сумма": "debt_amount",
        "сумма долга": "debt_amount",
        "сумма иска": "debt_amount",
        "claim_amount": "debt_amount",
        "дата": "contract_date",
        "дата договора": "contract_date",
        "широта": "lat",
        "latitude": "lat",
        "долгота": "lng",
        "lon": "lng",
        "longitude": "lng",
        "тип дела": "case_type",
        "case_type": "case_type",
        "id": "id",
        "id дела": "id",
        "номер договора": "contract_number",
        "contract_number": "contract_number",
    }
    return mapping.get(n, n)


def read_csv(path: Path, *, encoding: str = "utf-8-sig", delimiter: str = ";") -> list[dict[str, Any]]:
    """Читает CSV, возвращает список dict с ключами fio, address, passport, debt_amount, lat, lng."""
    path = Path(path)
    rows = []
    with path.open("r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            normalized = _normalize_row(row)
            if normalized.get("fio") or normalized.get("address"):
                rows.append(normalized)
    return rows


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Приводит строку к стандартным ключам: id, contract_number, fio, address, passport, debt_amount, case_type, lat, lng."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        col = _normalize_col(str(k))
        if col == "id":
            out["id"] = str(v).strip() if v is not None else ""
        elif col == "contract_number":
            out["contract_number"] = str(v).strip() if v is not None else ""
        elif col == "fio":
            out["fio"] = str(v).strip() if v is not None and str(v).strip() else out.get("fio", "")
        elif col == "address":
            out["address"] = str(v).strip() if v is not None and str(v).strip() else out.get("address", "")
        elif col == "passport":
            out["passport"] = str(v).strip() if v is not None else ""
        elif col == "contract_date":
            out["contract_date"] = str(v).strip() if v is not None else ""
        elif col == "debt_amount":
            try:
                out["debt_amount"] = float(str(v).replace(",", ".").replace(" ", "")) if v else None
            except (ValueError, TypeError):
                out["debt_amount"] = None
        elif col == "lat":
            try:
                out["lat"] = float(str(v).replace(",", ".")) if v else None
            except (ValueError, TypeError):
                out["lat"] = None
        elif col == "lng":
            try:
                out["lng"] = float(str(v).replace(",", ".")) if v else None
            except (ValueError, TypeError):
                out["lng"] = None
        elif col == "case_type":
            out["case_type"] = str(v).strip() if v is not None else ""
    return out


# --- GPS-only режим (без парсинга адресов) ---

def _validate_coord(value: Any, name: str, min_val: float, max_val: float) -> tuple[bool, float | None]:
    """Валидация координаты. Возвращает (ok, value)."""
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return False, None
    try:
        v = float(str(value).replace(",", "."))
        if min_val <= v <= max_val:
            return True, v
    except (ValueError, TypeError):
        pass
    return False, None


def validate_coordinates(lat: Any, lon: Any) -> tuple[bool, str]:
    """
    Проверка формата и диапазона координат WGS84.
    Возвращает (ok, error_message).
    """
    ok_lat, lat_val = _validate_coord(lat, "lat", -90, 90)
    ok_lon, lon_val = _validate_coord(lon, "lon", -180, 180)
    if not ok_lat:
        return False, f"Некорректная широта: {lat} (ожидается -90..90)"
    if not ok_lon:
        return False, f"Некорректная долгота: {lon} (ожидается -180..180)"
    return True, ""


def read_csv_gps(path: Path, *, encoding: str = "utf-8-sig", delimiter: Optional[str] = None) -> list[dict[str, Any]]:
    """Читает CSV с колонками lat/lon (или широта/долгота). Возвращает список dict с lat, lng, case_type, debt_amount."""
    path = Path(path)
    rows = []
    with path.open("r", encoding=encoding, newline="") as f:
        first_line = f.readline()
        if delimiter is None:
            delimiter = ";" if ";" in first_line else ","
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delimiter)
        for i, row in enumerate(reader):
            normalized = _normalize_row(row)
            lat, lon = normalized.get("lat"), normalized.get("lng")
            ok, _ = validate_coordinates(lat, lon)
            if ok:
                normalized["_row"] = i + 2  # 1-based + header
                rows.append(normalized)
    return rows


def read_xlsx_gps(path: Path) -> list[dict[str, Any]]:
    """Читает XLSX с колонками lat/lon."""
    import pandas as pd

    path = Path(path)
    df = pd.read_excel(path, sheet_name=0, header=0)
    rows = []
    for i, r in df.iterrows():
        row = {str(k): v for k, v in r.items()}
        normalized = _normalize_row(row)
        lat, lon = normalized.get("lat"), normalized.get("lng")
        ok, _ = validate_coordinates(lat, lon)
        if ok:
            normalized["_row"] = int(i) + 2
            rows.append(normalized)
    return rows


def read_geojson(path: Path) -> list[dict[str, Any]]:
    """Читает GeoJSON FeatureCollection. Извлекает Point coordinates [lon, lat] и properties."""
    import json

    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    features = data.get("features", [])
    for i, f in enumerate(features):
        geom = f.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        ok, _ = validate_coordinates(lat, lon)
        if not ok:
            continue
        props = f.get("properties") or {}
        debt = props.get("debt_amount", props.get("сумма"))
        if debt is not None:
            try:
                debt = float(debt)
            except (TypeError, ValueError):
                debt = None
        rows.append({
            "lat": lat,
            "lng": lon,
            "case_type": str(props.get("case_type", props.get("тип_дела", "")) or ""),
            "debt_amount": debt,
            "_row": i + 1,
        })
    return rows


def _elem_local_tag(elem) -> str:
    """Локальное имя тега без namespace."""
    tag = getattr(elem, "tag", "")
    return tag.split("}")[-1] if "}" in str(tag) else tag


def read_kml(path: Path) -> list[dict[str, Any]]:
    """Читает KML, извлекает координаты из Placemark."""
    from xml.etree import ElementTree as ET

    path = Path(path)
    tree = ET.parse(path)
    root = tree.getroot()

    rows = []
    for elem in root.iter():
        if _elem_local_tag(elem) != "Placemark":
            continue
        coords_el = None
        name_el = None
        for child in elem.iter():
            if _elem_local_tag(child) == "coordinates":
                coords_el = child
                break
        if coords_el is None or not (coords_el.text or "").strip():
            continue
        parts = coords_el.text.strip().replace(",", " ").split()
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        ok, _ = validate_coordinates(lat, lon)
        if not ok:
            continue
        for child in elem.iter():
            if _elem_local_tag(child) == "name":
                name_el = child
                break
        name = name_el.text.strip() if name_el is not None and name_el.text else ""
        rows.append({
            "lat": lat,
            "lng": lon,
            "case_type": name,
            "debt_amount": None,
            "_row": i + 1,
        })
    return rows


def read_file_gps(path: Path) -> list[dict[str, Any]]:
    """Читает файл с координатами по расширению: CSV, XLSX, GeoJSON, KML."""
    path = Path(path)
    suf = path.suffix.lower()
    if suf == ".csv":
        return read_csv_gps(path)
    if suf in (".xlsx", ".xls"):
        return read_xlsx_gps(path)
    if suf == ".geojson" or path.name.endswith(".geojson"):
        return read_geojson(path)
    if suf == ".kml":
        return read_kml(path)
    if suf == ".json":
        try:
            return read_geojson(path)
        except Exception:
            raise ValueError("JSON не является GeoJSON FeatureCollection")
    raise ValueError(f"Неподдерживаемый формат для GPS: {suf}. Используйте CSV, XLSX, GeoJSON, KML.")


def read_xlsx(path: Path) -> list[dict[str, Any]]:
    """Читает первый лист XLSX, возвращает список dict."""
    import pandas as pd

    path = Path(path)
    df = pd.read_excel(path, sheet_name=0, header=0)
    rows = []
    for _, r in df.iterrows():
        row = {str(k): v for k, v in r.items()}
        normalized = _normalize_row(row)
        if normalized.get("fio") or normalized.get("address"):
            rows.append(normalized)
    return rows


def read_file(path: Path) -> list[dict[str, Any]]:
    """Читает CSV или XLSX по расширению."""
    path = Path(path)
    suf = path.suffix.lower()
    if suf == ".csv":
        return read_csv(path)
    if suf in (".xlsx", ".xls"):
        return read_xlsx(path)
    raise ValueError(f"Неподдерживаемый формат: {suf}")
