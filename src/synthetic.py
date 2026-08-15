from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SyntheticMetadata:
    deteriorating_clients: list[str]
    deteriorating_merchants: list[str]
    start_month: str
    end_month: str


def generate_synthetic_transactions(
    n_clients: int = 300,
    n_merchants: int = 50,
    months: int = 18,
    seed: int = 42,
) -> tuple[pd.DataFrame, SyntheticMetadata]:
    """
    Generate acquiring-style transactions with persistent client-merchant affinities.

    A small hidden group deteriorates in the final 3 months. Synthetic flags are
    included only for validation; the pipeline ignores them.
    """
    rng = np.random.default_rng(seed)
    end = pd.Timestamp("2026-06-01")
    month_index = pd.date_range(end=end, periods=months, freq="MS")

    clients = [f"CL{i:05d}" for i in range(n_clients)]
    merchants = [f"MC{i:04d}" for i in range(n_merchants)]
    categories = ["5411", "5812", "5912", "5541", "5732", "5651"]

    merchant_category = {m: rng.choice(categories) for m in merchants}
    merchant_nit = {m: f"900{100000+i:06d}" for i, m in enumerate(merchants)}
    merchant_aff = {
        m: pd.Timestamp("2018-01-01") + pd.Timedelta(days=int(rng.integers(0, 2500)))
        for m in merchants
    }

    # Community structure: clients prefer merchants from one of 5 merchant groups.
    merchant_groups = np.array_split(np.array(merchants), 5)
    client_group = {c: int(rng.integers(0, 5)) for c in clients}
    favorites: dict[str, list[str]] = {}
    cards: dict[str, list[str]] = {}
    for idx, c in enumerate(clients):
        pool = merchant_groups[client_group[c]].tolist()
        favorites[c] = rng.choice(pool, size=min(4, len(pool)), replace=False).tolist()
        n_cards = int(rng.integers(1, 4))
        cards[c] = [f"CARD{idx:05d}_{k}" for k in range(n_cards)]

    deteriorating_clients = set(rng.choice(clients, size=max(10, n_clients // 15), replace=False).tolist())
    deteriorating_merchants = set(rng.choice(merchants, size=max(3, n_merchants // 12), replace=False).tolist())
    deterioration_start = month_index[-3]

    rows = []
    for month in month_index:
        days_in_month = month.days_in_month
        for c in clients:
            base_tx = max(1, int(rng.poisson(7)))
            if c in deteriorating_clients and month >= deterioration_start:
                base_tx = max(1, int(base_tx * 0.45))

            for _ in range(base_tx):
                # 82% favorite merchant, 13% same community, 5% random.
                p = rng.random()
                if p < 0.82:
                    m = rng.choice(favorites[c])
                elif p < 0.95:
                    m = rng.choice(merchant_groups[client_group[c]])
                else:
                    m = rng.choice(merchants)

                amount = float(np.round(rng.lognormal(mean=10.4, sigma=0.65), 2))
                reject_p = 0.035
                if c in deteriorating_clients and month >= deterioration_start:
                    reject_p += 0.18
                if m in deteriorating_merchants and month >= deterioration_start:
                    reject_p += 0.12

                # Merchants marked as deteriorating also lose some activity.
                if m in deteriorating_merchants and month >= deterioration_start and rng.random() < 0.35:
                    continue

                day = int(rng.integers(1, days_in_month + 1))
                hour = int(rng.integers(7, 23))
                minute = int(rng.integers(0, 60))
                ts = month + pd.Timedelta(days=day - 1, hours=hour, minutes=minute)
                status = "RECHAZADA" if rng.random() < reject_p else "APROBADA"
                card = rng.choice(cards[c])
                rows.append({
                    "cedula_cliente": c,
                    "id_tarjeta": card,
                    "codigo_unico_comercio": m,
                    "nit_comercio": merchant_nit[m],
                    "fecha_transaccion": ts,
                    "monto_transaccion": amount,
                    "estado_transaccion": status,
                    "mcc": merchant_category[m],
                    "fecha_afiliacion": merchant_aff[m],
                    "synthetic_deteriorating_client": int(c in deteriorating_clients),
                    "synthetic_deteriorating_merchant": int(m in deteriorating_merchants),
                })

    df = pd.DataFrame(rows).sort_values("fecha_transaccion").reset_index(drop=True)
    meta = SyntheticMetadata(
        deteriorating_clients=sorted(deteriorating_clients),
        deteriorating_merchants=sorted(deteriorating_merchants),
        start_month=str(month_index[0].date()),
        end_month=str(month_index[-1].date()),
    )
    return df, meta
