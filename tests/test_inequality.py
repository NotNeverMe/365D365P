import numpy as np
import pytest

from core import inequality as ineq


def test_perfect_equality_has_zero_gini():
    assert ineq.gini([10, 10, 10, 10]) == pytest.approx(0.0, abs=1e-12)


def test_one_person_holds_everything():
    n = 1000
    values = np.zeros(n)
    values[-1] = 1.0
    assert ineq.gini(values) == pytest.approx(1 - 1 / n, abs=1e-9)


def test_known_small_sample():
    # Textbook example: incomes 1,2,3,4 -> Gini = 0.25
    assert ineq.gini([1, 2, 3, 4]) == pytest.approx(0.25)


def test_scale_invariant_and_order_invariant():
    rng = np.random.default_rng(0)
    x = rng.lognormal(10, 1, 500)
    assert ineq.gini(x) == pytest.approx(ineq.gini(x * 37.5))
    assert ineq.gini(x) == pytest.approx(ineq.gini(rng.permutation(x)))


def test_lognormal_matches_theory():
    # Gini of a lognormal with sigma s is erf(s / 2).
    from math import erf

    rng = np.random.default_rng(1)
    x = rng.lognormal(0, 0.8, 200_000)
    assert ineq.gini(x) == pytest.approx(erf(0.8 / 2), abs=0.005)


def test_weights_equal_duplication():
    assert ineq.gini([1, 5], weights=[3, 1]) == pytest.approx(ineq.gini([1, 1, 1, 5]))


def test_lorenz_endpoints():
    pop, inc = ineq.lorenz_curve([3, 1, 2])
    assert (pop[0], inc[0]) == (0.0, 0.0)
    assert (pop[-1], inc[-1]) == (pytest.approx(1.0), pytest.approx(1.0))


def test_group_shares_sum_to_one():
    shares = ineq.group_shares(np.arange(1, 101), groups=5)
    assert shares.sum() == pytest.approx(1.0)
    assert (np.diff(shares) > 0).all()


def test_top_share_and_palma():
    x = np.arange(1, 101)
    assert 0.18 < ineq.top_share(x, top=0.1) < 0.20
    assert ineq.palma_ratio(x) > 1


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        ineq.gini([1, -2, 3])
    with pytest.raises(ValueError):
        ineq.gini([])
    with pytest.raises(ValueError):
        ineq.gini([0, 0, 0])
