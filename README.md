# TrustGraph — confianza transaccional y relacional Cliente ↔ Comercio

Proyecto académico/prototipo para construir un **Trust Score mensual** en una red adquirente. El modelo separa tres conceptos:

1. **Confianza comportamental del cliente**: persistencia, estabilidad, calidad transaccional y fidelidad relacional.
2. **Confianza comportamental del comercio**: persistencia, estabilidad, calidad, recurrencia de clientes y diversificación.
3. **Confianza relacional**: fortaleza y persistencia de cada vínculo Cliente ↔ Comercio, usada después para construir grafos y comunidades.

> El score **no es una probabilidad de fraude**. Sin una etiqueta de fraude/contracargo, representa consistencia y confianza comportamental observable.

## Objetivo

Diseñar un modelo mensual de confianza comportamental y relacional para clientes y comercios de una red adquirente, utilizando patrones de actividad, recurrencia, estabilidad, calidad, diversificación y persistencia de las relaciones Cliente–Comercio, con el propósito de identificar deterioros de comportamiento y caracterizar comunidades de confianza dentro de la red transaccional.

## Estructura

```text
transacciones diarias
        │
        ├── detección automática de columnas
        │
        ├── cliente-mes
        ├── comercio-mes
        └── cliente-comercio-mes
                 │
                 ├── Trust Cliente
                 ├── Trust Comercio
                 └── Relationship Strength
                           │
                           ▼
                    Grafo bipartito
                   Cliente ↔ Comercio
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
          comunidades clientes   comunidades comercios
```

## Datos mínimos

El pipeline intenta detectar automáticamente estos **roles canónicos**:

| Rol | Obligatorio | Ejemplos de nombres detectados |
|---|---:|---|
| `client_id` | Sí | `id_cliente`, `cedula_cliente`, `customer_id` |
| `merchant_id` | Sí | `id_comercio`, `codigo_unico`, `merchant_id` |
| `transaction_date` | Sí | `fecha_transaccion`, `fecha`, `timestamp` |
| `amount` | No* | `monto`, `valor`, `monto_transaccion` |
| `status` | No | `estado_transaccion`, `status` |
| `card_id` | No | `id_tarjeta`, `card_id` |
| `merchant_nit` | No | `nit`, `nit_comercio` |
| `merchant_category` | No | `mcc`, `categoria_comercio` |
| `merchant_affiliation_date` | No | `fecha_afiliacion` |

`amount` es opcional para que el pipeline sea tolerante, pero se recomienda fuertemente para un proyecto real.

Si un nombre es ambiguo, no se adivina silenciosamente: se genera un error con candidatos y se puede definir un override en `config/default.yaml`.

Ejemplo:

```yaml
schema_overrides:
  client_id: NUM_DOCUMENTO
  merchant_id: COD_ESTABLECIMIENTO
  transaction_date: FECHA_TX
  amount: VALOR_COMPRA
```

## Filosofía del score

### Cliente

Versión inicial:

- Persistencia: 25%
- Estabilidad: 25%
- Calidad: 20%
- Fidelidad relacional: 30%

La **fidelidad relacional** no es simplemente concentración. Se premia la persistencia de relaciones con comercios habituales y la fortaleza de esos vínculos.

### Comercio

Versión inicial:

- Persistencia: 20%
- Estabilidad: 25%
- Calidad: 15%
- Recurrencia de clientes: 30%
- Diversificación: 10%

Los pesos son hipótesis iniciales configurables. Cuando una dimensión no existe porque faltan datos opcionales, el score **repondera automáticamente** las dimensiones disponibles.

## Relationship Strength

Para cada pareja Cliente–Comercio y mes se calcula un indicador 0–100 basado en:

- meses de relación activa dentro de una ventana de 6 meses;
- participación de la relación dentro de las transacciones del cliente;
- participación del monto;
- racha de meses consecutivos.

La intención es diferenciar una compra ocasional de una relación persistente.

## Instalación

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Instala:

```bash
pip install -r requirements.txt
pip install -e .
```

## Camino 1 — probar con datos sintéticos

Generar un dataset pequeño:

```bash
python -m trustgraph.cli synthetic \
  --output data/synthetic_transactions.csv \
  --clients 300 \
  --merchants 50 \
  --months 18
```

El generador crea:

- personas/clientes;
- tarjetas;
- comercios;
- NIT;
- MCC;
- fechas de afiliación;
- transacciones aprobadas/rechazadas;
- afinidades persistentes Cliente ↔ Comercio;
- un subconjunto oculto con deterioro en los últimos meses para validar que el score reacciona.

Los campos `synthetic_deteriorating_*` existen **solo para validación** y nunca son utilizados por el modelo para calcular confianza.

Ejecuta el pipeline:

```bash
python -m trustgraph.cli run \
  --input data/synthetic_transactions.csv \
  --output outputs/synthetic_demo \
  --config config/default.yaml
```

## Camino 2 — usar datos reales

```bash
python -m trustgraph.cli run \
  --input ruta/a/transacciones.csv \
  --output outputs/real \
  --config config/default.yaml
```

Primero revisa:

```text
outputs/real/detected_schema.yaml
```

para comprobar qué columnas detectó el sistema.

## Outputs

El pipeline genera:

- `relationship_month.csv`: Cliente–Comercio–Mes y fortaleza de relación.
- `client_month.csv`: features y Trust Cliente mensual.
- `merchant_month.csv`: features y Trust Comercio mensual.
- `graph_metrics.csv`: degree, weighted degree y PageRank.
- `client_communities.csv`: comunidades de clientes.
- `merchant_communities.csv`: comunidades de comercios.
- `bipartite_graph.graphml`: grafo para Gephi/Cytoscape/NetworkX.
- `detected_schema.yaml`: auditoría de detección de columnas.

## Validación incluida

Ejecuta:

```bash
pytest -q
```

Las pruebas verifican:

1. detección automática de nombres de columnas;
2. ejecución completa del pipeline;
3. scores dentro de 0–100;
4. construcción efectiva del grafo;
5. reponderación cuando faltan columnas opcionales;
6. que el grupo sintético deteriorado presente, en promedio, una caída de Trust mayor que el grupo estable.

## Métricas mensuales principales

### Cliente-Mes

- `tx_count`
- `amount_sum`
- `ticket_avg`
- `active_days`
- `unique_merchants`
- `approval_rate`
- `rejection_rate`
- `active_month_ratio_*`
- `tx_cv_*`
- `amount_cv_*`
- `ticket_cv_*`
- `persistent_merchant_ratio`
- `avg_relationship_strength`
- `trust_score`
- `trust_change_1m`
- `trust_change_3m`

### Comercio-Mes

- `tx_count`
- `amount_sum`
- `ticket_avg`
- `active_days`
- `unique_clients`
- `repeat_customer_rate`
- `client_hhi`
- `approval_rate`
- indicadores de estabilidad histórica
- `trust_score`
- `trust_change_1m`
- `trust_change_3m`

## Escalabilidad

`NetworkX` es apropiado para el prototipo académico y muestras controladas. Con cientos de miles de clientes y una red muy grande, **no conviene proyectar el grafo completo en memoria**.

Ruta recomendada para producción:

1. calcular features y Relationship Strength con SQL/Spark/Polars;
2. filtrar relaciones débiles;
3. construir grafos por ventanas o comunidades;
4. usar un motor escalable de grafos si el volumen lo exige;
5. conservar este paquete como referencia metodológica y suite de validación.

El parámetro `graph.max_edges` evita que el prototipo intente materializar una red sin límite.

## Próximas extensiones sugeridas

- Trust a nivel persona y a nivel tarjeta por separado.
- Trust consolidado a nivel NIT y código de comercio.
- Peer groups por MCC/tamaño/antigüedad.
- detección explícita de deterioro futuro t+1/t+3;
- comparación Modelo A (tabular) vs Modelo B (tabular + grafo);
- aprendizaje de pesos del score mediante técnicas supervisadas cuando exista una variable objetivo válida;
- dashboards de evolución mensual y alertas por caída de confianza.


## Validación sintética reproducible

Además de `pytest`, el proyecto incluye una validación funcional completa:

```bash
python examples/validate_synthetic.py
```

Esta prueba genera 300 clientes, 50 comercios y 18 meses; ejecuta el pipeline; guarda los outputs; y comprueba automáticamente que:

- el esquema mínimo fue detectado;
- los Trust Scores quedan entre 0 y 100;
- el grafo contiene relaciones;
- relaciones con mayor antigüedad/persistencia reciben mayor fortaleza media que relaciones nuevas;
- clientes sintéticos deteriorados presentan una caída de Trust a 3 meses mayor que los estables;
- comercios sintéticos deteriorados presentan una caída de Trust a 3 meses mayor que los estables.

El resultado queda en `outputs/synthetic_demo/validation_report.json`.
