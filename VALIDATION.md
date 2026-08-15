# Validación ejecutada

El prototipo fue validado de dos formas:

1. **Suite automatizada (`pytest`)**: 4 pruebas aprobadas.
2. **Prueba funcional sintética de punta a punta**: 300 clientes, 50 comercios, 18 meses y 37.501 transacciones.

Resultados observados en la corrida de referencia (`seed=42`):

- Esquema detectado automáticamente: cliente, tarjeta, comercio, NIT, fecha, monto, estado, MCC y fecha de afiliación.
- 5.400 filas Cliente-Mes.
- 900 filas Comercio-Mes.
- 21.176 filas Cliente-Comercio-Mes.
- Grafo del último mes: 350 nodos y 907 aristas filtradas por fortaleza mínima.
- 5 comunidades de clientes y 5 comunidades de comercios.
- Cambio medio de Trust Cliente a 3 meses:
  - grupo estable: **+0,60 puntos** aproximadamente;
  - grupo sintético deteriorado: **-5,23 puntos** aproximadamente.
- Cambio medio de Trust Comercio a 3 meses:
  - grupo estable: **+0,30 puntos** aproximadamente;
  - grupo sintético deteriorado: **-3,67 puntos** aproximadamente.
- Fortaleza media de relaciones con 6+ meses: **51,62**.
- Fortaleza media de relaciones nuevas (1 mes): **17,56**.

Todos los chequeos funcionales pasaron. Los valores exactos reproducibles están en `outputs/synthetic_demo/validation_report.json`.
