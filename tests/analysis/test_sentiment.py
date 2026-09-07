from __future__ import annotations

from datetime import UTC, datetime

from moneymaker.analysis.sentiment import MODEL_NAME, score_content, score_text

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_bullish_language_scores_positive() -> None:
    polarity, confidence = score_text("Bitcoin rally continues as inflows surge")

    assert polarity > 0
    assert confidence > 0


def test_bearish_language_scores_negative() -> None:
    polarity, _ = score_text("Exchange hacked, panic selloff and liquidation")

    assert polarity < 0


def test_neutral_text_scores_zero_with_no_confidence() -> None:
    polarity, confidence = score_text("The conference is scheduled for Tuesday")

    assert polarity == 0.0
    assert confidence == 0.0


def test_negation_flips_a_term() -> None:
    plain, _ = score_text("this is a scam")
    negated, _ = score_text("this is not a scam")

    assert plain < 0
    assert negated > 0


def test_balanced_language_cancels_out() -> None:
    polarity, confidence = score_text("rally then crash")

    assert polarity == 0.0
    assert confidence > 0


def test_confidence_grows_with_the_number_of_matched_terms() -> None:
    _, few = score_text("surge")
    _, many = score_text("surge rally breakout adoption inflows")

    assert many > few
    assert many <= 1.0


def test_confidence_is_capped_at_one() -> None:
    _, confidence = score_text(" ".join(["surge"] * 50))

    assert confidence == 1.0


def test_scoring_is_case_insensitive() -> None:
    assert score_text("SURGE") == score_text("surge")


def test_score_content_wraps_the_result_in_a_domain_model() -> None:
    score = score_content("abc", "massive rally", scored_at=NOW)

    assert score.content_id == "abc"
    assert score.model == MODEL_NAME
    assert score.polarity > 0
    assert score.scored_at == NOW
