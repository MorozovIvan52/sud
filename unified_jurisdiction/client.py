"""
SDK: локальное ядро или HTTP-клиент к REST API.
"""
from __future__ import annotations

import os
from typing import Optional

from unified_jurisdiction.models import FindCourtRequest, FindCourtResponse


class UnifiedJurisdictionClient:
    """
    :param base_url: если задан (например http://127.0.0.1:8010), запросы идут на POST /api/v1/find-court
    :param use_cache: для режима local — кэш в UnifiedJurisdictionCore
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        use_cache: bool = True,
    ):
        self.base_url = (base_url or os.getenv("UNIFIED_JURISDICTION_API_URL") or "").rstrip("/")
        self._use_cache = use_cache
        self._core = None

    def find_court(self, req: FindCourtRequest) -> FindCourtResponse:
        if self.base_url:
            return self._find_http(req)
        return self._find_local(req)

    def _find_local(self, req: FindCourtRequest) -> FindCourtResponse:
        from unified_jurisdiction.core import UnifiedJurisdictionCore

        if self._core is None:
            self._core = UnifiedJurisdictionCore(use_cache=self._use_cache)
        return self._core.find_court(req)

    def _find_http(self, req: FindCourtRequest) -> FindCourtResponse:
        import urllib.error
        import urllib.request

        import json

        url = f"{self.base_url}/api/v1/find-court"
        body = {
            "address": req.address,
            "latitude": req.latitude,
            "longitude": req.longitude,
            "strict_verify": req.strict_verify,
            "prefer_dadata_court": req.prefer_dadata_court,
        }
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        http_req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8")
                payload = json.loads(raw)
            except Exception:
                return FindCourtResponse(success=False, error=f"HTTP {e.code}")
            if e.code == 400 and isinstance(payload, dict) and "detail" in payload:
                return FindCourtResponse(success=False, error=str(payload["detail"]))
            return FindCourtResponse(success=False, error=str(payload))
        except Exception as e:
            return FindCourtResponse(success=False, error=str(e))

        from unified_jurisdiction.models import UnifiedAddress

        ua = None
        if payload.get("unified_address"):
            d = payload["unified_address"]
            ua = UnifiedAddress(
                raw=d.get("raw") or "",
                normalized=d.get("normalized") or "",
                region=d.get("region"),
                district=d.get("district"),
                settlement=d.get("settlement"),
                street=d.get("street"),
                house=d.get("house"),
                latitude=d.get("latitude"),
                longitude=d.get("longitude"),
            )
        metrics = payload.get("metrics")
        if metrics is not None and not isinstance(metrics, dict):
            metrics = None
        return FindCourtResponse(
            success=bool(payload.get("success")),
            court=payload.get("court"),
            unified_address=ua,
            resolution_steps=list(payload.get("resolution_steps") or []),
            needs_manual_review=bool(payload.get("needs_manual_review")),
            spatial_override=bool(payload.get("spatial_override")),
            error=payload.get("error"),
            confidence_score=payload.get("confidence_score"),
            metrics=metrics,
        )

    def close(self) -> None:
        if self._core:
            try:
                self._core.close()
            except Exception:
                pass
            self._core = None
