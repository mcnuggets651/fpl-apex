from __future__ import annotations

from dataclasses import dataclass

from apex_fpl.services.finalized_stability import optimise_with_bounded_stability_retry


@dataclass(frozen=True)
class Candidate:
    squad_ids: tuple[int, ...]
    within_gw1_band: bool = True


@dataclass(frozen=True)
class Result:
    status: str
    selected: Candidate | None
    candidate_pool_stable: bool
    small_pool_selected_ids: tuple[int, ...] | None
    full_pool_selected_ids: tuple[int, ...] | None
    note: str = ""


def test_narrow_stable_flag_cannot_skip_broader_certification() -> None:
    calls: list[int] = []

    def optimiser(*args, **kwargs):
        limit = int(kwargs.get("exact_candidate_limit", 16))
        calls.append(limit)
        if limit <= 16:
            return Result(
                status="optimal",
                selected=Candidate((1, 2, 3)),
                candidate_pool_stable=True,
                small_pool_selected_ids=(1, 2, 3),
                full_pool_selected_ids=(1, 2, 3),
                note="narrow claims stable",
            )
        return Result(
            status="optimal",
            selected=Candidate((1, 2, 4)),
            candidate_pool_stable=True,
            small_pool_selected_ids=(1, 2, 4),
            full_pool_selected_ids=(1, 2, 4),
            note="broader winner",
        )

    result = optimise_with_bounded_stability_retry(
        optimiser,
        exact_candidate_limit=16,
        retry_exact_candidate_limit=24,
    )

    assert calls == [16, 24]
    assert result.selected is not None
    assert result.selected.squad_ids == (1, 2, 4)
    assert result.candidate_pool_stable is True
    assert "winner_changed=true" in result.note
