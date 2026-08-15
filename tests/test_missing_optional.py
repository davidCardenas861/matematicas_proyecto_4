from trustgraph import TrustGraphPipeline, generate_synthetic_transactions


def test_pipeline_reweights_when_optional_columns_are_missing():
    df, _ = generate_synthetic_transactions(n_clients=50, n_merchants=15, months=10, seed=3)
    df = df.drop(columns=["estado_transaccion", "mcc", "fecha_afiliacion"])
    result = TrustGraphPipeline().run(df)
    assert result.client_month["trust_score"].notna().any()
    assert result.merchant_month["trust_score"].notna().any()
