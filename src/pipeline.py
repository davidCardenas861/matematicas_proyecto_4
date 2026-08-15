from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd
import yaml

from .features import build_client_month, build_merchant_month, build_relationship_month
from .graph import build_bipartite_graph, detect_communities, graph_metrics, project_side
from .schema import SchemaMatch, canonicalize_dataframe, infer_schema
from .scoring import score_clients, score_merchants


@dataclass
class PipelineResult:
    schema: SchemaMatch
    transactions: pd.DataFrame
    relationship_month: pd.DataFrame
    client_month: pd.DataFrame
    merchant_month: pd.DataFrame
    graph: nx.Graph
    graph_metrics: pd.DataFrame
    client_communities: pd.DataFrame
    merchant_communities: pd.DataFrame


class TrustGraphPipeline:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or self.default_config()

    @staticmethod
    def default_config() -> dict[str, Any]:
        return {
            "schema_overrides": {},
            "features": {
                "rolling_months_short": 3,
                "rolling_months_medium": 6,
                "rolling_months_long": 12,
                "relationship_window": 6,
                "min_history_months_for_stability": 3,
            },
            "scores": {
                "client": {
                    "persistence": 0.25,
                    "stability": 0.25,
                    "quality": 0.20,
                    "relationship_fidelity": 0.30,
                },
                "merchant": {
                    "persistence": 0.20,
                    "stability": 0.25,
                    "quality": 0.15,
                    "customer_recurrence": 0.30,
                    "diversification": 0.10,
                },
                "bands": {"very_high": 85, "high": 70, "medium": 50, "low": 0},
            },
            "graph": {
                "min_relationship_strength": 30,
                "max_edges": 200000,
                "projection_min_weight": 1,
                "community_seed": 42,
            },
        }

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TrustGraphPipeline":
        with open(path, "r", encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    def run(self, df: pd.DataFrame) -> PipelineResult:
        cfg = self.config
        fcfg = cfg["features"]
        schema = infer_schema(df, overrides=cfg.get("schema_overrides", {}))
        tx = canonicalize_dataframe(df, schema)

        relationship = build_relationship_month(
            tx,
            relationship_window=fcfg["relationship_window"],
        )
        client = build_client_month(
            tx,
            relationship,
            rolling_short=fcfg["rolling_months_short"],
            rolling_medium=fcfg["rolling_months_medium"],
            rolling_long=fcfg["rolling_months_long"],
            min_history=fcfg["min_history_months_for_stability"],
        )
        merchant = build_merchant_month(
            tx,
            relationship,
            rolling_short=fcfg["rolling_months_short"],
            rolling_medium=fcfg["rolling_months_medium"],
            rolling_long=fcfg["rolling_months_long"],
            min_history=fcfg["min_history_months_for_stability"],
        )
        client = score_clients(
            client,
            cfg["scores"]["client"],
            cfg["scores"]["bands"],
            fcfg["rolling_months_medium"],
            fcfg["rolling_months_long"],
        )
        merchant = score_merchants(
            merchant,
            cfg["scores"]["merchant"],
            cfg["scores"]["bands"],
            fcfg["rolling_months_medium"],
            fcfg["rolling_months_long"],
        )

        gcfg = cfg["graph"]
        G = build_bipartite_graph(
            relationship,
            client,
            merchant,
            min_relationship_strength=gcfg["min_relationship_strength"],
            max_edges=gcfg["max_edges"],
        )
        metrics = graph_metrics(G)

        client_proj = project_side(G, "client", gcfg["projection_min_weight"])
        merchant_proj = project_side(G, "merchant", gcfg["projection_min_weight"])
        cc = detect_communities(client_proj, gcfg["community_seed"])
        mc = detect_communities(merchant_proj, gcfg["community_seed"])

        client_communities = pd.DataFrame(
            [{"node": n, "client_id": client_proj.nodes[n].get("entity_id"), "community": c}
             for n, c in cc.items()]
        )
        merchant_communities = pd.DataFrame(
            [{"node": n, "merchant_id": merchant_proj.nodes[n].get("entity_id"), "community": c}
             for n, c in mc.items()]
        )

        return PipelineResult(
            schema=schema,
            transactions=tx,
            relationship_month=relationship,
            client_month=client,
            merchant_month=merchant,
            graph=G,
            graph_metrics=metrics,
            client_communities=client_communities,
            merchant_communities=merchant_communities,
        )

    @staticmethod
    def save(result: PipelineResult, output_dir: str | Path) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        result.relationship_month.to_csv(out / "relationship_month.csv", index=False)
        result.client_month.to_csv(out / "client_month.csv", index=False)
        result.merchant_month.to_csv(out / "merchant_month.csv", index=False)
        result.graph_metrics.to_csv(out / "graph_metrics.csv", index=False)
        result.client_communities.to_csv(out / "client_communities.csv", index=False)
        result.merchant_communities.to_csv(out / "merchant_communities.csv", index=False)
        nx.write_graphml(result.graph, out / "bipartite_graph.graphml")
        with open(out / "detected_schema.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(result.schema.to_dict(), f, allow_unicode=True, sort_keys=False)
