from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Any

import numpy as np
import pandas as pd


class SchemaDetectionError(ValueError):
    """Raised when the minimum transactional schema cannot be inferred safely."""


ROLE_ALIASES: dict[str, list[str]] = {
    "client_id": [
        "id_cliente", "cliente_id", "client_id", "customer_id", "id_customer",
        "cedula", "cedula_cliente", "documento_cliente", "persona_id", "id_persona",
    ],
    "card_id": [
        "id_tarjeta", "tarjeta_id", "card_id", "pan_hash", "token_tarjeta", "tarjeta",
    ],
    "merchant_id": [
        "id_comercio", "comercio_id", "merchant_id", "codigo_comercio", "codigo_unico", "codigo_unico_comercio",
        "merchant_code", "establecimiento_id", "id_establecimiento",
    ],
    "merchant_nit": [
        "nit", "nit_comercio", "merchant_nit", "tax_id", "documento_comercio",
    ],
    "transaction_date": [
        "fecha", "fecha_transaccion", "transaction_date", "date", "datetime",
        "fecha_hora", "timestamp", "transaction_timestamp",
    ],
    "amount": [
        "monto", "valor", "importe", "amount", "transaction_amount", "valor_transaccion",
        "monto_transaccion",
    ],
    "status": [
        "estado", "estado_transaccion", "status", "transaction_status", "respuesta",
        "resultado", "approved_flag", "aprobada",
    ],
    "merchant_category": [
        "mcc", "categoria_comercio", "merchant_category", "categoria", "sector",
        "actividad_economica",
    ],
    "merchant_affiliation_date": [
        "fecha_afiliacion", "affiliation_date", "merchant_affiliation_date", "fecha_alta_comercio",
    ],
    "client_affiliation_date": [
        "fecha_alta_cliente", "client_affiliation_date", "fecha_vinculacion_cliente",
        "customer_since",
    ],
}

REQUIRED_ROLES = ("client_id", "merchant_id", "transaction_date")
OPTIONAL_ROLES = tuple(r for r in ROLE_ALIASES if r not in REQUIRED_ROLES)


def _norm(name: str) -> str:
    name = str(name).strip().lower()
    name = re.sub(r"[^a-z0-9áéíóúñ]+", "_", name)
    return name.strip("_")


def _alias_score(column: str, aliases: list[str]) -> float:
    c = _norm(column)
    norm_aliases = [_norm(a) for a in aliases]
    if c in norm_aliases:
        return 1.0
    tokens = set(c.split("_"))
    best = 0.0
    for alias in norm_aliases:
        atokens = set(alias.split("_"))
        if not atokens:
            continue
        overlap = len(tokens & atokens) / len(tokens | atokens)
        best = max(best, overlap * 0.75)
    return best


def _semantic_bonus(series: pd.Series, role: str) -> float:
    non_null = series.dropna()
    if non_null.empty:
        return 0.0

    if role in {"transaction_date", "merchant_affiliation_date", "client_affiliation_date"}:
        if pd.api.types.is_datetime64_any_dtype(series):
            return 0.25
        sample = non_null.astype(str).head(200)
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        return 0.18 if parsed.notna().mean() > 0.9 else 0.0

    if role == "amount":
        numeric = pd.to_numeric(non_null.head(500), errors="coerce")
        return 0.18 if numeric.notna().mean() > 0.95 else 0.0

    if role == "status":
        nunique = non_null.nunique()
        return 0.12 if nunique <= 20 else 0.0

    if role in {"client_id", "card_id", "merchant_id", "merchant_nit"}:
        ratio = non_null.nunique() / max(len(non_null), 1)
        return 0.08 if ratio > 0.005 else 0.0

    return 0.0


@dataclass
class SchemaMatch:
    mapping: dict[str, str]
    confidence: dict[str, float]
    unresolved_required: list[str]
    candidates: dict[str, list[tuple[str, float]]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_schema(
    df: pd.DataFrame,
    overrides: dict[str, str] | None = None,
    min_confidence: float = 0.72,
) -> SchemaMatch:
    """
    Infer canonical transactional roles from arbitrary column names.

    Minimum required roles:
      - client_id
      - merchant_id
      - transaction_date

    Optional roles are detected when available. Explicit overrides always win.
    """
    overrides = overrides or {}
    columns = list(df.columns)
    mapping: dict[str, str] = {}
    confidence: dict[str, float] = {}
    candidates: dict[str, list[tuple[str, float]]] = {}

    for role, aliases in ROLE_ALIASES.items():
        if role in overrides:
            col = overrides[role]
            if col not in df.columns:
                raise SchemaDetectionError(
                    f"Override '{role}: {col}' does not exist in dataframe columns."
                )
            mapping[role] = col
            confidence[role] = 1.0
            candidates[role] = [(col, 1.0)]
            continue

        scored: list[tuple[str, float]] = []
        for col in columns:
            score = min(1.0, _alias_score(col, aliases) + _semantic_bonus(df[col], role))
            scored.append((col, round(float(score), 4)))
        scored.sort(key=lambda x: x[1], reverse=True)
        candidates[role] = scored[:5]

        if scored and scored[0][1] >= min_confidence:
            # Avoid assigning the same column to two ID roles automatically.
            chosen = scored[0][0]
            if chosen not in mapping.values():
                mapping[role] = chosen
                confidence[role] = scored[0][1]

    unresolved = [r for r in REQUIRED_ROLES if r not in mapping]
    if unresolved:
        detail = {r: candidates.get(r, []) for r in unresolved}
        raise SchemaDetectionError(
            "Could not safely infer required roles: "
            f"{unresolved}. Candidate columns: {detail}. "
            "Pass schema_overrides={'client_id': '...', 'merchant_id': '...', "
            "'transaction_date': '...'} when names are ambiguous."
        )

    return SchemaMatch(mapping, confidence, unresolved, candidates)


def canonicalize_dataframe(df: pd.DataFrame, match: SchemaMatch) -> pd.DataFrame:
    """Return a copy with inferred columns renamed to canonical role names."""
    inverse = {source: role for role, source in match.mapping.items()}
    out = df.rename(columns=inverse).copy()

    out["transaction_date"] = pd.to_datetime(out["transaction_date"], errors="coerce")
    out = out[out["transaction_date"].notna()].copy()

    if "amount" in out.columns:
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
        out["amount"] = out["amount"].fillna(0.0)
    else:
        out["amount"] = 1.0

    for date_col in ["merchant_affiliation_date", "client_affiliation_date"]:
        if date_col in out.columns:
            out[date_col] = pd.to_datetime(out[date_col], errors="coerce")

    out["month"] = out["transaction_date"].dt.to_period("M").dt.to_timestamp()
    return out
