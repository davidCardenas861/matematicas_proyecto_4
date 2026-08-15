from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd


def build_bipartite_graph(
    relationship: pd.DataFrame,
    client_scores: pd.DataFrame,
    merchant_scores: pd.DataFrame,
    month: pd.Timestamp | str | None = None,
    min_relationship_strength: float = 30.0,
    max_edges: int = 200_000,
) -> nx.Graph:
    rel = relationship.copy()
    if month is None:
        month = rel["month"].max()
    month = pd.Timestamp(month).to_period("M").to_timestamp()
    rel = rel[rel["month"] == month].copy()
    rel = rel[rel["relationship_strength"] >= min_relationship_strength]
    if len(rel) > max_edges:
        rel = rel.nlargest(max_edges, "relationship_strength")

    cs = client_scores[client_scores["month"] == month].set_index("client_id")
    ms = merchant_scores[merchant_scores["month"] == month].set_index("merchant_id")

    G = nx.Graph(month=str(month.date()), bipartite=True)
    for row in rel.itertuples(index=False):
        c = f"C::{row.client_id}"
        m = f"M::{row.merchant_id}"
        ctrust = float(cs.loc[row.client_id, "trust_score"]) if row.client_id in cs.index else np.nan
        mtrust = float(ms.loc[row.merchant_id, "trust_score"]) if row.merchant_id in ms.index else np.nan
        G.add_node(c, bipartite="client", entity_id=str(row.client_id), trust_score=ctrust)
        G.add_node(m, bipartite="merchant", entity_id=str(row.merchant_id), trust_score=mtrust)
        G.add_edge(
            c,
            m,
            weight=float(row.relationship_strength),
            tx_count=int(row.tx_count),
            amount_sum=float(row.amount_sum),
        )
    return G


def project_side(G: nx.Graph, side: str, min_weight: float = 1.0) -> nx.Graph:
    nodes = [n for n, d in G.nodes(data=True) if d.get("bipartite") == side]
    P = nx.algorithms.bipartite.weighted_projected_graph(G, nodes)
    remove = [(u, v) for u, v, d in P.edges(data=True) if d.get("weight", 0) < min_weight]
    P.remove_edges_from(remove)
    for n in P.nodes:
        P.nodes[n].update(G.nodes[n])
    return P


def detect_communities(G: nx.Graph, seed: int = 42) -> dict[str, int]:
    if G.number_of_nodes() == 0:
        return {}
    if G.number_of_edges() == 0:
        return {n: i for i, n in enumerate(G.nodes())}
    communities = nx.community.louvain_communities(G, weight="weight", seed=seed)
    mapping: dict[str, int] = {}
    for cid, community in enumerate(communities):
        for node in community:
            mapping[node] = cid
    return mapping


def graph_metrics(G: nx.Graph) -> pd.DataFrame:
    if G.number_of_nodes() == 0:
        return pd.DataFrame(columns=["node", "degree", "weighted_degree", "pagerank"])
    degree = dict(G.degree())
    weighted = dict(G.degree(weight="weight"))
    pagerank = nx.pagerank(G, weight="weight") if G.number_of_edges() else {n: 1 / len(G) for n in G}
    rows = []
    for n in G.nodes:
        rows.append({
            "node": n,
            "entity_id": G.nodes[n].get("entity_id"),
            "entity_type": G.nodes[n].get("bipartite"),
            "trust_score": G.nodes[n].get("trust_score"),
            "degree": degree.get(n, 0),
            "weighted_degree": weighted.get(n, 0.0),
            "pagerank": pagerank.get(n, np.nan),
        })
    return pd.DataFrame(rows)
