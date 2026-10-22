"""Tests for the three normalisation functions + hard gate."""

import math
import pytest
from legacy.normalize import s_benefit, s_cost, s_target, hard_gate, geometric_mean


def test_s_benefit_basic():
    assert s_benefit(0.5, 0.0, 1.0) == 50.0
    assert s_benefit(1.0, 0.0, 1.0) == 100.0
    assert s_benefit(0.0, 0.0, 1.0) == 0.0
    assert s_benefit(-0.5, 0.0, 1.0) == 0.0
    assert s_benefit(1.5, 0.0, 1.0) == 100.0


def test_s_benefit_none():
    assert s_benefit(None, 0.0, 1.0) is None
    assert s_benefit(math.nan, 0.0, 1.0) is None


def test_s_cost_basic():
    assert s_cost(0.5, 0.0, 1.0) == 50.0
    assert s_cost(0.0, 0.0, 1.0) == 100.0
    assert s_cost(1.0, 0.0, 1.0) == 0.0
    assert s_cost(2.0, 0.0, 1.0) == 0.0


def test_s_target_below_L():
    # x = 15, L = 30 → 100 * 15/30 = 50
    assert s_target(15, 30, 80, 100) == 50.0


def test_s_target_in_range():
    assert s_target(50, 30, 80, 100) == 100.0
    assert s_target(30, 30, 80, 100) == 100.0
    assert s_target(80, 30, 80, 100) == 100.0


def test_s_target_above_U():
    # x = 90, U = 80, H = 100 → 100 * (100-90)/(100-80) = 50
    assert s_target(90, 30, 80, 100) == 50.0


def test_s_target_above_H():
    assert s_target(110, 30, 80, 100) == 0.0


def test_hard_gate_pass():
    # All components >= 20 → no cap
    score = hard_gate(70.0, {"a": 30, "b": 80, "c": 50})
    assert score == 70.0


def test_hard_gate_trigger():
    # Component < 20 → cap at 1.5 * 15 = 22.5
    score = hard_gate(70.0, {"a": 15, "b": 80, "c": 50})
    assert score == 22.5


def test_geometric_mean():
    scores = {"a": 50, "b": 50}
    weights = {"a": 0.5, "b": 0.5}
    # sqrt(50 * 50) = 50
    assert abs(geometric_mean(scores, weights) - 50.0) < 0.01


def test_geometric_mean_zero():
    # If one component is 0, geometric mean ≈ 0
    scores = {"a": 0, "b": 100}
    weights = {"a": 0.5, "b": 0.5}
    assert geometric_mean(scores, weights) < 0.1