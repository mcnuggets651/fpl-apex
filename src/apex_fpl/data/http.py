from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests


class CachedHttp:
    def __init__(self, cache_dir: Path, timeout: int = 25, ttl_seconds: int = 1800):
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.ttl = ttl_seconds
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return self.cache_dir / safe

    def get_json(self, url: str, key: str, force: bool = False, params: dict | None = None) -> Any:
        p = self._path(f"{key}.json")
        if not force and p.exists() and time.time() - p.stat().st_mtime < self.ttl:
            return json.loads(p.read_text())
        r = requests.get(url, params=params, timeout=self.timeout, headers={"User-Agent": "apex-fpl/0.1"})
        r.raise_for_status()
        data = r.json()
        p.write_text(json.dumps(data))
        return data

    def get_text(self, url: str, key: str, force: bool = False) -> str:
        p = self._path(key)
        if not force and p.exists() and time.time() - p.stat().st_mtime < self.ttl:
            return p.read_text()
        r = requests.get(url, timeout=self.timeout, headers={"User-Agent": "apex-fpl/0.1"})
        r.raise_for_status()
        p.write_text(r.text)
        return r.text
