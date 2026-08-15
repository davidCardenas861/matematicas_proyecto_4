from pathlib import Path

from trustgraph import TrustGraphPipeline, generate_synthetic_transactions


ROOT = Path(__file__).resolve().parents[1]

df, metadata = generate_synthetic_transactions(
    n_clients=300,
    n_merchants=50,
    months=18,
    seed=42,
)

pipeline = TrustGraphPipeline.from_yaml(ROOT / "config" / "default.yaml")
result = pipeline.run(df)
pipeline.save(result, ROOT / "outputs" / "synthetic_demo")

print("Schema detected:", result.schema.mapping)
print("Synthetic deterioration clients:", len(metadata.deteriorating_clients))
print("Latest client score mean:", round(result.client_month.groupby("month").tail(300)["trust_score"].mean(), 2))
print("Graph nodes/edges:", result.graph.number_of_nodes(), result.graph.number_of_edges())
