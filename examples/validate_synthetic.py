from __future__ import annotations

import json
from pathlib import Path

from trustgraph import TrustGraphPipeline, generate_synthetic_transactions


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "synthetic_sample.csv"
OUTPUT_DIR = ROOT / "outputs" / "synthetic_demo"
REPORT_PATH = OUTPUT_DIR / "validation_report.json"


def main() -> None:
    df, meta = generate_synthetic_transactions(
        n_clients=300,
        n_merchants=50,
        months=18,
        seed=42,
    )
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_PATH, index=False)

    pipeline = TrustGraphPipeline.from_yaml(ROOT / "config" / "default.yaml")
    result = pipeline.run(df)
    pipeline.save(result, OUTPUT_DIR)

    latest_month = result.client_month["month"].max()
    c = result.client_month[result.client_month["month"] == latest_month].copy()
    c["synthetic_deteriorating"] = c["client_id"].isin(meta.deteriorating_clients)
    client_delta = c.groupby("synthetic_deteriorating")["trust_change_3m"].mean().to_dict()

    m = result.merchant_month[result.merchant_month["month"] == latest_month].copy()
    m["synthetic_deteriorating"] = m["merchant_id"].isin(meta.deteriorating_merchants)
    merchant_delta = m.groupby("synthetic_deteriorating")["trust_change_3m"].mean().to_dict()

    rel = result.relationship_month
    old_strength = rel.loc[rel["relation_age_months"] >= 6, "relationship_strength"].mean()
    new_strength = rel.loc[rel["relation_age_months"] == 1, "relationship_strength"].mean()

    checks = {
        "required_schema_detected": all(
            role in result.schema.mapping for role in ["client_id", "merchant_id", "transaction_date"]
        ),
        "client_scores_in_0_100": bool(result.client_month["trust_score"].dropna().between(0, 100).all()),
        "merchant_scores_in_0_100": bool(result.merchant_month["trust_score"].dropna().between(0, 100).all()),
        "graph_has_edges": result.graph.number_of_edges() > 0,
        "persistent_relationships_are_stronger": bool(old_strength > new_strength),
        "deteriorating_clients_drop_more": bool(client_delta.get(True, 0) < client_delta.get(False, 0)),
        "deteriorating_merchants_drop_more": bool(merchant_delta.get(True, 0) < merchant_delta.get(False, 0)),
    }

    report = {
        "dataset": {
            "rows": len(df),
            "clients": int(df["cedula_cliente"].nunique()),
            "merchants": int(df["codigo_unico_comercio"].nunique()),
            "months": int(df["fecha_transaccion"].dt.to_period("M").nunique()),
        },
        "detected_schema": result.schema.mapping,
        "outputs": {
            "client_month_rows": len(result.client_month),
            "merchant_month_rows": len(result.merchant_month),
            "relationship_month_rows": len(result.relationship_month),
            "graph_nodes": result.graph.number_of_nodes(),
            "graph_edges": result.graph.number_of_edges(),
            "client_communities": int(result.client_communities["community"].nunique()),
            "merchant_communities": int(result.merchant_communities["community"].nunique()),
        },
        "signals": {
            "mean_client_trust_change_3m_deteriorating": float(client_delta.get(True, float("nan"))),
            "mean_client_trust_change_3m_stable": float(client_delta.get(False, float("nan"))),
            "mean_merchant_trust_change_3m_deteriorating": float(merchant_delta.get(True, float("nan"))),
            "mean_merchant_trust_change_3m_stable": float(merchant_delta.get(False, float("nan"))),
            "mean_relationship_strength_age_ge_6m": float(old_strength),
            "mean_relationship_strength_age_1m": float(new_strength),
        },
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for name, passed in checks.items():
        print(f"[{'OK' if passed else 'FAIL'}] {name}")
    print(json.dumps(report["signals"], ensure_ascii=False, indent=2))
    print(f"Report -> {REPORT_PATH}")

    if not report["all_checks_passed"]:
        raise SystemExit("Synthetic validation failed")


if __name__ == "__main__":
    main()
