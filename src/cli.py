from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .pipeline import TrustGraphPipeline
from .synthetic import generate_synthetic_transactions


def _read_table(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    if p.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(p)
    raise ValueError("Supported input formats: .csv, .parquet")


def main() -> None:
    parser = argparse.ArgumentParser(description="TrustGraph CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_syn = sub.add_parser("synthetic", help="Generate synthetic acquiring transactions")
    p_syn.add_argument("--output", default="data/synthetic_transactions.csv")
    p_syn.add_argument("--clients", type=int, default=300)
    p_syn.add_argument("--merchants", type=int, default=50)
    p_syn.add_argument("--months", type=int, default=18)
    p_syn.add_argument("--seed", type=int, default=42)

    p_run = sub.add_parser("run", help="Run the complete TrustGraph pipeline")
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--output", default="outputs")
    p_run.add_argument("--config", default=None)

    args = parser.parse_args()

    if args.command == "synthetic":
        df, meta = generate_synthetic_transactions(
            n_clients=args.clients,
            n_merchants=args.merchants,
            months=args.months,
            seed=args.seed,
        )
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        with open(out.with_suffix(".metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta.__dict__, f, ensure_ascii=False, indent=2)
        print(f"Synthetic dataset: {len(df):,} rows -> {out}")
        return

    if args.command == "run":
        df = _read_table(args.input)
        pipeline = TrustGraphPipeline.from_yaml(args.config) if args.config else TrustGraphPipeline()
        result = pipeline.run(df)
        pipeline.save(result, args.output)
        print("Detected schema:", result.schema.mapping)
        print(f"Client-month rows: {len(result.client_month):,}")
        print(f"Merchant-month rows: {len(result.merchant_month):,}")
        print(f"Relationship-month rows: {len(result.relationship_month):,}")
        print(f"Graph: {result.graph.number_of_nodes():,} nodes / {result.graph.number_of_edges():,} edges")
        print(f"Outputs -> {args.output}")


if __name__ == "__main__":
    main()
