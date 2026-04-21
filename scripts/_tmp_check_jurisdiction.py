# Temporary: batch jurisdiction check (delete after use if desired)
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "court_locator"))

from court_locator.database import Database
from court_locator.law_rules import LawRuleMatcher

ADDRESSES = [
    "г. Нижний Новгород, ш. Казанское, д. 14к3",
    "г. Нижний Новгород, ул. Рождественская, д. 19",
    "г. Нижний Новгород, ул. Большая Печерская, д. 10",
    "г. Нижний Новгород, ул. Октябрьская, д. 5",
    "г. Нижний Новгород, пр. Молодежный, д. 31",
    "г. Нижний Новгород, пр. Ильича, д. 40",
    "г. Нижний Новгород, ул. Белинского, д. 12",
    "г. Нижний Новгород, ул. Варварская, д. 8",
    "г. Нижний Новгород, ул. Пискунова, д. 22",
    "г. Нижний Новгород, ул. Ковалихинская, д. 5",
    "г. Нижний Новгород, ул. Германа Лопатина, д. 3",
    "г. Нижний Новгород, пл. Минина и Пожарского, д. 1",
    "г. Нижний Новгород, ул. Кожевенная, д. 15",
    "Нижегородская обл., г. Арзамас, ул. Ленина, д. 20",
    "Нижегородская обл., г. Арзамас, ул. Московская, д. 5",
    "Нижегородская обл., г. Дзержинск, ул. Циолковского, д. 30",
    "Нижегородская обл., г. Бор, ул. Ленина, д. 10",
    "Нижегородская обл., г. Кстово, ул. Базовая, д. 5",
    "Нижегородская обл., г. Саров, ул. Гоголя, д. 7",
    "Нижегородская обл., рп. Воротынец, ул. М. Горького, д. 50",
    "Нижегородская обл., г. Лысково, ул. Строителей, д. 5",
]

PREFIX = "Нижегородская область, "


def main() -> None:
    db = Database()
    rules = db.get_law_rules()
    kazan_rows = [r for r in rules if "азан" in (r.get("street_pattern") or "").lower()]
    print(f"law_rules total: {len(rules)}, rules with 'азан' in pattern: {len(kazan_rows)}")
    if kazan_rows[:3]:
        for r in kazan_rows[:5]:
            print("  ", r.get("section_num"), r.get("street_pattern")[:80])

    matcher = LawRuleMatcher(db)
    print("(только law_rules, без геокодера)")
    print()
    for a in ADDRESSES:
        full = a if "Нижегородская" in a else PREFIX + a
        r = matcher.match(full)
        if r:
            name = r.get("court_name") or ""
            src = r.get("source") or r.get("match_source") or "law_rules"
            sec = r.get("section_num") or ""
            print(f"OK  [{src}] уч.{sec}: {name[:75]}")
            print(f"     {a}")
        else:
            print(f"--- None: {a}")
        print()

    db.close()


def dump_kazan_patterns() -> None:
    import json

    db = Database()
    rows = db.get_law_rules()
    hit = [r for r in rows if "казан" in (r.get("street_pattern") or "").lower()]
    print(json.dumps(hit, ensure_ascii=False, indent=2)[:2000])
    db.close()


if __name__ == "__main__":
    main()
    print("--- dump patterns containing 'казан':")
    dump_kazan_patterns()
