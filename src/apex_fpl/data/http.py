from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests


class CachedHttp:
    def __init__(
        self,
        cache_dir: Path,
        timeout: int = 25,
        ttl_seconds: int = 1800,
        stale_if_error_seconds: int = 7200,
    ):
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.ttl = ttl_seconds
        self.stale_if_error = stale_if_error_seconds
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return self.cache_dir / safe

    @staticmethod
    def _age_seconds(path: Path) -> float:
        return time.time() - path.stat().st_mtime

    def _can_use_stale_on_error(self, path: Path, force: bool) -> bool:
        return (
            force
            and path.exists()
            and self.stale_if_error >= 0
            and self._age_seconds(path) <= self.stale_if_error
        )

    def get_json(self, url: str, key: str, force: bool = False, params: dict | None = None) -> Any:
        p = self._path(f"{key}.json")
        if not force and p.exists() and self._age_seconds(p) < self.ttl:
            return json.loads(p.read_text())
        try:
            r = requests.get(
                url,
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": "apex-fpl/0.1"},
            )
            r.raise_for_status()
        except requests.RequestException:
            if self._can_use_stale_on_error(p, force):
                return json.loads(p.read_text())
            raise
        data = r.json()
        p.write_text(json.dumps(data))
        return data

    def get_text(self, url: str, key: str, force: bool = False) -> str:
        p = self._path(key)
        if not force and p.exists() and self._age_seconds(p) < self.ttl:
            return p.read_text()
        try:
            r = requests.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": "apex-fpl/0.1"},
            )
            r.raise_for_status()
        except requests.RequestException:
            if self._can_use_stale_on_error(p, force):
                return p.read_text()
            raise
        p.write_text(r.text)
        return r.text
