from apex_fpl.services.adversarial_certification import adversarial_certification_blockers


def _payload():
    return {
        "contract": "apex-adversarial-launch-ban-v2",
        "decision_bundle_id": "bundle",
        "targets": [
            {
                "target": "Alpha",
                "status": "optimal",
                "certified": True,
                "reality_interpretation": "genuine_value_support",
            },
            {
                "target": "Beta",
                "status": "not_in_baseline_launch",
                "certified": True,
                "reality_interpretation": "objective_neutral",
            },
        ],
        "summary": {
            "audit_complete": True,
            "search_surface_defect_signals": [],
            "ban_solve_errors": [],
        },
    }


def test_complete_stable_adversarial_report_certifies():
    assert adversarial_certification_blockers(_payload()) == ()


def test_search_surface_defect_blocks_release():
    payload = _payload()
    payload["targets"][0]["reality_interpretation"] = "search_surface_defect_signal"
    payload["summary"]["search_surface_defect_signals"] = ["Alpha"]
    blockers = adversarial_certification_blockers(payload)
    assert any("improves both" in row for row in blockers)


def test_unresolved_uncertified_and_solve_error_targets_block_release():
    payload = _payload()
    payload["targets"] = [
        {
            "target": "Alpha",
            "status": "target_not_uniquely_resolved",
            "certified": False,
            "reality_interpretation": "target_resolution_diagnostic",
        },
        {
            "target": "Beta",
            "status": "ban_solve_error",
            "certified": False,
            "reality_interpretation": "broader_candidate_instability_or_no_certified_solution",
        },
        {
            "target": "Gamma",
            "status": "optimal",
            "certified": False,
            "reality_interpretation": "broader_candidate_instability_or_no_certified_solution",
        },
    ]
    payload["summary"].update(
        {"audit_complete": False, "ban_solve_errors": ["Beta"]}
    )
    blockers = adversarial_certification_blockers(payload)
    assert any("not uniquely resolved" in row for row in blockers)
    assert any("ban solve failed" in row for row in blockers)
    assert any("not certified: Gamma" in row for row in blockers)
    assert any("did not cover" in row for row in blockers)
