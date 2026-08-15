from __future__ import annotations

import numpy as np
import pandas as pd


def _status_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "status" not in out.columns:
        out["is_approved"] = np.nan
        out["is_rejected"] = np.nan
        return out

    s = out["status"].astype(str).str.strip().str.lower()
    approved_tokens = {"approved", "aprobada", "aprobado", "ok", "success", "1", "true"}
    rejected_tokens = {"rejected", "rechazada", "rechazado", "declined", "denied", "0", "false"}
    out["is_approved"] = s.isin(approved_tokens).astype(float)
    out["is_rejected"] = s.isin(rejected_tokens).astype(float)

    unknown = ~(s.isin(approved_tokens | rejected_tokens))
    out.loc[unknown, ["is_approved", "is_rejected"]] = np.nan
    return out


def _rolling_cv(s: pd.Series, window: int, min_periods: int = 3) -> pd.Series:
    mean = s.rolling(window, min_periods=min_periods).mean().abs()
    std = s.rolling(window, min_periods=min_periods).std(ddof=0)
    return std / mean.replace(0, np.nan)


def _add_history_features(
    panel: pd.DataFrame,
    id_col: str,
    rolling_short: int,
    rolling_medium: int,
    rolling_long: int,
    min_history: int,
) -> pd.DataFrame:
    panel = panel.sort_values([id_col, "month"]).copy()
    g = panel.groupby(id_col, group_keys=False)

    panel["tx_mom"] = g["tx_count"].pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    panel["amount_mom"] = g["amount_sum"].pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)

    for w in [rolling_short, rolling_medium, rolling_long]:
        panel[f"tx_cv_{w}m"] = g["tx_count"].transform(
            lambda s: _rolling_cv(s, w, min_history)
        )
        panel[f"amount_cv_{w}m"] = g["amount_sum"].transform(
            lambda s: _rolling_cv(s, w, min_history)
        )
        panel[f"ticket_cv_{w}m"] = g["ticket_avg"].transform(
            lambda s: _rolling_cv(s, w, min_history)
        )
        panel[f"active_month_ratio_{w}m"] = g["tx_count"].transform(
            lambda s: s.gt(0).rolling(w, min_periods=1).mean()
        )

    return panel


def build_relationship_month(
    tx: pd.DataFrame,
    relationship_window: int = 6,
) -> pd.DataFrame:
    """Build one row per client-merchant-month and relationship persistence features."""
    x = _status_flags(tx)
    agg = x.groupby(["client_id", "merchant_id", "month"], as_index=False).agg(
        tx_count=("transaction_date", "size"),
        amount_sum=("amount", "sum"),
        amount_mean=("amount", "mean"),
        active_days=("transaction_date", lambda s: s.dt.date.nunique()),
        approval_rate=("is_approved", "mean"),
        rejection_rate=("is_rejected", "mean"),
    )

    client_month = agg.groupby(["client_id", "month"], as_index=False).agg(
        client_tx=("tx_count", "sum"),
        client_amount=("amount_sum", "sum"),
    )
    merchant_month = agg.groupby(["merchant_id", "month"], as_index=False).agg(
        merchant_tx=("tx_count", "sum"),
        merchant_amount=("amount_sum", "sum"),
    )
    agg = agg.merge(client_month, on=["client_id", "month"], how="left")
    agg = agg.merge(merchant_month, on=["merchant_id", "month"], how="left")
    agg["client_tx_share"] = agg["tx_count"] / agg["client_tx"].replace(0, np.nan)
    agg["client_amount_share"] = agg["amount_sum"] / agg["client_amount"].replace(0, np.nan)
    agg["merchant_tx_share"] = agg["tx_count"] / agg["merchant_tx"].replace(0, np.nan)

    # Build full monthly presence only for months between first and last observed transaction.
    agg = agg.sort_values(["client_id", "merchant_id", "month"])
    agg["relation_active_month_ratio"] = (
        agg.groupby(["client_id", "merchant_id"])["month"]
        .transform(lambda s: pd.Series(1.0, index=s.index).rolling(relationship_window, min_periods=1).mean())
    )
    # Above would always be 1 on sparse observations; compute persistence from calendar month gaps instead.
    def relation_history(group: pd.DataFrame) -> pd.DataFrame:
        keys = getattr(group, "name", (None, None))
        group = group.sort_values("month").copy()
        if "client_id" not in group.columns:
            group["client_id"] = keys[0]
        if "merchant_id" not in group.columns:
            group["merchant_id"] = keys[1]
        months = group["month"].tolist()
        ratios, streaks, ages = [], [], []
        for idx, m in enumerate(months):
            start = (m.to_period("M") - (relationship_window - 1)).to_timestamp()
            active = [d for d in months[: idx + 1] if start <= d <= m]
            ratios.append(len(set(active)) / relationship_window)

            streak = 1
            cur = m.to_period("M")
            active_periods = {d.to_period("M") for d in months[: idx + 1]}
            while (cur - streak) in active_periods and streak < relationship_window:
                streak += 1
            streaks.append(streak)
            ages.append((m.to_period("M") - months[0].to_period("M")).n + 1)
        group["relation_active_month_ratio"] = ratios
        group["relation_streak_months"] = streaks
        group["relation_age_months"] = ages
        return group

    agg = (
        agg.groupby(["client_id", "merchant_id"], group_keys=False)
        .apply(relation_history, include_groups=False)
        .reset_index(drop=True)
    )
    agg["relationship_strength"] = 100 * (
        0.40 * agg["relation_active_month_ratio"].clip(0, 1)
        + 0.25 * agg["client_tx_share"].fillna(0).clip(0, 1)
        + 0.20 * agg["client_amount_share"].fillna(0).clip(0, 1)
        + 0.15 * (agg["relation_streak_months"] / relationship_window).clip(0, 1)
    )
    return agg


def build_client_month(
    tx: pd.DataFrame,
    relationship: pd.DataFrame,
    rolling_short: int = 3,
    rolling_medium: int = 6,
    rolling_long: int = 12,
    min_history: int = 3,
) -> pd.DataFrame:
    x = _status_flags(tx)
    aggs = {
        "tx_count": ("transaction_date", "size"),
        "amount_sum": ("amount", "sum"),
        "ticket_avg": ("amount", "mean"),
        "active_days": ("transaction_date", lambda s: s.dt.date.nunique()),
        "unique_merchants": ("merchant_id", "nunique"),
        "approval_rate": ("is_approved", "mean"),
        "rejection_rate": ("is_rejected", "mean"),
    }
    if "merchant_category" in x.columns:
        aggs["unique_categories"] = ("merchant_category", "nunique")

    panel = x.groupby(["client_id", "month"], as_index=False).agg(**aggs)

    rel = relationship.copy()
    rel["is_persistent_relation"] = rel["relation_active_month_ratio"] >= (2 / 6)
    rel_summary = rel.groupby(["client_id", "month"], as_index=False).agg(
        avg_relationship_strength=("relationship_strength", "mean"),
        max_relationship_strength=("relationship_strength", "max"),
        persistent_merchants=("is_persistent_relation", "sum"),
        max_merchant_tx_share=("client_tx_share", "max"),
    )
    rel_summary["persistent_merchant_ratio"] = (
        rel_summary["persistent_merchants"]
        / panel.set_index(["client_id", "month"])["unique_merchants"].reindex(
            pd.MultiIndex.from_frame(rel_summary[["client_id", "month"]])
        ).to_numpy()
    )
    panel = panel.merge(rel_summary, on=["client_id", "month"], how="left")

    if "client_affiliation_date" in x.columns:
        aff = x.groupby("client_id", as_index=False)["client_affiliation_date"].min()
        panel = panel.merge(aff, on="client_id", how="left")
        panel["tenure_months"] = (
            panel["month"].dt.to_period("M") - panel["client_affiliation_date"].dt.to_period("M")
        ).apply(lambda p: p.n if pd.notna(p) else np.nan)

    panel = _add_history_features(
        panel, "client_id", rolling_short, rolling_medium, rolling_long, min_history
    )
    return panel


def build_merchant_month(
    tx: pd.DataFrame,
    relationship: pd.DataFrame,
    rolling_short: int = 3,
    rolling_medium: int = 6,
    rolling_long: int = 12,
    min_history: int = 3,
) -> pd.DataFrame:
    x = _status_flags(tx)
    panel = x.groupby(["merchant_id", "month"], as_index=False).agg(
        tx_count=("transaction_date", "size"),
        amount_sum=("amount", "sum"),
        ticket_avg=("amount", "mean"),
        active_days=("transaction_date", lambda s: s.dt.date.nunique()),
        unique_clients=("client_id", "nunique"),
        approval_rate=("is_approved", "mean"),
        rejection_rate=("is_rejected", "mean"),
    )

    rel = relationship.copy()
    rel["is_recurrent_client"] = rel["relation_active_month_ratio"] >= (2 / 6)
    merchant_rel = rel.groupby(["merchant_id", "month"], as_index=False).agg(
        recurrent_clients=("is_recurrent_client", "sum"),
        avg_relationship_strength=("relationship_strength", "mean"),
        max_client_tx_share=("merchant_tx_share", "max"),
    )
    panel = panel.merge(merchant_rel, on=["merchant_id", "month"], how="left")
    panel["repeat_customer_rate"] = panel["recurrent_clients"] / panel["unique_clients"].replace(0, np.nan)

    # HHI by client share of merchant transaction count; lower HHI = more diversified.
    hhi = (
        rel.assign(sq=lambda d: d["merchant_tx_share"].fillna(0) ** 2)
        .groupby(["merchant_id", "month"], as_index=False)["sq"].sum()
        .rename(columns={"sq": "client_hhi"})
    )
    panel = panel.merge(hhi, on=["merchant_id", "month"], how="left")

    if "merchant_category" in x.columns:
        cat = x.groupby("merchant_id", as_index=False)["merchant_category"].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]
        )
        panel = panel.merge(cat, on="merchant_id", how="left")

    if "merchant_nit" in x.columns:
        nit = x.groupby("merchant_id", as_index=False)["merchant_nit"].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]
        )
        panel = panel.merge(nit, on="merchant_id", how="left")

    if "merchant_affiliation_date" in x.columns:
        aff = x.groupby("merchant_id", as_index=False)["merchant_affiliation_date"].min()
        panel = panel.merge(aff, on="merchant_id", how="left")
        panel["tenure_months"] = (
            panel["month"].dt.to_period("M") - panel["merchant_affiliation_date"].dt.to_period("M")
        ).apply(lambda p: p.n if pd.notna(p) else np.nan)

    panel = _add_history_features(
        panel, "merchant_id", rolling_short, rolling_medium, rolling_long, min_history
    )
    return panel
