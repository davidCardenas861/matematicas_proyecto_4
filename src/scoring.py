from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_mean(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    available = [c for c in cols if c in df.columns]
    if not available:
        return pd.Series(np.nan, index=df.index)
    return df[available].mean(axis=1, skipna=True)


def _bounded_ratio_score(s: pd.Series) -> pd.Series:
    return (100 * s.astype(float).clip(0, 1)).where(s.notna())


def _inverse_cv_score(s: pd.Series) -> pd.Series:
    # Smooth mapping: CV=0 -> 100, CV=1 -> 50, CV=3 -> 25.
    s = s.astype(float).clip(lower=0)
    return 100 / (1 + s)


def _adaptive_weighted_score(
    dimensions: pd.DataFrame,
    weights: dict[str, float],
) -> pd.Series:
    num = pd.Series(0.0, index=dimensions.index)
    den = pd.Series(0.0, index=dimensions.index)
    for dim, weight in weights.items():
        if dim not in dimensions.columns:
            continue
        valid = dimensions[dim].notna()
        num.loc[valid] += dimensions.loc[valid, dim] * float(weight)
        den.loc[valid] += float(weight)
    return (num / den.replace(0, np.nan)).clip(0, 100)


def _score_band(score: pd.Series, bands: dict[str, float]) -> pd.Series:
    vh = bands.get("very_high", 85)
    hi = bands.get("high", 70)
    md = bands.get("medium", 50)
    return pd.cut(
        score,
        bins=[-np.inf, md, hi, vh, np.inf],
        labels=["low", "medium", "high", "very_high"],
        right=False,
    ).astype("string")


def score_clients(
    panel: pd.DataFrame,
    weights: dict[str, float],
    bands: dict[str, float],
    rolling_medium: int = 6,
    rolling_long: int = 12,
) -> pd.DataFrame:
    out = panel.copy()

    persistence = _bounded_ratio_score(out.get(f"active_month_ratio_{rolling_long}m", pd.Series(np.nan, index=out.index)))

    stability_parts = []
    for c in [f"tx_cv_{rolling_medium}m", f"amount_cv_{rolling_medium}m", f"ticket_cv_{rolling_medium}m"]:
        if c in out.columns:
            stability_parts.append(_inverse_cv_score(out[c]).rename(c))
    stability = pd.concat(stability_parts, axis=1).mean(axis=1) if stability_parts else pd.Series(np.nan, index=out.index)

    if "approval_rate" in out.columns:
        quality = _bounded_ratio_score(out["approval_rate"])
    else:
        quality = pd.Series(np.nan, index=out.index)

    fidelity = _safe_mean(out.assign(
        persistent_score=_bounded_ratio_score(out.get("persistent_merchant_ratio", pd.Series(np.nan, index=out.index))),
        relationship_score=out.get("avg_relationship_strength", pd.Series(np.nan, index=out.index)),
    ), ["persistent_score", "relationship_score"])

    dims = pd.DataFrame({
        "persistence": persistence,
        "stability": stability,
        "quality": quality,
        "relationship_fidelity": fidelity,
    }, index=out.index)

    for c in dims.columns:
        out[f"score_{c}"] = dims[c]
    out["trust_score"] = _adaptive_weighted_score(dims, weights)
    out["trust_band"] = _score_band(out["trust_score"], bands)
    out["trust_change_1m"] = out.groupby("client_id")["trust_score"].diff()
    out["trust_change_3m"] = out.groupby("client_id")["trust_score"].diff(3)
    return out


def score_merchants(
    panel: pd.DataFrame,
    weights: dict[str, float],
    bands: dict[str, float],
    rolling_medium: int = 6,
    rolling_long: int = 12,
) -> pd.DataFrame:
    out = panel.copy()
    persistence = _bounded_ratio_score(out.get(f"active_month_ratio_{rolling_long}m", pd.Series(np.nan, index=out.index)))

    stability_parts = []
    for c in [f"tx_cv_{rolling_medium}m", f"amount_cv_{rolling_medium}m", f"ticket_cv_{rolling_medium}m"]:
        if c in out.columns:
            stability_parts.append(_inverse_cv_score(out[c]).rename(c))
    stability = pd.concat(stability_parts, axis=1).mean(axis=1) if stability_parts else pd.Series(np.nan, index=out.index)

    quality = _bounded_ratio_score(out["approval_rate"]) if "approval_rate" in out.columns else pd.Series(np.nan, index=out.index)
    recurrence = _safe_mean(out.assign(
        repeat_score=_bounded_ratio_score(out.get("repeat_customer_rate", pd.Series(np.nan, index=out.index))),
        relationship_score=out.get("avg_relationship_strength", pd.Series(np.nan, index=out.index)),
    ), ["repeat_score", "relationship_score"])

    diversification = 100 * (1 - out.get("client_hhi", pd.Series(np.nan, index=out.index)).clip(0, 1))

    dims = pd.DataFrame({
        "persistence": persistence,
        "stability": stability,
        "quality": quality,
        "customer_recurrence": recurrence,
        "diversification": diversification,
    }, index=out.index)

    for c in dims.columns:
        out[f"score_{c}"] = dims[c]
    out["trust_score"] = _adaptive_weighted_score(dims, weights)
    out["trust_band"] = _score_band(out["trust_score"], bands)
    out["trust_change_1m"] = out.groupby("merchant_id")["trust_score"].diff()
    out["trust_change_3m"] = out.groupby("merchant_id")["trust_score"].diff(3)
    return out
