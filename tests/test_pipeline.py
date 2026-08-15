import numpy as np

from trustgraph import TrustGraphPipeline, generate_synthetic_transactions


def test_pipeline_runs_end_to_end():
    df, _ = generate_synthetic_transactions(n_clients=80, n_merchants=20, months=12, seed=7)
    result = TrustGraphPipeline().run(df)

    assert not result.client_month.empty
    assert not result.merchant_month.empty
    assert not result.relationship_month.empty
    assert result.client_month["trust_score"].dropna().between(0, 100).all()
    assert result.merchant_month["trust_score"].dropna().between(0, 100).all()
    assert result.graph.number_of_nodes() > 0
    assert result.graph.number_of_edges() > 0


def test_deterioration_signal_has_negative_trust_change_on_average():
    df, meta = generate_synthetic_transactions(n_clients=160, n_merchants=30, months=18, seed=42)
    result = TrustGraphPipeline().run(df)
    cm = result.client_month
    last = cm[cm["month"] == cm["month"].max()].copy()
    last["is_deteriorating"] = last["client_id"].isin(meta.deteriorating_clients)

    det = last.loc[last["is_deteriorating"], "trust_change_3m"].dropna().mean()
    stable = last.loc[~last["is_deteriorating"], "trust_change_3m"].dropna().mean()
    assert np.isfinite(det)
    assert det < stable
