"""Gini Calculator: inequality from your own data, and from published World Bank shares.

Builds on :mod:`core.inequality` (microdata Gini, Lorenz curve, shares) and adds

* validated parsing of pasted numbers or a CSV with an optional weights column,
* a seeded bootstrap confidence interval for the Gini,
* a grouped-data Gini from quintile (or decile) income shares,
* a comparison with the World Bank's published survey Gini, country by country.

Run ``python projects/004-gini-calculator/gini_calc.py`` to print the numbers quoted in the README.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from math import erf

import numpy as np
import pandas as pd
from scipy.special import erfinv
from scipy.stats import norm

from core import inequality as ineq
from core import worldbank as wb

WB_GINI = "SI.POV.GINI"
WB_QUINTILES = {
    "q1": "SI.DST.FRST.20",
    "q2": "SI.DST.02ND.20",
    "q3": "SI.DST.03RD.20",
    "q4": "SI.DST.04TH.20",
    "q5": "SI.DST.05TH.20",
}
QUINTILE_LABELS = ["Poorest 20%", "Second 20%", "Middle 20%", "Fourth 20%", "Richest 20%"]

PRESET_TEXT = {
    "Five households": "12000 18000 25000 40000 150000",
    "Textbook 1-2-3-4 (Gini = 0.25)": "1 2 3 4",
    "Perfect equality": "50000 50000 50000 50000",
}

VALUE_COLUMN_HINTS = ("income", "earnings", "wage", "salary", "value", "wealth", "y")
WEIGHT_COLUMN_HINTS = ("weight", "weights", "wt", "w", "hhweight", "pweight")


# --------------------------------------------------------------------------- parsing


class InputError(ValueError):
    """User-supplied data cannot be used. The message says what to fix."""


@dataclass(frozen=True)
class Dataset:
    """Validated observations: ``weights`` is None when every observation counts once."""

    values: np.ndarray
    weights: np.ndarray | None = None
    value_column: str | None = None
    weight_column: str | None = None


def _rows(positions: np.ndarray, offset: int = 1, limit: int = 5) -> str:
    shown = ", ".join(str(int(p) + offset) for p in positions[:limit])
    return shown + (f" and {len(positions) - limit} more" if len(positions) > limit else "")


def validate(values, weights=None) -> Dataset:
    """Check numbers are usable for a Gini and return them as a :class:`Dataset`."""
    x = np.asarray(values, dtype=float).ravel()
    if x.size < 2:
        raise InputError("Need at least 2 observations to measure inequality.")
    if not np.isfinite(x).all():
        raise InputError(f"Values must be finite numbers; check row(s) {_rows(np.flatnonzero(~np.isfinite(x)))}.")
    if (x < 0).any():
        raise InputError(
            f"Negative values are not supported (row(s) {_rows(np.flatnonzero(x < 0))}). "
            "Gini and the Lorenz curve need non-negative incomes."
        )
    if x.sum() == 0:
        raise InputError("All values are zero, so shares of total income are undefined.")
    w = None
    if weights is not None:
        w = np.asarray(weights, dtype=float).ravel()
        if w.shape != x.shape:
            raise InputError(f"Got {x.size} values but {w.size} weights; they must match.")
        if not np.isfinite(w).all() or (w <= 0).any():
            bad = np.flatnonzero(~np.isfinite(w) | (w <= 0))
            raise InputError(f"Weights must be positive numbers; check row(s) {_rows(bad)}.")
    return Dataset(values=x, weights=w)


def parse_numbers(text: str) -> Dataset:
    """Parse numbers separated by spaces, commas, semicolons or new lines.

    Do not use commas as thousands separators ("12,000" would read as 12 and 000).
    """
    tokens = [t for t in re.split(r"[\s,;]+", text.strip()) if t]
    if not tokens:
        raise InputError("No numbers found. Paste values separated by spaces, commas or new lines.")
    parsed, bad = [], []
    for token in tokens:
        try:
            parsed.append(float(token))
        except ValueError:
            bad.append(token)
    if bad:
        shown = ", ".join(repr(t) for t in bad[:4]) + (" ..." if len(bad) > 4 else "")
        verb = "entry is not a number" if len(bad) == 1 else "entries are not numbers"
        raise InputError(f"{len(bad)} {verb}: {shown}.")
    return validate(parsed)


def _detect_delimiter(text: str) -> str:
    """Most common of , ; tab | on the first non-empty line (csv.Sniffer misreads single-column files)."""
    first = next((line for line in text.splitlines() if line.strip()), "")
    counts = {d: first.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def _read_table(source) -> pd.DataFrame:
    text = source.read() if hasattr(source, "read") else source
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", errors="replace")
    delimiter = _detect_delimiter(text)
    try:
        frame = pd.read_csv(io.StringIO(text), sep=delimiter)
        # A file of bare numbers has no header: pandas then uses the first number as the column name.
        if len(frame.columns) and all(_is_number(c) for c in frame.columns):
            frame = pd.read_csv(io.StringIO(text), sep=delimiter, header=None, names=[f"column {i + 1}" for i in range(len(frame.columns))])
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise InputError(f"Could not read the file as CSV ({exc}).") from exc
    if frame.empty:
        raise InputError("The file has no data rows.")
    return frame


def _is_number(text) -> bool:
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True


def _pick_column(frame: pd.DataFrame, requested: str | None, hints: tuple[str, ...], what: str, exclude=()) -> str | None:
    if requested is not None:
        if requested not in frame.columns:
            raise InputError(f"{what} column '{requested}' not found. Columns in the file: {', '.join(map(str, frame.columns))}.")
        return requested
    lowered = {str(c).strip().lower(): c for c in frame.columns if c not in exclude}
    for hint in hints:
        if hint in lowered:
            return lowered[hint]
    return None


def _numeric_column(frame: pd.DataFrame, column: str) -> np.ndarray:
    raw = frame[column]
    numbers = pd.to_numeric(raw, errors="coerce")
    unreadable = np.flatnonzero(numbers.isna().to_numpy())
    if len(unreadable):
        # +2: one for the header line, one because people count rows from 1
        kind = "empty" if raw.iloc[unreadable[0]] is None or pd.isna(raw.iloc[unreadable[0]]) else "not a number"
        raise InputError(f"Column '{column}': {kind} in file row(s) {_rows(unreadable, offset=2)}.")
    return numbers.to_numpy(dtype=float)


def parse_csv(source, value_column: str | None = None, weight_column: str | None = None) -> Dataset:
    """Read incomes (and optional weights) from CSV text, bytes or a file-like object.

    If ``value_column`` is not given, a column named like income/earnings/wage/value is used, else the first
    numeric column. A column named weight/weights is used as weights unless ``weight_column`` says otherwise.
    """
    frame = _read_table(source)
    weight_col = _pick_column(frame, weight_column, WEIGHT_COLUMN_HINTS, "Weight")
    value_col = _pick_column(frame, value_column, VALUE_COLUMN_HINTS, "Value", exclude=(weight_col,))
    if value_col is None:
        candidates = [c for c in frame.columns if c != weight_col and pd.to_numeric(frame[c], errors="coerce").notna().any()]
        if not candidates:
            raise InputError(f"No numeric column found. Columns in the file: {', '.join(map(str, frame.columns))}.")
        value_col = candidates[0]
    values = _numeric_column(frame, value_col)
    weights = _numeric_column(frame, weight_col) if weight_col is not None else None
    checked = validate(values, weights)
    return Dataset(checked.values, checked.weights, str(value_col), None if weight_col is None else str(weight_col))


# --------------------------------------------------------------------------- bootstrap


@dataclass(frozen=True)
class GiniEstimate:
    """Point estimate with a percentile bootstrap interval, all on the 0-1 scale."""

    gini: float
    low: float
    high: float
    level: float
    n_boot: int

    @property
    def half_width(self) -> float:
        return (self.high - self.low) / 2


def bootstrap_gini(values, weights=None, *, n_boot: int = 1000, level: float = 0.95, seed: int = 0) -> GiniEstimate:
    """Gini with a percentile bootstrap confidence interval.

    Observations (with their weights) are resampled with replacement ``n_boot`` times. The random generator
    is seeded, so the same data and seed always give the same interval.
    """
    if not 0 < level < 1:
        raise ValueError("level must be between 0 and 1")
    if n_boot < 2:
        raise ValueError("n_boot must be at least 2")
    data = validate(values, weights)
    x, w = data.values, data.weights
    rng = np.random.default_rng(seed)
    draws = np.full(n_boot, np.nan)
    for b in range(n_boot):
        pick = rng.integers(0, x.size, x.size)
        try:
            draws[b] = ineq.gini(x[pick], None if w is None else w[pick])
        except ValueError:  # a resample of all zeros has no Lorenz curve
            continue
    if np.isnan(draws).all():
        raise InputError("Every bootstrap resample had zero total income; the data are too sparse for a confidence interval.")
    tail = (1 - level) / 2 * 100
    low, high = np.nanpercentile(draws, [tail, 100 - tail])
    return GiniEstimate(ineq.gini(x, w), float(low), float(high), level, n_boot)


def bootstrap_coverage(n: int, sigma: float = 0.8, *, reps: int = 150, n_boot: int = 200, level: float = 0.95, seed: int = 0) -> float:
    """Share of simulated lognormal samples whose bootstrap interval contains the true Gini.

    A well-calibrated ``level`` interval should come out close to ``level``. Small samples fall short.
    """
    truth = lognormal_gini(sigma)
    hits = 0
    for r in range(reps):
        sample = lognormal_sample(n, sigma, seed=seed + 1000 + r)
        est = bootstrap_gini(sample, n_boot=n_boot, level=level, seed=seed + r)
        hits += est.low <= truth <= est.high
    return hits / reps


# --------------------------------------------------------------------------- summary of one dataset


@dataclass(frozen=True)
class Summary:
    n: int
    gini: GiniEstimate
    shares: np.ndarray  # quintile income shares, poorest first
    top10: float
    palma: float
    grouped_gini: float  # Gini recovered from the quintile shares alone

    def table(self) -> pd.DataFrame:
        return pd.DataFrame({"Group": QUINTILE_LABELS, "Share of income": self.shares})


def summarise(values, weights=None, *, n_boot: int = 1000, level: float = 0.95, seed: int = 0) -> Summary:
    """Gini with CI, quintile shares, top-10% share, Palma ratio and the quintile-only Gini."""
    data = validate(values, weights)
    x, w = data.values, data.weights
    shares = ineq.group_shares(x, w, groups=5)
    return Summary(
        n=x.size,
        gini=bootstrap_gini(x, w, n_boot=n_boot, level=level, seed=seed),
        shares=shares,
        top10=ineq.top_share(x, w, top=0.1),
        palma=ineq.palma_ratio(x, w),
        grouped_gini=gini_from_shares(shares),
    )


# --------------------------------------------------------------------------- grouped data


def _clean_shares(shares) -> np.ndarray:
    s = np.asarray(shares, dtype=float).ravel()
    if s.size < 2:
        raise InputError("Need at least 2 income shares (for example 5 quintiles or 10 deciles).")
    if not np.isfinite(s).all() or (s < 0).any():
        raise InputError("Income shares must be non-negative numbers.")
    if s.sum() <= 0:
        raise InputError("Income shares sum to zero.")
    s = s / s.sum()  # accepts fractions or percentages, and absorbs rounding such as 99.9 or 100.2
    if (np.diff(s) < -1e-9).any():
        raise InputError("Income shares must be ordered from the poorest group to the richest, so non-decreasing.")
    return s


def lorenz_from_shares(shares) -> tuple[np.ndarray, np.ndarray]:
    """Lorenz points (population share, income share) from equal-population group shares, poorest first."""
    s = _clean_shares(shares)
    pop = np.linspace(0.0, 1.0, s.size + 1)
    inc = np.concatenate([[0.0], np.cumsum(s)])
    inc[-1] = 1.0
    return pop, inc


def gini_from_shares(shares) -> float:
    """Gini from group income shares: trapezoid area under the piecewise-linear Lorenz curve.

    With k groups the Lorenz curve is joined by straight segments, but the true curve is convex and lies
    below them. The estimate is therefore a lower bound on the Gini: it ignores inequality inside groups.
    """
    pop, inc = lorenz_from_shares(shares)
    return float(1.0 - 2.0 * np.trapezoid(inc, pop))


def grouped_gini(values, weights=None, groups: int = 5) -> float:
    """Gini that would be estimated from the ``groups`` income shares of this microdata."""
    return gini_from_shares(ineq.group_shares(values, weights, groups=groups))


# --------------------------------------------------------------------------- synthetic examples


def lognormal_sample(n: int, sigma: float, seed: int = 0) -> np.ndarray:
    """Lognormal incomes with median e**10 (about 22,000). Theoretical Gini is erf(sigma / 2)."""
    return np.random.default_rng(seed).lognormal(10.0, sigma, n)


def pareto_sample(n: int, alpha: float, seed: int = 0, minimum: float = 10_000.0) -> np.ndarray:
    """Pareto (type I) incomes above ``minimum``. Theoretical Gini is 1 / (2 alpha - 1) for alpha > 1."""
    return minimum * (1.0 + np.random.default_rng(seed).pareto(alpha, n))


def lognormal_gini(sigma: float) -> float:
    return erf(sigma / 2.0)


def pareto_gini(alpha: float) -> float:
    if alpha <= 1:
        raise ValueError("The Pareto mean is infinite for alpha <= 1, so the Gini is not defined")
    return 1.0 / (2.0 * alpha - 1.0)


def lognormal_grouped_gap(gini: float, groups: int = 5) -> float:
    """Understatement (full Gini minus grouped Gini) for a lognormal distribution with this Gini.

    The lognormal Lorenz curve is L(p) = Phi(Phi^-1(p) - sigma) and its Gini is erf(sigma / 2), so sigma
    can be recovered from a Gini and the group shares computed exactly.
    """
    sigma = 2.0 * float(erfinv(gini))
    p = np.linspace(0, 1, groups + 1)[1:-1]
    lorenz = np.concatenate([[0.0], norm.cdf(norm.ppf(p) - sigma), [1.0]])
    return gini - float(1.0 - 2.0 * np.trapezoid(lorenz, dx=1.0 / groups))


# --------------------------------------------------------------------------- World Bank


def worldbank_table(*, refresh: bool = False) -> pd.DataFrame:
    """Survey Gini and quintile shares per country-year, with the grouped estimate beside the published value.

    Columns: iso3, country, year, gini_published (0-100), q1..q5 (% of income), gini_grouped (0-100),
    gap (published minus grouped, in Gini points) and gap_pct (gap as % of the published Gini).
    Only country-years where the Gini and all five shares exist are kept.
    """
    codes = {"gini_published": WB_GINI, **WB_QUINTILES}
    wide = wb.indicators(codes, refresh=refresh).dropna().reset_index()
    wide["country"] = wide["iso3"].map(wb.names())
    shares = wide[list(WB_QUINTILES)].to_numpy()
    wide["gini_grouped"] = [gini_from_shares(row) * 100 for row in shares]
    wide["gap"] = wide["gini_published"] - wide["gini_grouped"]
    wide["gap_pct"] = wide["gap"] / wide["gini_published"] * 100
    cols = ["iso3", "country", "year", "gini_published", *WB_QUINTILES, "gini_grouped", "gap", "gap_pct"]
    return wide[cols].sort_values(["iso3", "year"]).reset_index(drop=True)


def latest_per_country(table: pd.DataFrame) -> pd.DataFrame:
    """Most recent survey year for each country."""
    return table.sort_values("year").groupby("iso3", as_index=False).tail(1).sort_values("iso3").reset_index(drop=True)


def coverage(table: pd.DataFrame) -> dict[str, float]:
    latest = latest_per_country(table)
    return {
        "country_years": len(table),
        "countries": table["iso3"].nunique(),
        "first_year": int(table["year"].min()),
        "last_year": int(table["year"].max()),
        "median_latest_year": float(latest["year"].median()),
    }


def understatement_summary(table: pd.DataFrame) -> dict[str, float]:
    """How far the grouped estimate falls below the published Gini, in Gini points (0-100 scale)."""
    gap = table["gap"]
    return {
        "n": len(table),
        "share_understated": float((gap > 0).mean()),
        "mean_gap": float(gap.mean()),
        "median_gap": float(gap.median()),
        "min_gap": float(gap.min()),
        "max_gap": float(gap.max()),
        "mean_gap_pct": float(table["gap_pct"].mean()),
        "corr_gap_gini": float(gap.corr(table["gini_published"])),
    }


def lognormal_gap_check(table: pd.DataFrame) -> dict[str, float]:
    """Compare observed gaps with those a lognormal distribution with the same Gini would produce."""
    predicted = table["gini_published"].div(100).map(lognormal_grouped_gap) * 100
    return {
        "mean_observed": float(table["gap"].mean()),
        "mean_predicted": float(predicted.mean()),
        "corr": float(table["gap"].corr(predicted)),
        "mean_abs_error": float((table["gap"] - predicted).abs().mean()),
    }


def lorenz_for_country(table: pd.DataFrame, iso3: str, year: int | None = None) -> tuple[np.ndarray, np.ndarray, int]:
    """Lorenz points from a country's quintile shares (latest year unless ``year`` is given), and that year."""
    rows = table[table["iso3"] == iso3]
    if year is not None:
        rows = rows[rows["year"] == year]
    if rows.empty:
        raise KeyError(f"No World Bank quintile data for {iso3}" + (f" in {year}" if year else ""))
    row = rows.sort_values("year").iloc[-1]
    pop, inc = lorenz_from_shares(row[list(WB_QUINTILES)].to_numpy(dtype=float))
    return pop, inc, int(row["year"])


# --------------------------------------------------------------------------- command line


def main() -> None:
    table = worldbank_table()
    cov = coverage(table)
    latest = latest_per_country(table)
    print("World Bank survey Gini and quintile shares")
    print(
        f"  {cov['country_years']} country-years, {cov['countries']} countries, "
        f"{cov['first_year']}-{cov['last_year']}, median latest survey year {cov['median_latest_year']:.0f}"
    )

    for label, frame in [("All country-years", table), ("Latest year per country", latest)]:
        s = understatement_summary(frame)
        print(f"\n{label}: grouped (quintile) Gini minus published Gini, Gini points")
        print(
            f"  n={s['n']}  understated in {s['share_understated']:.0%}  mean gap {s['mean_gap']:.2f}  "
            f"median {s['median_gap']:.2f}  range {s['min_gap']:.2f} to {s['max_gap']:.2f}  "
            f"mean {s['mean_gap_pct']:.1f}% of the published Gini  corr(gap, Gini) {s['corr_gap_gini']:.2f}"
        )

    check = lognormal_gap_check(latest)
    print(
        f"\nLognormal benchmark (latest year): observed mean gap {check['mean_observed']:.2f} vs "
        f"{check['mean_predicted']:.2f} predicted from each country's Gini alone; "
        f"corr {check['corr']:.2f}, mean absolute error {check['mean_abs_error']:.2f}"
    )

    cols = ["country", "year", "gini_published", "gini_grouped", "gap"]
    print("\nLargest gaps (latest year)")
    print(latest.nlargest(5, "gap")[cols].round(2).to_string(index=False))
    print("\nSmallest gaps (latest year)")
    print(latest.nsmallest(5, "gap")[cols].round(2).to_string(index=False))
    print("\nMost and least unequal (latest year, published Gini)")
    print(latest.nlargest(3, "gini_published")[cols].round(1).to_string(index=False))
    print(latest.nsmallest(3, "gini_published")[cols].round(1).to_string(index=False))

    print("\nSimulated incomes, n=100000, seed=0 (quintile Gini vs full Gini)")
    for label, theory, sample in [
        ("lognormal sigma=0.8", lognormal_gini(0.8), lognormal_sample(100_000, 0.8)),
        ("lognormal sigma=1.2", lognormal_gini(1.2), lognormal_sample(100_000, 1.2)),
        ("pareto alpha=3", pareto_gini(3), pareto_sample(100_000, 3)),
    ]:
        print(
            f"  {label:20s} theory {theory:.3f}  sample {ineq.gini(sample):.3f}  "
            f"from quintile shares {grouped_gini(sample):.3f}"
        )
    print("\nSample Gini of 2,000 Pareto draws across 20 seeds (heavy tails make the Gini unstable)")
    for alpha in (3.0, 1.2):
        draws = [ineq.gini(pareto_sample(2000, alpha, seed=s)) for s in range(20)]
        print(f"  alpha={alpha}: theory {pareto_gini(alpha):.3f}, sample range {min(draws):.3f} to {max(draws):.3f}")

    est = bootstrap_gini(lognormal_sample(1000, 0.8), n_boot=1000, seed=0)
    print(f"\nBootstrap 95% CI for a lognormal(0.8) sample of 1,000: {est.gini:.3f} [{est.low:.3f}, {est.high:.3f}] (theory {lognormal_gini(0.8):.3f})")
    print("Does the 95% interval contain the true Gini? (150 simulated lognormal(0.8) samples, 200 resamples each)")
    for n in (50, 200, 1000):
        print(f"  n={n:4d}: {bootstrap_coverage(n):.0%}")


if __name__ == "__main__":
    main()
