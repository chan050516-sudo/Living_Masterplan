"""Tests for Shannon diversity index."""

from app.derived.diversity import shannon_diversity


def test_single_subtype():
    assert shannon_diversity(["a", "a", "a"]) == 0.0


def test_uniform_two():
    assert abs(shannon_diversity(["a", "b"]) - 1.0) < 0.001


def test_uniform_four():
    assert abs(shannon_diversity(["a", "b", "c", "d"]) - 1.0) < 0.001


def test_skewed():
    # 3 of "a", 1 of "b" → entropy is between 0 and 1
    s = shannon_diversity(["a", "a", "a", "b"])
    assert 0.0 < s < 1.0