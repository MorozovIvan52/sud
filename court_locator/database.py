"""
Работа с БД: таблица court_districts (полигоны участков) и существующая courts (parser).
"""
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from court_locator import config


def _ru_lower_sql(value: Optional[str]) -> str:
    """Нижний регистр для кириллицы в SQLite (встроенный LOWER не трогает русские буквы)."""
    if value is None:
        return ""
    return str(value).lower().replace("ё", "е")


class Database:
    """
    Подключение к court_districts.sqlite (полигоны) и к courts.sqlite проекта (список судов).
    """

    def __init__(self, courts_db_path: Optional[str] = None, districts_db_path: Optional[str] = None):
        self.courts_path = Path(courts_db_path or config.COURTS_DB_PATH)
        self.districts_path = Path(districts_db_path or config.COURT_DISTRICTS_DB_PATH)
        self._conn_courts = None
        self._conn_districts = None

    def _get_courts_conn(self) -> sqlite3.Connection:
        if self._conn_courts is None:
            self.courts_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn_courts = sqlite3.connect(str(self.courts_path))
            self._conn_courts.row_factory = sqlite3.Row
        return self._conn_courts

    def _get_districts_conn(self) -> sqlite3.Connection:
        if self._conn_districts is None:
            self.districts_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn_districts = sqlite3.connect(str(self.districts_path))
            self._conn_districts.row_factory = sqlite3.Row
            self._conn_districts.create_function("ru_lower", 1, _ru_lower_sql)
        return self._conn_districts

    def _create_districts_tables(self) -> None:
        """Таблица участков с границами (GeoJSON полигоны)."""
        conn = self._get_districts_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS court_districts (
                id INTEGER PRIMARY KEY,
                district_number TEXT,
                region TEXT,
                boundaries TEXT,
                law_reference TEXT,
                address TEXT,
                phone TEXT,
                email TEXT,
                schedule TEXT,
                judge_name TEXT,
                court_name TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_court_districts_region ON court_districts(region)")
        try:
            conn.execute("ALTER TABLE court_districts ADD COLUMN last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError:
            pass
        # Миграция на email (если таблица уже создана без колонки)
        try:
            conn.execute("ALTER TABLE court_districts ADD COLUMN email TEXT")
        except sqlite3.OperationalError:
            pass
        # Миграция на law_reference (ссылка на региональный закон/НПА)
        try:
            conn.execute("ALTER TABLE court_districts ADD COLUMN law_reference TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()

    def _create_law_rules_table(self) -> None:
        """Правила текстового определения участка (без полигонов)."""
        conn = self._get_districts_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS law_rules (
                id INTEGER PRIMARY KEY,
                section_num TEXT,
                region TEXT,
                area_text TEXT,
                street_pattern TEXT,
                house_from INTEGER,
                house_to INTEGER,
                house_parity TEXT,
                house_suffix TEXT,
                house_step INTEGER,
                law_reference TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_law_rules_region ON law_rules(region)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_law_rules_section ON law_rules(section_num)")
        # migrations
        for col, ddl in [
            ("house_parity", "ALTER TABLE law_rules ADD COLUMN house_parity TEXT"),
            ("house_suffix", "ALTER TABLE law_rules ADD COLUMN house_suffix TEXT"),
            ("house_step", "ALTER TABLE law_rules ADD COLUMN house_step INTEGER"),
        ]:
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass
        conn.commit()

    def _create_dagalin_mirovye_table(self) -> None:
        """
        Справочник мировых судебных участков с dagalin.org: название и текст территориальной подсудности.
        """
        conn = self._get_districts_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dagalin_mirovye_courts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url TEXT NOT NULL UNIQUE,
                region_code TEXT,
                court_name TEXT NOT NULL,
                jurisdiction_text TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dagalin_mirovye_region ON dagalin_mirovye_courts(region_code)"
        )
        try:
            conn.execute("ALTER TABLE dagalin_mirovye_courts ADD COLUMN detail_json TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()

    def clear_dagalin_mirovye_courts(self) -> None:
        """Удаляет все строки справочника dagalin (перед полной перезаливкой)."""
        self._create_dagalin_mirovye_table()
        conn = self._get_districts_conn()
        conn.execute("DELETE FROM dagalin_mirovye_courts")
        conn.commit()

    def upsert_dagalin_mirovye_courts(self, rows: List[Dict[str, Any]]) -> None:
        """
        Вставка/обновление по source_url.
        Ожидаемые ключи: source_url, region_code, court_name, jurisdiction_text;
        опционально detail_json (не затирается при обновлении, если ключ не передан).
        """
        self._create_dagalin_mirovye_table()
        conn = self._get_districts_conn()
        for r in rows:
            dj = r.get("detail_json")
            if dj is not None and dj != "":
                conn.execute(
                    """
                    INSERT INTO dagalin_mirovye_courts (source_url, region_code, court_name, jurisdiction_text, detail_json, last_updated)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(source_url) DO UPDATE SET
                        region_code = excluded.region_code,
                        court_name = excluded.court_name,
                        jurisdiction_text = excluded.jurisdiction_text,
                        detail_json = excluded.detail_json,
                        last_updated = CURRENT_TIMESTAMP
                    """,
                    (
                        r.get("source_url") or "",
                        r.get("region_code"),
                        r.get("court_name") or "",
                        r.get("jurisdiction_text"),
                        dj,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO dagalin_mirovye_courts (source_url, region_code, court_name, jurisdiction_text, last_updated)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(source_url) DO UPDATE SET
                        region_code = excluded.region_code,
                        court_name = excluded.court_name,
                        jurisdiction_text = excluded.jurisdiction_text,
                        last_updated = CURRENT_TIMESTAMP
                    """,
                    (
                        r.get("source_url") or "",
                        r.get("region_code"),
                        r.get("court_name") or "",
                        r.get("jurisdiction_text"),
                    ),
                )
        conn.commit()

    def update_dagalin_detail_json(self, source_url: str, detail_json: str) -> None:
        """Обновить только detail_json по URL карточки dagalin."""
        if not source_url or not detail_json:
            return
        self._create_dagalin_mirovye_table()
        conn = self._get_districts_conn()
        conn.execute(
            """
            UPDATE dagalin_mirovye_courts SET detail_json = ?, last_updated = CURRENT_TIMESTAMP
            WHERE source_url = ?
            """,
            (detail_json, source_url),
        )
        conn.commit()

    def count_dagalin_mirovye_rows(self) -> int:
        """Число строк в справочнике dagalin (для автозагрузки)."""
        self._create_dagalin_mirovye_table()
        conn = self._get_districts_conn()
        cur = conn.execute("SELECT COUNT(*) FROM dagalin_mirovye_courts")
        return int(cur.fetchone()[0])

    def get_dagalin_row_by_url(self, source_url: str) -> Optional[Dict[str, Any]]:
        """Одна строка справочника dagalin по URL карточки."""
        if not source_url:
            return None
        self._create_dagalin_mirovye_table()
        conn = self._get_districts_conn()
        cur = conn.execute(
            """
            SELECT source_url, region_code, court_name, jurisdiction_text, detail_json
            FROM dagalin_mirovye_courts WHERE source_url = ? LIMIT 1
            """,
            (source_url.strip(),),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def find_dagalin_rows_by_text_tokens(self, tokens: List[str], region_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Кандидаты для поиска участка по адресу: строки, где jurisdiction_text или court_name содержат хотя бы один токен.
        """
        self._create_dagalin_mirovye_table()
        conn = self._get_districts_conn()
        tokens = [t.strip() for t in tokens if t and len(t.strip()) >= 3][:8]
        if not tokens:
            return []
        likes: List[str] = []
        params: List[str] = []
        for t in tokens:
            p = f"%{t.lower().replace('ё', 'е')}%"
            likes.append(
                "(ru_lower(jurisdiction_text) LIKE ? OR ru_lower(court_name) LIKE ?)"
            )
            params.extend([p, p])
        where = "(" + " OR ".join(likes) + ")"
        if region_code:
            where = f"({where}) AND region_code = ?"
            params.append(region_code)
        sql = f"SELECT source_url, region_code, court_name, jurisdiction_text FROM dagalin_mirovye_courts WHERE {where}"
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def find_dagalin_row_for_court(
        self, court_name: Optional[str], section_num: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Строка dagalin_mirovye_courts для живого парсинга: source_url, court_name, detail_json.
        Совпадение по точному названию или по номеру участка (даже если detail_json ещё пуст).
        """
        self._create_dagalin_mirovye_table()
        conn = self._get_districts_conn()
        cn = (court_name or "").strip()

        if cn:
            cur = conn.execute(
                """
                SELECT source_url, court_name, detail_json
                FROM dagalin_mirovye_courts
                WHERE LOWER(TRIM(court_name)) = LOWER(TRIM(?))
                LIMIT 1
                """,
                (cn,),
            )
            row = cur.fetchone()
            if row:
                return dict(row)

        sn: Optional[int] = None
        if section_num is not None:
            try:
                sn = int(section_num)
            except (TypeError, ValueError):
                sn = None
        if sn is None or sn <= 0:
            return None

        cur = conn.execute(
            """
            SELECT source_url, court_name, detail_json
            FROM dagalin_mirovye_courts
            WHERE court_name LIKE ? OR court_name LIKE ? OR court_name LIKE ? OR court_name LIKE ?
            """,
            (f"%№ {sn} %", f"%№{sn} %", f"%№ {sn},%", f"%№ {sn}.%"),
        )
        rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            return None
        if len(rows) == 1:
            return rows[0]

        cn_low = cn.lower()
        best: Optional[Dict[str, Any]] = None
        best_score = -1
        for r in rows:
            name = (r.get("court_name") or "").lower()
            score = 0
            if cn_low and cn_low == name:
                score = 10000
            elif cn_low and (cn_low in name or name in cn_low):
                score = 5000 + min(len(cn_low), len(name))
            elif cn_low:
                score = len(set(cn_low.split()) & set(name.split()))
            if score > best_score:
                best_score = score
                best = r
        return best

    def find_dagalin_detail_for_court(
        self, court_name: Optional[str], section_num: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Кэшированный detail_json (без HTTP), если строка уже была догружена."""
        row = self.find_dagalin_row_for_court(court_name, section_num)
        if not row:
            return None
        dj = row.get("detail_json")
        if not dj or not str(dj).strip():
            return None
        try:
            return json.loads(dj)
        except json.JSONDecodeError:
            return None

    def list_dagalin_urls_missing_detail(self, limit: int = 0) -> List[str]:
        """URL карточек dagalin без заполненного detail_json (для догрузки реквизитов)."""
        self._create_dagalin_mirovye_table()
        conn = self._get_districts_conn()
        sql = (
            "SELECT source_url FROM dagalin_mirovye_courts "
            "WHERE detail_json IS NULL OR TRIM(detail_json) = '' ORDER BY source_url"
        )
        if limit and limit > 0:
            cur = conn.execute(sql + " LIMIT ?", (int(limit),))
        else:
            cur = conn.execute(sql)
        return [str(r[0]) for r in cur.fetchall() if r[0]]

    def init_schema(self) -> None:
        """Создаёт таблицу court_districts при отсутствии. Таблицу courts не трогаем (её создаёт parser)."""
        self._create_districts_tables()
        self._create_law_rules_table()
        self._create_dagalin_mirovye_table()

    def get_all_districts(self) -> List[Dict[str, Any]]:
        """
        Все участки с полигонами из court_districts.
        Если записей нет — возвращает пустой список (поиск пойдёт через courts).
        """
        self._create_districts_tables()
        conn = self._get_districts_conn()
        cur = conn.execute("SELECT * FROM court_districts")
        rows = cur.fetchall()
        result = []
        for row in rows:
            r = dict(row)
            boundaries = r.get("boundaries")
            if boundaries and isinstance(boundaries, str):
                try:
                    r["boundaries"] = json.loads(boundaries)
                except json.JSONDecodeError:
                    r["boundaries"] = None
            else:
                r["boundaries"] = boundaries
            result.append(r)
        return result

    def get_courts_with_coordinates(self) -> List[Dict[str, Any]]:
        """Суды из parser/courts.sqlite с заполненным полем coordinates (для поиска ближайшего)."""
        if not self.courts_path.exists():
            return []
        conn = self._get_courts_conn()
        cur = conn.execute(
            "SELECT * FROM courts WHERE coordinates IS NOT NULL AND TRIM(coordinates) != ''"
        )
        return [dict(r) for r in cur.fetchall()]

    def get_all_courts(self) -> List[Dict[str, Any]]:
        """Все суды из parser/courts.sqlite."""
        if not self.courts_path.exists():
            return []
        conn = self._get_courts_conn()
        cur = conn.execute("SELECT * FROM courts")
        return [dict(r) for r in cur.fetchall()]

    def get_court_by_district(self, region: str, district: str) -> Optional[Dict[str, Any]]:
        """
        Суд по региону и району (совместимо с parser).
        Пробует точное совпадение, затем district + " район" (для «Новоорский» → «Новоорский район»).
        """
        if not self.courts_path.exists():
            return None
        conn = self._get_courts_conn()
        variants = [district] if district else [""]
        if district and not district.lower().endswith("район"):
            variants.append(f"{district} район")
        for d in variants:
            cur = conn.execute(
                """
                SELECT * FROM courts
                WHERE LOWER(TRIM(region)) = LOWER(TRIM(?)) AND LOWER(TRIM(COALESCE(district, ''))) = LOWER(TRIM(?))
                LIMIT 1
                """,
                (region, d or ""),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
        return None

    def update_districts(self, new_data: List[Dict[str, Any]]) -> None:
        """Обновление данных court_districts (границы участков)."""
        self._create_districts_tables()
        conn = self._get_districts_conn()
        for d in new_data:
            boundaries = d.get("boundaries")
            if isinstance(boundaries, (list, dict)):
                boundaries = json.dumps(boundaries)
            conn.execute(
                """
                INSERT OR REPLACE INTO court_districts
                (id, district_number, region, boundaries, law_reference, address, phone, email, schedule, judge_name, court_name, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    d.get("id"),
                    d.get("district_number"),
                    d.get("region"),
                    boundaries,
                    d.get("law_reference"),
                    d.get("address"),
                    d.get("phone"),
                    d.get("email"),
                    d.get("schedule"),
                    d.get("judge_name"),
                    d.get("court_name"),
                ),
            )
        conn.commit()

    def update_law_rules(self, new_rules: List[Dict[str, Any]], clear_before: bool = False) -> None:
        """Обновление таблицы law_rules."""
        self._create_law_rules_table()
        conn = self._get_districts_conn()
        if clear_before:
            conn.execute("DELETE FROM law_rules")
        for r in new_rules:
            conn.execute(
                """
                INSERT OR REPLACE INTO law_rules
                (id, section_num, region, area_text, street_pattern, house_from, house_to, house_parity, house_suffix, house_step, law_reference, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    r.get("id"),
                    r.get("section_num"),
                    r.get("region"),
                    r.get("area_text"),
                    r.get("street_pattern"),
                    r.get("house_from"),
                    r.get("house_to"),
                    r.get("house_parity"),
                    r.get("house_suffix"),
                    r.get("house_step"),
                    r.get("law_reference"),
                ),
            )
        conn.commit()

    def get_law_rules(self) -> List[Dict[str, Any]]:
        """Все правила law_rules."""
        self._create_law_rules_table()
        conn = self._get_districts_conn()
        cur = conn.execute(
            """
            SELECT id, section_num, region, area_text, street_pattern, house_from, house_to, house_parity, house_suffix, house_step, law_reference
            FROM law_rules
            """
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        if self._conn_courts:
            self._conn_courts.close()
            self._conn_courts = None
        if self._conn_districts:
            self._conn_districts.close()
            self._conn_districts = None
