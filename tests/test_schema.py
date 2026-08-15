import pandas as pd

from trustgraph.schema import infer_schema


def test_schema_alias_detection():
    df = pd.DataFrame({
        "cedula_cliente": ["1", "2"],
        "codigo_unico_comercio": ["A", "B"],
        "fecha_transaccion": ["2026-01-01", "2026-01-02"],
        "monto_transaccion": [100.0, 200.0],
        "estado_transaccion": ["APROBADA", "RECHAZADA"],
    })
    match = infer_schema(df)
    assert match.mapping["client_id"] == "cedula_cliente"
    assert match.mapping["merchant_id"] == "codigo_unico_comercio"
    assert match.mapping["transaction_date"] == "fecha_transaccion"
    assert match.mapping["amount"] == "monto_transaccion"
