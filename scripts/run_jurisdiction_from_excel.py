#!/usr/bin/env python3
"""
Определение подсудности по Excel (обёртка над корневым скриптом).

Рекомендуется запускать из корня проекта:
  python run_excel_jurisdiction.py файл.xlsx
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    from run_excel_jurisdiction import main

    sys.exit(main())
