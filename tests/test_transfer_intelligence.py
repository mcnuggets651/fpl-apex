from apex_fpl.services.transfer_intelligence import assess_transfer_signal


def test_here_we_go_is_high_review_for_selected_player():
    result = assess_transfer_signal(
        source="fabrizio_romano",
        signal="EXCLUSIVE: club to club agreement done, here we go! Medical ongoing.",
        selected_or_sensitive=True,
    )
    assert result.review_priority == "high"
    assert result.transfer_state == "agreement_or_medical"
    assert result.requires_official_confirmation is True


def test_exploratory_transfer_report_does_not_become_projection_override():
    result = assess_transfer_signal(
        source="fabrizio_romano",
        signal="Club monitoring the player and considering an approach.",
        selected_or_sensitive=False,
    )
    assert result.review_priority == "low"
    assert result.transfer_state == "exploratory"
    assert result.requires_official_confirmation is True


def test_unknown_source_does_not_create_transfer_risk():
    result = assess_transfer_signal(
        source="random_account",
        signal="here we go",
        selected_or_sensitive=True,
    )
    assert result.review_priority == "none"
    assert result.requires_official_confirmation is False
