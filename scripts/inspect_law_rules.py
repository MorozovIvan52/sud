from __future__ import annotations

import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from court_locator.database import Database


def main() -> None:
    db = Database()
    db.init_schema()
    rules = db.get_law_rules()
    print("rules count:", len(rules))
    vat = [r for r in rules if "Ватутина" in (r.get("street_pattern") or "")]
    print("Vatuina rules:", vat[:3])
    db.close()


if __name__ == "__main__":
    main()
