"""Stable provider-neutral ports for Apex V2 production backends."""

from __future__ import annotations

from typing import Protocol

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.release_registry import ReleaseKey, ReleaseRecord
from apex_fpl.core.production_authority_root import ProductionAuthorityRoot


class ProductionReleaseRegistry(Protocol):
    """Durable shared registry required by production cutover."""

    backend_id: str

    def append(self, record: ReleaseRecord) -> ReleaseRecord: ...

    def read_release(self, release_id: str) -> ReleaseRecord: ...

    def current_release_id(self, key: ReleaseKey) -> str | None: ...

    def compare_and_swap_current(
        self,
        key: ReleaseKey,
        *,
        expected_release_id: str | None,
        new_release_id: str,
    ) -> None: ...


class ProductionAuthorityRootRegistry(Protocol):
    """Dedicated immutable authority-root history and season-level CAS pointer."""

    backend_id: str

    def append(self, root: ProductionAuthorityRoot) -> ProductionAuthorityRoot: ...

    def read_root(self, root_id: str) -> ProductionAuthorityRoot: ...

    def current_root_id(self, season: str) -> str | None: ...

    def compare_and_swap_current(
        self,
        season: str,
        *,
        expected_root_id: str | None,
        new_root_id: str,
    ) -> None: ...


class ReopenableArtifactStore(ArtifactStore, Protocol):
    """ArtifactStore that can open a fresh independent adapter to the same backend."""

    backend_id: str

    def reopen(self) -> "ReopenableArtifactStore": ...


class ReopenableReleaseRegistry(ProductionReleaseRegistry, Protocol):
    """Release registry that can open a fresh adapter to the same shared backend."""

    def reopen(self) -> "ReopenableReleaseRegistry": ...


class ReopenableAuthorityRootRegistry(ProductionAuthorityRootRegistry, Protocol):
    """Authority-root registry that can reopen an independent shared-backend adapter."""

    def reopen(self) -> "ReopenableAuthorityRootRegistry": ...
