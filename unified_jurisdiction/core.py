"""
UnifiedJurisdictionCore: шаги A–D поверх существующего court_locator + PostGIS.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from unified_jurisdiction.cache_layer import UnifiedCache, cache_key_for_address, cache_key_for_coordinates
from unified_jurisdiction.court_name_normalize import normalize_court_name
from unified_jurisdiction.models import FindCourtRequest, FindCourtResponse, UnifiedAddress
from unified_jurisdiction.normalizer import normalize_to_unified
from unified_jurisdiction.voting import (
    ResolutionOutcome,
    WeightedSourceVote,
    jurisdiction_min_confidence_sum,
    resolve_weighted_votes,
)

from court_locator.config import use_postgis_for_spatial_search
from court_locator.dagalin_enrich import enrich_court_with_dagalin
from court_locator.log_sanitize import redact_secrets

logger = logging.getLogger("unified_jurisdiction.core")
_ROOT = Path(__file__).resolve().parent.parent


def _skip_external_geo() -> bool:
    """SKIP_EXTERNAL_GEO=1|true|yes|on — не вызывать внешний геокод в шаге C (Nominatim/Yandex и т.д.)."""
    v = (os.getenv("SKIP_EXTERNAL_GEO") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _ensure_paths():
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))


def _confidence_score(source: str, steps: List[str]) -> Optional[float]:
    s = (source or "").lower()
    if "dagalin_address_match" in s:
        return 0.86
    if "dadata" in s:
        return 0.97
    if "district" in s or "unified_a" in s:
        return 0.9
    if "postgis" in s or "court_districts" in s or "unified_c" in s:
        return 0.92
    if "nearest" in s or "courts_geo" in s:
        return 0.65
    if "coordinates_district" in s or "reverse" in s:
        return 0.88
    if any("C:geocoded" in st for st in steps):
        return 0.85
    return 0.8 if steps else None


def _effective_prefer_dadata(request_value: bool) -> bool:
    v = (os.getenv("UNIFIED_PREFER_DADATA_COURT") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return request_value


def _court_names_conflict(a: Optional[Dict], b: Optional[Dict]) -> bool:
    if not a or not b:
        return False
    na = (a.get("court_name") or "").strip().lower()
    nb = (b.get("court_name") or "").strip().lower()
    if not na or not nb:
        return False
    return na != nb


def _section_meta_court_id(section_num: Any) -> Optional[str]:
    if section_num is None:
        return None
    try:
        return str(int(section_num))
    except (TypeError, ValueError):
        s = str(section_num).strip()
        return s or None


def build_weighted_votes_for_address_branch(
    court_a: Optional[Dict[str, Any]],
    court_b: Optional[Dict[str, Any]],
    court_c: Optional[Dict[str, Any]],
    court_d: Optional[Dict[str, Any]],
) -> List[WeightedSourceVote]:
    """
    Собирает голоса для текстового адреса: C (пространственный), B (DaData), D (Dagalin), A (БД района).
    Веса: полигон/postgis 1.0; coordinates_district 0.95; прочий spatial fallback 0.45; DaData 0.8; Dagalin 0.5; БД района 0.3.
    """
    votes: List[WeightedSourceVote] = []
    if court_c:
        name = (court_c.get("court_name") or "").strip()
        if name:
            src = str(court_c.get("source") or "")
            if src == "court_districts" or "postgis" in src.lower():
                tag, w = "polygon", 1.0
            elif src == "coordinates_district":
                tag, w = "polygon", 0.95
            else:
                tag, w = "spatial", 0.45
            meta = {
                "court_id": _section_meta_court_id(court_c.get("section_num")),
                "spatial_source": src,
            }
            votes.append(
                WeightedSourceVote(
                    source=tag,
                    court_name=name,
                    weight=w,
                    court_key=normalize_court_name(name),
                    meta=meta,
                )
            )
    if court_b:
        name = (court_b.get("court_name") or "").strip()
        if name:
            votes.append(
                WeightedSourceVote(
                    source="dadata",
                    court_name=name,
                    weight=0.8,
                    court_key=normalize_court_name(name),
                    meta={"court_id": _section_meta_court_id(court_b.get("section_num"))},
                )
            )
    if court_d:
        name = (court_d.get("court_name") or "").strip()
        if name:
            votes.append(
                WeightedSourceVote(
                    source="dagalin",
                    court_name=name,
                    weight=0.5,
                    court_key=normalize_court_name(name),
                    meta={"court_id": _section_meta_court_id(court_d.get("section_num"))},
                )
            )
    if court_a:
        name = (court_a.get("court_name") or "").strip()
        if name:
            votes.append(
                WeightedSourceVote(
                    source="district_db",
                    court_name=name,
                    weight=0.3,
                    court_key=normalize_court_name(name),
                    meta={"court_id": _section_meta_court_id(court_a.get("section_num"))},
                )
            )
    return votes


def _warn_normalized_key_collisions(votes: List[WeightedSourceVote]) -> None:
    """Предупреждение: один court_key после нормализации из разных строк названия (типичная коллизия по номеру)."""
    by_key: Dict[str, List[str]] = defaultdict(list)
    for v in votes:
        if v.court_key:
            by_key[v.court_key].append(v.court_name)
    for key, names in by_key.items():
        uniq = {n.strip() for n in names if (n or "").strip()}
        if len(uniq) > 1:
            logger.warning(
                "jurisdiction: court_key=%r совпал для разных исходных названий (проверьте регион/район в ключе): %s",
                key,
                sorted(uniq),
            )


def _log_jurisdiction_votes_debug(
    address: str,
    votes: List[WeightedSourceVote],
    outcome: ResolutionOutcome,
    selected_court_id: Optional[str],
) -> None:
    """Детальные логи для отладки «почему needs_manual_review» (уровень DEBUG)."""
    logger.debug(
        "jurisdiction min confidence sum (JURISDICTION_MIN_CONFIDENCE_SUM) = %.2f",
        jurisdiction_min_confidence_sum(),
    )
    collected = [
        {
            "source": v.source,
            "court_name": v.court_name,
            "court_key": v.court_key,
            "weight": v.weight,
            "court_id": (v.meta or {}).get("court_id"),
        }
        for v in votes
    ]
    logger.debug("Sources collected for address %r (n=%s): %s", address, len(votes), collected)
    for v in votes:
        logger.debug(
            "vote normalize: source=%s before=%r after_key=%r weight=%s",
            v.source,
            v.court_name,
            v.court_key or "",
            v.weight,
        )
    _warn_normalized_key_collisions(votes)
    keys = [v.court_key for v in votes if v.court_key]
    if len(keys) > 1 and len(set(keys)) < len(keys):
        logger.warning(
            "jurisdiction: повторяющиеся court_key среди голосов (согласованность источников): %s",
            keys,
        )
    logger.info(
        "Voting result: address=%r selected_court_id=%s court_key=%s confidence=%.2f reason=%r "
        "manual_review=%s weight_sum_by_key=%s",
        address,
        selected_court_id,
        outcome.court_key,
        outcome.confidence_score,
        outcome.reason,
        outcome.needs_manual_review,
        outcome.weight_sum_by_key,
    )


def match_outcome_to_court_dict(
    outcome_court_key: Optional[str],
    court_d: Optional[Dict[str, Any]],
    court_b: Optional[Dict[str, Any]],
    court_c: Optional[Dict[str, Any]],
    court_a: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Первый кандидат с тем же court_key, что у итога голосования (порядок: Dagalin, DaData, spatial, район)."""
    if not outcome_court_key:
        return None
    for c in (court_d, court_b, court_c, court_a):
        if not c:
            continue
        nm = (c.get("court_name") or "").strip()
        if nm and normalize_court_name(nm) == outcome_court_key:
            return c
    return None


class UnifiedJurisdictionCore:
    def __init__(self, use_cache: bool = True):
        _ensure_paths()
        self._use_cache = use_cache
        self._cache = UnifiedCache() if use_cache else None
        from court_locator.database import Database
        from court_locator.court_matcher import CourtMatcher

        self._db = Database()
        self._db.init_schema()
        self._matcher = CourtMatcher(self._db)

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:
            pass

    def find_court(self, req: FindCourtRequest) -> FindCourtResponse:
        t0 = time.perf_counter()
        res = self._find_court_inner(req)
        ms = round((time.perf_counter() - t0) * 1000, 2)
        res.metrics = {**(res.metrics or {}), "total_ms": ms}
        if res.success and res.court and not res.source_votes:
            res.confidence_score = _confidence_score(
                str(res.court.get("source") or ""),
                res.resolution_steps,
            )
        return res

    def _find_court_inner(self, req: FindCourtRequest) -> FindCourtResponse:
        steps: list[str] = []
        unified: Optional[UnifiedAddress] = None

        lat, lng = req.latitude, req.longitude
        if lat is not None and lng is not None:
            try:
                lat, lng = float(lat), float(lng)
            except (TypeError, ValueError):
                return FindCourtResponse(success=False, error="Некорректные координаты")
            cache_key = cache_key_for_coordinates(lat, lng)
            if self._cache:
                hit = self._cache.get(cache_key)
                if hit:
                    c = hit.get("court")
                    if isinstance(c, dict):
                        enrich_court_with_dagalin(c, self._db)
                    return FindCourtResponse(
                        success=True,
                        court=c,
                        resolution_steps=["cache:coordinates"],
                    )
            court, steps_coord = self._spatial_pipeline(lat, lng, address_for_log=None)
            enrich_court_with_dagalin(court, self._db)
            if self._cache and court:
                self._cache.set(cache_key, {"court": court})
            return FindCourtResponse(
                success=bool(court),
                court=court,
                unified_address=None,
                resolution_steps=steps_coord,
                needs_manual_review=bool(court and court.get("needs_manual_review")),
                error=None if court else "Суд по координатам не найден",
            )

        address = (req.address or "").strip()
        if not address:
            return FindCourtResponse(success=False, error="Не указан адрес и координаты")

        unified = normalize_to_unified(address)
        cache_key = cache_key_for_address(unified.normalized)
        if self._cache:
            hit = self._cache.get(cache_key)
            if hit:
                c = hit.get("court")
                if isinstance(c, dict):
                    enrich_court_with_dagalin(c, self._db)
                return FindCourtResponse(
                    success=True,
                    court=c,
                    unified_address=unified,
                    resolution_steps=["cache:address"],
                )

        prefer_dadata = _effective_prefer_dadata(req.prefer_dadata_court)
        dadata_ok = getattr(self._matcher, "_dadata_available", False)

        court_d: Optional[Dict[str, Any]] = None
        try:
            from court_locator.dagalin_address_search import find_court_by_dagalin_address_index

            court_d = find_court_by_dagalin_address_index(self._db, unified)
            if court_d:
                steps.append("D:dagalin_address_index")
        except Exception as e:
            logger.warning("dagalin address index: %s", str(e)[:240])

        court_a: Optional[Dict[str, Any]] = None
        court_b: Optional[Dict[str, Any]] = None

        if prefer_dadata and dadata_ok:
            court_b = self._step_b(unified)
            if court_b:
                steps.append("B:dadata")
            else:
                steps.append("B:dadata_empty")
            court_a = self._step_a(unified)
            if court_a:
                steps.append("A:district_db")
            if court_b and court_a and _court_names_conflict(court_b, court_a):
                logger.warning(
                    "unified_jurisdiction: DaData и БД по району расходятся; приоритет DaData (prefer_dadata_court)"
                )
        else:
            court_a = self._step_a(unified)
            if court_a:
                steps.append("A:district_db")
            if (not court_a or req.strict_verify) and dadata_ok:
                court_b = self._step_b(unified)
                if court_b:
                    steps.append("B:dadata")

        court_c: Optional[Dict[str, Any]] = None
        need_spatial = (not court_a and not court_b) or req.strict_verify
        if need_spatial:
            court_c, sub = self._step_c_spatial(unified.normalized)
            steps.extend(sub)

        manual = False
        spatial_override = False
        if req.strict_verify and court_c:
            legacy_final = court_c
            if _court_names_conflict(court_a, court_c) or _court_names_conflict(court_b, court_c):
                manual = True
                spatial_override = True
            self._merge_sparse_from_dagalin(legacy_final, court_d)
        elif court_d:
            legacy_final = court_d
            self._fill_dagalin_from_alternates(legacy_final, court_a, court_b, court_c)
        elif prefer_dadata and court_b:
            legacy_final = court_b
        elif court_a:
            legacy_final = court_a
        elif court_b:
            legacy_final = court_b
        elif court_c:
            legacy_final = court_c
        else:
            legacy_final = None

        votes = build_weighted_votes_for_address_branch(court_a, court_b, court_c, court_d)
        outcome = resolve_weighted_votes(votes)
        source_vote_dicts = [
            {
                "source": v.source,
                "court_key": v.court_key,
                "weight": v.weight,
                "court_id": (v.meta or {}).get("court_id"),
            }
            for v in votes
        ]
        selected_court_id: Optional[str] = None
        if outcome.court_key:
            for v in votes:
                if v.court_key == outcome.court_key:
                    cid = (v.meta or {}).get("court_id")
                    if cid:
                        selected_court_id = str(cid)
                        break

        if req.strict_verify and court_c:
            final = legacy_final
        else:
            matched = match_outcome_to_court_dict(
                outcome.court_key, court_d, court_b, court_c, court_a
            )
            final = matched if matched is not None else legacy_final

        if court_d and final is court_d:
            self._fill_dagalin_from_alternates(final, court_a, court_b, court_c)

        if final and final.get("source") in ("courts_nearest", "courts_geo"):
            logger.warning(
                "unified_jurisdiction: fallback nearest court (manual review recommended) source=%s region=%s",
                final.get("source"),
                final.get("region"),
            )
            manual = True

        enrich_court_with_dagalin(final, self._db)
        if self._cache and final:
            self._cache.set(cache_key, {"court": final})

        try:
            from court_locator import config as cl_config

            yx = (getattr(cl_config, "YANDEX_GEO_KEY", None) or "").strip()
            y_src = getattr(cl_config, "YANDEX_GEO_KEY_SOURCE", "?")
            y_env = getattr(cl_config, "YANDEX_GEO_KEY_ENV", "") or "-"
            yandex_diag = f"{y_src}<-{y_env}" if yx else "NONE"
        except Exception:
            yandex_diag = "?"
        logger.info(
            "find_court finished address normalized_len=%s resolution_steps=%s success=%s yandex_geo=%s",
            len(unified.normalized or ""),
            steps,
            bool(final),
            yandex_diag,
        )
        _log_jurisdiction_votes_debug(
            unified.raw or unified.normalized or "",
            votes,
            outcome,
            selected_court_id,
        )

        conf_voting: Optional[float] = outcome.confidence_score
        needs_from_votes = outcome.needs_manual_review

        return FindCourtResponse(
            success=bool(final),
            court=final,
            unified_address=unified,
            resolution_steps=steps,
            needs_manual_review=manual
            or needs_from_votes
            or bool(final and final.get("needs_manual_review")),
            spatial_override=spatial_override,
            error=None if final else "Суд не найден",
            confidence_score=conf_voting,
            resolution_reason=outcome.reason,
            source_votes=source_vote_dicts,
            selected_court_id=selected_court_id,
        )

    def _fill_dagalin_from_alternates(
        self,
        base: Dict[str, Any],
        court_a: Optional[Dict[str, Any]],
        court_b: Optional[Dict[str, Any]],
        court_c: Optional[Dict[str, Any]],
    ) -> None:
        """Дополняет ответ dagalin пустыми полями из БД/DaData/геокода."""
        for alt in (court_c, court_b, court_a):
            if not alt:
                continue
            for k in ("address", "phone", "email", "postal_index", "judge_name", "region", "district"):
                v = alt.get(k)
                if v and not str(base.get(k) or "").strip():
                    base[k] = v
            sn = alt.get("section_num")
            if sn is not None:
                try:
                    sni = int(sn)
                    if sni > 0 and int(base.get("section_num") or 0) == 0:
                        base["section_num"] = sni
                except (TypeError, ValueError):
                    pass

    def _merge_sparse_from_dagalin(
        self, primary: Optional[Dict[str, Any]], dagalin: Optional[Dict[str, Any]]
    ) -> None:
        """При приоритете геокода — подтянуть с dagalin расширенные блоки, если в primary пусто."""
        if not primary or not dagalin:
            return
        for k in ("superior_court", "state_fee_requisites", "bailiffs"):
            blk = dagalin.get(k)
            if isinstance(blk, dict) and blk and not primary.get(k):
                primary[k] = dict(blk)

    def _step_a(self, u: UnifiedAddress) -> Optional[Dict[str, Any]]:
        if not u.region or not u.district:
            return None
        row = self._db.get_court_by_district(u.region, u.district)
        if not row:
            return None
        from court_locator.utils import court_row_to_result

        return court_row_to_result(row, "unified_A_district")

    def _step_b(self, u: UnifiedAddress) -> Optional[Dict[str, Any]]:
        try:
            from court_locator import config
        except Exception:
            return None
        token = (getattr(config, "DADATA_TOKEN", None) or "").strip()
        if not token:
            return None
        try:
            from court_locator.parser_bridge import dadata_find_court_by_address

            row = dadata_find_court_by_address(u.normalized, region=u.region, token=token)
        except Exception as e:
            logger.warning("unified step B DaData: %s", str(e)[:200])
            row = None
        if not row or not row.get("court_name"):
            return None
        from court_locator.utils import court_row_to_result

        return court_row_to_result(row, "unified_B_dadata")

    def _step_c_spatial(self, normalized_address: str) -> Tuple[Optional[Dict[str, Any]], list[str]]:
        steps: list[str] = []
        if _skip_external_geo():
            steps.append("C:skipped_external_geo")
            return None, steps
        gr = self._matcher.gps.geocode_with_verification(normalized_address)
        if not gr:
            steps.append("C:geocode_failed")
            return None, steps
        steps.append("C:geocoded")
        lat, lon = gr.lat, gr.lon

        if use_postgis_for_spatial_search():
            try:
                from court_locator.postgis_adapter import find_court_by_coordinates_postgis, is_postgis_available

                if is_postgis_available():
                    row = find_court_by_coordinates_postgis(lat, lon)
                    if row:
                        from court_locator.utils import court_row_to_result

                        steps.append("C:postgis")
                        c = court_row_to_result(row, "unified_C_postgis")
                        c["confidence"] = gr.confidence
                        c["geocode_source"] = gr.source
                        return c, steps
            except Exception as e:
                logger.warning("unified step C PostGIS: %s", redact_secrets(str(e)))

        court = self._matcher.find_court_by_coordinates(lat, lon)
        if court:
            court["confidence"] = getattr(gr, "confidence", None)
            court["geocode_source"] = getattr(gr, "source", None)
            src = court.get("source", "")
            if src == "court_districts":
                steps.append("C:sqlite_districts")
            elif src == "postgis":
                steps.append("C:postgis")
            elif src == "coordinates_district":
                steps.append("C:reverse_geocode_district")
            else:
                steps.append(f"C:spatial:{src}")
        return court, steps

    def _spatial_pipeline(
        self,
        lat: float,
        lng: float,
        address_for_log: Optional[str],
    ) -> Tuple[Optional[Dict[str, Any]], list[str]]:
        steps: list[str] = ["coords_only"]
        court = self._matcher.find_court_by_coordinates(lat, lng)
        if court:
            steps.append(court.get("source") or "matcher")
        return court, steps
