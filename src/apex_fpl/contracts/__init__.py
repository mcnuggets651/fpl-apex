"""Versioned, read-only interoperability contracts exported by Apex FPL."""

from apex_fpl.contracts.football_intelligence import (
    CONTRACT_VERSION,
    FootballIntelligenceContractError,
    build_football_intelligence_snapshot,
    write_football_intelligence_snapshot,
)

__all__ = [
    "CONTRACT_VERSION",
    "FootballIntelligenceContractError",
    "build_football_intelligence_snapshot",
    "write_football_intelligence_snapshot",
]
