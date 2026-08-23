"""Ports and immutable capture contracts for the Apex V2 acquisition boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol

import requests

from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.ids import RawCaptureId


@dataclass(frozen=True, slots=True)
class SourceRequest:
    source_name: str
    url: str
    params: tuple[tuple[str, str], ...] = ()
    freshness_seconds: int = 1800
    schema_name: str = "raw-http-response"
    schema_version: str = "1"

    def __post_init__(self) -> None:
        if not self.source_name.strip() or not self.url.strip():
            raise ValueError("source request name/url cannot be empty")
        if self.freshness_seconds < 0:
            raise ValueError("freshness_seconds cannot be negative")
        ordered = tuple(sorted((str(key), str(value)) for key, value in self.params))
        if len({key for key, _ in ordered}) != len(ordered):
            raise ValueError("source request params must have unique keys")
        object.__setattr__(self, "source_name", self.source_name.strip())
        object.__setattr__(self, "url", self.url.strip())
        object.__setattr__(self, "params", ordered)

    @classmethod
    def create(
        cls,
        *,
        source_name: str,
        url: str,
        params: Mapping[str, object] | None = None,
        freshness_seconds: int = 1800,
        schema_name: str = "raw-http-response",
        schema_version: str = "1",
    ) -> "SourceRequest":
        return cls(
            source_name=source_name,
            url=url,
            params=tuple((str(key), str(value)) for key, value in (params or {}).items()),
            freshness_seconds=freshness_seconds,
            schema_name=schema_name,
            schema_version=schema_version,
        )

    def params_dict(self) -> dict[str, str]:
        return dict(self.params)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: bytes
    headers: Mapping[str, str]


class HttpTransport(Protocol):
    def get(self, url: str, *, params: Mapping[str, str]) -> HttpResponse: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class RequestsTransport:
    """Live adapter. It is legal only inside the acquisition boundary."""

    def __init__(self, *, timeout: int = 25, session: requests.Session | None = None):
        self.timeout = timeout
        self.session = session or requests.Session()

    def get(self, url: str, *, params: Mapping[str, str]) -> HttpResponse:
        response = self.session.get(
            url,
            params=dict(params),
            timeout=self.timeout,
            headers={"User-Agent": "apex-fpl-v2-acquisition/1"},
        )
        return HttpResponse(
            status_code=int(response.status_code),
            body=bytes(response.content),
            headers={str(key): str(value) for key, value in response.headers.items()},
        )


class NetworkAfterSealError(RuntimeError):
    """Raised by the sentinel transport if downstream computation attempts I/O."""


class SealedTransport:
    """Sentinel that can be injected in tests to prove no post-seal network path exists."""

    def get(self, url: str, *, params: Mapping[str, str]) -> HttpResponse:
        del params
        raise NetworkAfterSealError(f"network access forbidden after world seal: {url}")


def _selected_headers(headers: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    selected = {"content-type", "etag", "last-modified"}
    rows = []
    for key, value in headers.items():
        lowered = str(key).casefold()
        if lowered in selected:
            rows.append((lowered, str(value)))
    return tuple(sorted(rows))


@dataclass(frozen=True, slots=True)
class RawCapture:
    capture_id: RawCaptureId
    source_name: str
    url: str
    params: tuple[tuple[str, str], ...]
    retrieved_at: str
    freshness_seconds: int
    status_code: int
    response_headers: tuple[tuple[str, str], ...]
    body_artifact_id: str
    body_sha256: str
    body_size: int
    schema_name: str
    schema_version: str

    @classmethod
    def create(
        cls,
        *,
        request: SourceRequest,
        retrieved_at: datetime,
        response: HttpResponse,
        body_artifact_id: str,
        body_sha256: str,
        body_size: int,
    ) -> "RawCapture":
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        stamp = retrieved_at.astimezone(timezone.utc).isoformat()
        identity = {
            "schema_name": "apex-raw-capture",
            "schema_version": 1,
            "source_name": request.source_name,
            "request": {
                "method": "GET",
                "url": request.url,
                "params": [[key, value] for key, value in request.params],
            },
            "retrieved_at": stamp,
            "freshness_seconds": request.freshness_seconds,
            "status_code": int(response.status_code),
            "response_headers": [
                [key, value] for key, value in _selected_headers(response.headers)
            ],
            "body_artifact_id": body_artifact_id,
            "body_sha256": body_sha256,
            "body_size": int(body_size),
            "payload_schema": {
                "name": request.schema_name,
                "version": request.schema_version,
            },
        }
        capture_id = RawCaptureId(canonical_sha256(identity))
        return cls(
            capture_id=capture_id,
            source_name=request.source_name,
            url=request.url,
            params=request.params,
            retrieved_at=stamp,
            freshness_seconds=request.freshness_seconds,
            status_code=int(response.status_code),
            response_headers=_selected_headers(response.headers),
            body_artifact_id=body_artifact_id,
            body_sha256=body_sha256,
            body_size=int(body_size),
            schema_name=request.schema_name,
            schema_version=request.schema_version,
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-raw-capture",
            "schema_version": 1,
            "source_name": self.source_name,
            "request": {
                "method": "GET",
                "url": self.url,
                "params": [[key, value] for key, value in self.params],
            },
            "retrieved_at": self.retrieved_at,
            "freshness_seconds": self.freshness_seconds,
            "status_code": self.status_code,
            "response_headers": [[key, value] for key, value in self.response_headers],
            "body_artifact_id": self.body_artifact_id,
            "body_sha256": self.body_sha256,
            "body_size": self.body_size,
            "payload_schema": {"name": self.schema_name, "version": self.schema_version},
        }

    def as_dict(self) -> dict[str, object]:
        payload = self.identity_payload()
        payload["raw_capture_id"] = str(self.capture_id)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RawCapture":
        request = payload.get("request")
        schema = payload.get("payload_schema")
        if not isinstance(request, dict) or not isinstance(schema, dict):
            raise ValueError("raw capture request/schema metadata is missing")
        if request.get("method") != "GET":
            raise ValueError("unsupported raw capture method")
        params = request.get("params")
        headers = payload.get("response_headers")
        if not isinstance(params, list) or not isinstance(headers, list):
            raise ValueError("raw capture params/headers are invalid")
        capture = cls(
            capture_id=RawCaptureId(str(payload["raw_capture_id"])),
            source_name=str(payload["source_name"]),
            url=str(request["url"]),
            params=tuple((str(row[0]), str(row[1])) for row in params),
            retrieved_at=str(payload["retrieved_at"]),
            freshness_seconds=int(payload["freshness_seconds"]),
            status_code=int(payload["status_code"]),
            response_headers=tuple((str(row[0]), str(row[1])) for row in headers),
            body_artifact_id=str(payload["body_artifact_id"]),
            body_sha256=str(payload["body_sha256"]),
            body_size=int(payload["body_size"]),
            schema_name=str(schema["name"]),
            schema_version=str(schema["version"]),
        )
        expected = RawCaptureId(canonical_sha256(capture.identity_payload()))
        if capture.capture_id != expected:
            raise ValueError("raw capture semantic identity mismatch")
        return capture


@dataclass(frozen=True, slots=True)
class StoredRawCapture:
    capture: RawCapture
    manifest_artifact_id: str
