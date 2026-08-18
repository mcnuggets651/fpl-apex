from __future__ import annotations

from dataclasses import dataclass

TRANSFER_SPECIALIST_SOURCES = {"fabrizio_romano"}


@dataclass(frozen=True)
class TransferRiskAssessment:
    review_priority: str
    transfer_state: str
    review_reason: str
    requires_official_confirmation: bool = True


def assess_transfer_signal(
    *,
    source: str,
    signal: str,
    selected_or_sensitive: bool = False,
) -> TransferRiskAssessment:
    """Classify transfer-specialist evidence without mutating canonical projections.

    This service is intentionally diagnostic only. Transfer reports can trigger
    review/blocking attention, but official FPL/club confirmation remains the
    authority for canonical club identity, availability, minutes and xP inputs.
    """
    source_key = str(source).strip().casefold()
    if source_key not in TRANSFER_SPECIALIST_SOURCES:
        return TransferRiskAssessment("none", "unknown", "", False)

    text = " ".join(str(signal).casefold().split())
    if not text:
        return TransferRiskAssessment("none", "unknown", "")

    completed_markers = (
        "here we go",
        "deal agreed",
        "agreement reached",
        "club to club agreement",
        "medical booked",
        "medical ongoing",
        "signs for",
        "joins ",
    )
    advanced_markers = (
        "advanced talks",
        "negotiations advanced",
        "close to agreement",
        "final stages",
        "expected to leave",
        "set to leave",
        "wants the move",
    )
    exploratory_markers = (
        "interest",
        "monitoring",
        "considering",
        "in talks",
        "negotiations",
        "approach",
    )

    if any(marker in text for marker in completed_markers):
        priority = "high" if selected_or_sensitive else "medium"
        return TransferRiskAssessment(
            priority,
            "agreement_or_medical",
            "transfer-specialist evidence indicates an agreement/medical-level move; verify official club/FPL state before selection",
        )
    if any(marker in text for marker in advanced_markers):
        priority = "high" if selected_or_sensitive else "medium"
        return TransferRiskAssessment(
            priority,
            "advanced",
            "transfer-specialist evidence indicates an advanced move; review selection risk and seek official confirmation",
        )
    if any(marker in text for marker in exploratory_markers):
        priority = "medium" if selected_or_sensitive else "low"
        return TransferRiskAssessment(
            priority,
            "exploratory",
            "transfer-specialist evidence indicates transfer activity; monitor but do not mutate canonical projection inputs",
        )
    return TransferRiskAssessment("none", "unclassified", "")
