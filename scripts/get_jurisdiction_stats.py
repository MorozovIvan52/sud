#!/usr/bin/env python3
"""
Вывод статистики системы определения подсудности (MetricsCollector).
Запуск после обработки батча: python scripts/get_jurisdiction_stats.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from batch_processing.services.metrics_collector import get_metrics_collector


def main():
    collector = get_metrics_collector()
    stats = collector.get_statistics()
    print("=== Статистика определения подсудности ===\n")
    print(f"Всего запросов:    {stats['total_requests']}")
    print(f"Успешно:           {stats['success_count']}")
    print(f"Ошибки:            {stats['failure_count']}")
    print(f"Точность (success): {stats['success_rate']:.1%}")
    print(f"Среднее время:     {stats['average_time_ms']:.2f} мс")
    if stats["error_distribution"]:
        print("\nРаспределение ошибок:")
        for code, count in sorted(stats["error_distribution"].items(), key=lambda x: -x[1]):
            print(f"  {code}: {count}")
    if stats["source_performance"]:
        print("\nПо источникам:")
        for src, count in sorted(stats["source_performance"].items(), key=lambda x: -x[1]):
            print(f"  {src}: {count}")
    if stats["district_performance"]:
        print("\nПо районам (топ-10):")
        for dist, count in sorted(stats["district_performance"].items(), key=lambda x: -x[1])[:10]:
            print(f"  {dist}: {count}")
    print()
    if "--json" in sys.argv:
        print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
