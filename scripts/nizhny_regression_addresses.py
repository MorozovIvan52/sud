"""
Общая выборка из 50 адресов: 25 по Нижнему Новгороду (синтетика из границ участков)
+ 25 по Нижегородской области (уникальные адреса из выгрузки dagalin).
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _street_token_plausible(p: str) -> bool:
    """
    Отсекает мусор из разбора границ: обрывки «3 (корп», только цифры, без букв.
    """
    p = p.strip()
    if len(p) < 4:
        return False
    pl = p.lower()
    if "корп" in pl or "корпус" in pl:
        return False
    if "(" in p and ")" not in p:
        return False
    if ")" in p and "(" not in p:
        return False
    if re.match(r"^\d+\s*\(", p) or re.match(r"^\d\s*\(", p):
        return False
    if re.match(r"^\d+$", p):
        return False
    if not re.search(r"[А-Яа-яЁё]", p):
        return False
    if re.fullmatch(r"[\d\s\.\-/]+", p):
        return False
    return True


def _uniq_by_address(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for r in rows:
        addr = " ".join((r.get("address") or "").split())
        if addr and addr not in seen:
            seen.add(addr)
            out.append(r)
    return out


def _collect_nn_street_addresses(root: Path, limit: int = 25) -> List[Dict[str, str]]:
    path = root / "batch_outputs" / "nizhny_sections_from_text.csv"
    if not path.exists():
        return []
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("boundary_text") or "").replace("\n", " ")
            for m in re.finditer(
                r"(?:Улицы|Улица|Проспекты|Проспект)\s*:\s*([^\\.]{8,400})",
                text,
                flags=re.IGNORECASE,
            ):
                chunk = m.group(1)
                parts = [p.strip(" .\"'()") for p in chunk.split(",")]
                for p in parts:
                    p = re.sub(r"\s*-\s*дома.*$", "", p, flags=re.IGNORECASE).strip()
                    p = re.sub(r"\s*N\s*\d+.*$", "", p, flags=re.IGNORECASE).strip()
                    if len(p) < 3:
                        continue
                    if re.search(r"район|метро|станц|посел|шоссе|переул", p, flags=re.IGNORECASE):
                        continue
                    if not _street_token_plausible(p):
                        continue
                    key = p.lower().replace("ё", "е")
                    if key in seen:
                        continue
                    seen.add(key)
                    kind = "проспект" if "просп" in m.group(0).lower() else "ул."
                    addr = f"Нижегородская обл, г Нижний Новгород, {kind} {p}, д 1"
                    out.append({"address": addr, "name": f"NN synthetic: {p}"})
                    if len(out) >= limit:
                        return out
    return out


def build_fifty_sample_addresses(root: Path) -> Tuple[List[Dict[str, str]], int, int]:
    """
    Возвращает (список {address, name}, число NN, число по области).
    Синтетика по NN: до limit валидных улиц; если в CSV много мусора, число NN может быть < limit.
    """
    src = root / "batch_outputs" / "dagalin_scrape_1774785438.json"
    if not src.exists():
        raise FileNotFoundError(f"Нужен файл выгрузки: {src}")

    data = json.loads(src.read_text(encoding="utf-8"))
    niz = [x for x in data if "Нижегородская" in (x.get("address") or "")]

    nn = _collect_nn_street_addresses(root, limit=25)
    obl = _uniq_by_address([x for x in niz if "Нижний Новгород" not in (x.get("address") or "")])[:25]
    picks: List[Dict[str, str]] = []
    for x in nn:
        picks.append({"address": x["address"], "name": x["name"]})
    for x in obl:
        picks.append(
            {
                "address": " ".join((x.get("address") or "").split()),
                "name": x.get("name") or "",
            }
        )
    return picks, len(nn), len(obl)
