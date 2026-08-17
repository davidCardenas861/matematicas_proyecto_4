"""Algoritmos clasicos de grafos sobre la red de comercios del proyecto de David.

El enunciado de la Unidad 4 nombra explicitamente camino mas corto y arboles recubridores.
El repositorio original aplica centralidad y deteccion de comunidades, que son pertinentes pero
no estan en esa lista, asi que este modulo agrega los dos algoritmos clasicos sobre la misma red
y escribe las figuras y las cifras que van al informe.

La proyeccion de comercios conecta dos comercios cuando comparten clientes, y el peso de la
proyeccion es el numero de clientes compartidos. Como los algoritmos de camino y de arbol
recubridor minimizan costos, el peso se invierte para obtener una distancia: dos comercios que
comparten muchos clientes quedan cerca.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

TINTA = "#1A1A1A"
ROJO = "#C0392B"
GRIS = "#8A8A8A"

REPO = Path(__file__).resolve().parent
SALIDAS = REPO / "outputs" / "synthetic_demo"
FIGURAS = REPO / "outputs" / "extension"


def cargar_proyeccion():
    """Lee el grafo bipartito y lo proyecta sobre los comercios.

    Devuelve la proyeccion con dos atributos por arista: `clientes_comunes`, que es el peso
    original de la proyeccion, y `distancia`, que es su inverso y es lo que consumen Dijkstra y
    Kruskal.
    """
    bipartito = nx.read_graphml(SALIDAS / "bipartite_graph.graphml")
    comercios = [n for n, d in bipartito.nodes(data=True) if d.get("bipartite") == "merchant"]
    proyeccion = nx.algorithms.bipartite.weighted_projected_graph(bipartito, comercios)

    for u, v, datos in proyeccion.edges(data=True):
        compartidos = datos.get("weight", 1)
        datos["clientes_comunes"] = compartidos
        datos["distancia"] = 1.0 / compartidos

    for nodo in proyeccion.nodes:
        proyeccion.nodes[nodo]["etiqueta"] = bipartito.nodes[nodo].get("entity_id", nodo)
    return bipartito, proyeccion


def componente_principal(proyeccion):
    """Aisla la componente conexa mas grande de la proyeccion.

    La red de comercios no es conexa: hay comercios que no comparten ningun cliente con el resto
    en el mes analizado. Un arbol recubridor solo existe sobre una componente conexa, y el camino
    mas corto tampoco esta definido entre componentes distintas, asi que ambos algoritmos se
    aplican sobre la mayor y el resto se reporta aparte.
    """
    componentes = sorted(nx.connected_components(proyeccion), key=len, reverse=True)
    return proyeccion.subgraph(componentes[0]).copy(), [len(c) for c in componentes]


def arbol_recubridor(componente):
    """Arbol recubridor minimo por Kruskal sobre la distancia entre comercios.

    Interpretacion: es el esqueleto de la red de comercios, el conjunto minimo de relaciones que
    mantiene conectados a todos los comercios de la componente pasando siempre por los pares que
    mas clientes comparten. Sirve para decidir sobre que relaciones sostener una campana cruzada
    sin repetir esfuerzo.
    """
    arbol = nx.minimum_spanning_tree(componente, weight="distancia", algorithm="kruskal")
    costo = sum(d["distancia"] for _, _, d in arbol.edges(data=True))
    grados = sorted(arbol.degree(), key=lambda par: par[1], reverse=True)
    return arbol, costo, grados


def camino_mas_corto(proyeccion, origen, destino):
    """Camino mas corto por Dijkstra entre dos comercios, en la metrica de distancia."""
    ruta = nx.dijkstra_path(proyeccion, origen, destino, weight="distancia")
    costo = nx.dijkstra_path_length(proyeccion, origen, destino, weight="distancia")
    saltos = [(proyeccion.nodes[a]["etiqueta"], proyeccion.nodes[b]["etiqueta"],
               proyeccion[a][b]["clientes_comunes"]) for a, b in zip(ruta, ruta[1:])]
    return ruta, costo, saltos


def marco(eje):
    """Recuadro completo con marcas hacia adentro, al estilo de los informes."""
    for lado in eje.spines.values():
        lado.set_linewidth(0.8)
        lado.set_color(TINTA)
    eje.tick_params(direction="in", top=True, right=True, length=0, labelsize=0)


def _bloques(componente):
    """Parte la componente por su puente y devuelve los dos bloques de vertices."""
    puentes = list(nx.bridges(componente))
    if not puentes:
        return [set(componente.nodes)]
    recortada = componente.copy()
    recortada.remove_edge(*puentes[0])
    return sorted(nx.connected_components(recortada), key=len, reverse=True)


def _recuadro_bloque(eje, posicion, nodos, etiqueta, margen=0.09):
    """Enmarca un bloque de vertices con un recuadro suave y su rotulo."""
    xs = [posicion[n][0] for n in nodos]
    ys = [posicion[n][1] for n in nodos]
    x0, x1 = min(xs) - margen, max(xs) + margen
    y0, y1 = min(ys) - margen, max(ys) + margen
    eje.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, transform=eje.transData,
                                facecolor="#F2F2F2", edgecolor="#C9C9C9", linewidth=0.8,
                                linestyle=(0, (5, 3)), zorder=0))
    eje.text((x0 + x1) / 2, y1 + 0.015, etiqueta, fontsize=7.5, color=GRIS, ha="center",
             va="bottom", zorder=4)


def figura_arbol(proyeccion, arbol, metricas, destino):
    """Dibuja la proyeccion completa en gris y encima el arbol recubridor en rojo."""
    # Kamada-Kawai respeta las distancias y reparte mejor el espacio que spring_layout, que con un
    # solo puente entre los dos grupos deja los nodos amontonados en dos esquinas.
    posicion = nx.kamada_kawai_layout(proyeccion, weight="distancia")
    maximo = max(metricas.values())
    tamanos = [45 + 150 * metricas.get(proyeccion.nodes[n]["etiqueta"], 0) / maximo
               for n in proyeccion.nodes]

    figura, eje = plt.subplots(figsize=(6.6, 4.4), dpi=300)

    grupos = _bloques(proyeccion)
    for grupo, nombre in zip(grupos, ["Bloque A", "Bloque B"]):
        _recuadro_bloque(eje, posicion, grupo, "%s, %d comercios" % (nombre, len(grupo)))

    puente = list(nx.bridges(proyeccion))
    aristas_arbol = [(u, v) for u, v in arbol.edges() if (u, v) not in puente and (v, u) not in puente]

    nx.draw_networkx_edges(proyeccion, posicion, ax=eje, edge_color="#D3D3D3", width=0.4)
    nx.draw_networkx_edges(proyeccion, posicion, edgelist=aristas_arbol, ax=eje, edge_color=ROJO,
                           width=1.7)
    if puente:
        nx.draw_networkx_edges(proyeccion, posicion, edgelist=puente, ax=eje, edge_color=ROJO,
                               width=2.2, style=(0, (4, 2)))
    nx.draw_networkx_nodes(proyeccion, posicion, ax=eje, node_size=tamanos,
                           node_color="white", edgecolors=TINTA, linewidths=1.0)

    etiquetas = {n: proyeccion.nodes[n]["etiqueta"].replace("MC00", "") for n in proyeccion.nodes}
    nx.draw_networkx_labels(proyeccion, posicion, labels=etiquetas, ax=eje, font_size=5.4,
                            font_color=TINTA)

    if puente:
        u, v = puente[0]
        medio = ((posicion[u][0] + posicion[v][0]) / 2, (posicion[u][1] + posicion[v][1]) / 2)
        eje.text(medio[0], medio[1] - 0.05, "puente", fontsize=7.5, color=ROJO, ha="center",
                 va="top", rotation=0)

    eje.margins(0.10)
    eje.set_xticks([])
    eje.set_yticks([])
    marco(eje)
    figura.savefig(destino, bbox_inches="tight", pad_inches=0.04, facecolor="white")
    plt.close(figura)
    return posicion


def figura_camino(proyeccion, ruta, posicion, destino):
    """Resalta en rojo el camino mas corto sobre el mismo trazado de la red."""
    aristas = list(zip(ruta, ruta[1:]))
    figura, eje = plt.subplots(figsize=(6.6, 4.6), dpi=300)

    for grupo, nombre in zip(_bloques(proyeccion), ["Bloque A", "Bloque B"]):
        _recuadro_bloque(eje, posicion, grupo, nombre)

    nx.draw_networkx_edges(proyeccion, posicion, ax=eje, edge_color="#DCDCDC", width=0.35)
    nx.draw_networkx_edges(proyeccion, posicion, edgelist=aristas, ax=eje, edge_color=ROJO,
                           width=2.2)
    nx.draw_networkx_nodes(proyeccion, posicion, ax=eje, node_size=55,
                           node_color="white", edgecolors="#9A9A9A", linewidths=0.7)
    nx.draw_networkx_nodes(proyeccion, posicion, nodelist=ruta, ax=eje, node_size=170,
                           node_color="white", edgecolors=ROJO, linewidths=1.6)
    nx.draw_networkx_nodes(proyeccion, posicion, nodelist=[ruta[0], ruta[-1]], ax=eje,
                           node_size=170, node_color=ROJO, edgecolors=ROJO, linewidths=1.6)

    # El numero de salto va dentro del nodo y el codigo del comercio debajo, para no encimarlos.
    for orden, nodo in enumerate(ruta):
        x, y = posicion[nodo]
        color_texto = "white" if nodo in (ruta[0], ruta[-1]) else ROJO
        eje.text(x, y, str(orden), fontsize=6.5, color=color_texto, ha="center", va="center",
                 zorder=5)
        eje.text(x, y - 0.115, proyeccion.nodes[nodo]["etiqueta"], fontsize=6.8, color=TINTA,
                 ha="center", va="top", zorder=5)

    eje.margins(0.10)
    eje.set_xticks([])
    eje.set_yticks([])
    marco(eje)
    figura.savefig(destino, bbox_inches="tight", pad_inches=0.04, facecolor="white")
    plt.close(figura)


def figura_bipartito(bipartito, destino, n_clientes=5):
    """Esquema del modelo bipartito con aristas reales del ultimo mes.

    Sustituye la ilustracion conceptual del documento original: en vez de inventar pesos, toma
    cinco clientes del grafo y dibuja sus relaciones tal como quedaron, con su fuerza.
    """
    # Se toman las relaciones mas fuertes del mes y solo los nodos que las sostienen, para que el
    # esquema quepa y se lea. Dibujar los clientes con mas relaciones produce una marana ilegible.
    fuertes = sorted(bipartito.edges(data=True), key=lambda e: e[2]["weight"], reverse=True)[:8]
    nodos = {n for u, v, _ in fuertes for n in (u, v)}
    clientes = sorted(n for n in nodos if bipartito.nodes[n].get("bipartite") == "client")
    comercios = sorted(n for n in nodos if bipartito.nodes[n].get("bipartite") == "merchant")
    seleccion = set(fuertes and [(u, v) for u, v, _ in fuertes])

    figura, eje = plt.subplots(figsize=(6.2, 3.6), dpi=300)
    posicion = {}
    for i, c in enumerate(clientes):
        posicion[c] = (0.0, -i)
    for j, m in enumerate(comercios):
        posicion[m] = (1.0, -j * len(clientes) / max(len(comercios) - 1, 1))

    for c in clientes:
        for m in bipartito.neighbors(c):
            if m not in posicion:
                continue
            peso = bipartito[c][m]["weight"]
            x0, y0 = posicion[c]
            x1, y1 = posicion[m]
            eje.plot([x0, x1], [y0, y1], color=ROJO if peso >= 60 else GRIS,
                     linewidth=0.5 + 1.8 * peso / 100, zorder=1)
            eje.text((x0 + x1) / 2, (y0 + y1) / 2, "%.0f" % peso, fontsize=5.6,
                     color=TINTA, ha="center", va="center", zorder=3,
                     bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none"))

    for grupo, marcador in [(clientes, "o"), (comercios, "s")]:
        for n in grupo:
            x, y = posicion[n]
            eje.plot(x, y, marcador, markersize=7, markerfacecolor="white",
                     markeredgecolor=TINTA, markeredgewidth=1.0, zorder=2)
            eje.text(x + (-0.06 if x == 0 else 0.06), y, bipartito.nodes[n]["entity_id"],
                     fontsize=6.4, color=TINTA, va="center",
                     ha="right" if x == 0 else "left", zorder=3)

    eje.text(0.0, 0.85, "clientes", fontsize=8, color=TINTA, ha="center")
    eje.text(1.0, 0.85, "comercios", fontsize=8, color=TINTA, ha="center")
    eje.set_xlim(-0.42, 1.42)
    eje.set_ylim(-len(clientes) - 0.4, 1.3)
    eje.set_xticks([])
    eje.set_yticks([])
    marco(eje)
    figura.savefig(destino, bbox_inches="tight", pad_inches=0.04, facecolor="white")
    plt.close(figura)


def matriz_adyacencia(componente, nodos):
    """Matriz de adyacencia ponderada de un subconjunto de comercios.

    La tutora dedico buena parte de la clase del 13 de agosto a la matriz de adyacencia como forma
    de representar el grafo y operar sobre el, asi que el informe la incluye explicitamente.
    """
    etiquetas = [componente.nodes[n]["etiqueta"] for n in nodos]
    filas = []
    for u in nodos:
        filas.append([int(componente[u][v]["clientes_comunes"]) if componente.has_edge(u, v) else 0
                      for v in nodos])
    return etiquetas, filas


def figura_matriz(componente, destino, puente=None):
    """Dibuja la matriz de adyacencia de la componente ordenada por bloques.

    Al ordenar los comercios por su grupo, la matriz muestra dos bloques densos y casi nada fuera
    de ellos: es la misma particion que encuentra Louvain, vista como matriz.
    """
    nodos = sorted(componente.nodes,
                   key=lambda n: (componente.nodes[n]["etiqueta"] not in _grupo_alto(componente),
                                  componente.nodes[n]["etiqueta"]))
    etiquetas, filas = matriz_adyacencia(componente, nodos)
    matriz = np.array(filas, dtype=float)

    n = len(etiquetas)
    figura, eje = plt.subplots(figsize=(5.8, 5.2), dpi=300)

    # La intensidad de cada celda es el numero de clientes compartidos, no un simple si o no.
    mapa = matplotlib.colors.LinearSegmentedColormap.from_list(
        "tinta", ["#FFFFFF", "#BFBFBF", "#4D4D4D"])
    imagen = eje.imshow(np.where(matriz > 0, matriz, np.nan), cmap=mapa, vmin=1,
                        vmax=matriz.max(), interpolation="nearest")

    # Rejilla blanca fina para que las celdas se lean como celdas.
    eje.set_xticks(np.arange(-0.5, n, 1), minor=True)
    eje.set_yticks(np.arange(-0.5, n, 1), minor=True)
    eje.grid(which="minor", color="white", linewidth=0.8)
    eje.tick_params(which="minor", length=0)

    # Los dos bloques se marcan con un recuadro y con una llave por fuera del eje, para no escribir
    # rotulos encima de las celdas.
    corte = len(_grupo_alto(componente))
    for inicio, largo, nombre in [(-0.5, corte, "Bloque A"), (corte - 0.5, n - corte, "Bloque B")]:
        eje.add_patch(plt.Rectangle((inicio, inicio), largo, largo, fill=False,
                                    edgecolor=TINTA, linewidth=1.3, zorder=2))
        eje.plot([-2.1, -2.1], [inicio + 0.15, inicio + largo - 0.15], color=TINTA, linewidth=1.0,
                 clip_on=False, zorder=4)
        eje.text(-2.6, inicio + largo / 2, nombre, fontsize=8, color=TINTA, rotation=90,
                 ha="center", va="center", clip_on=False)

    if puente:
        i, j = etiquetas.index(puente[0]), etiquetas.index(puente[1])
        for x, y in [(i, j), (j, i)]:
            eje.add_patch(plt.Rectangle((y - 0.5, x - 0.5), 1, 1, facecolor=ROJO,
                                        edgecolor=ROJO, linewidth=1.2, zorder=3))
        alto, ancho = (i, j) if i < j else (j, i)
        eje.text(ancho + 0.9, alto, "puente", fontsize=7.5, color=ROJO, ha="left", va="center")

    eje.set_xticks(range(n))
    eje.set_yticks(range(n))
    eje.set_xticklabels([e.replace("MC00", "") for e in etiquetas], fontsize=6)
    eje.set_yticklabels([e.replace("MC00", "") for e in etiquetas], fontsize=6)
    eje.tick_params(length=0)
    for lado in eje.spines.values():
        lado.set_visible(False)

    barra = figura.colorbar(imagen, ax=eje, fraction=0.036, pad=0.03)
    barra.set_label("clientes compartidos", fontsize=7.5, color=TINTA)
    barra.ax.tick_params(labelsize=6.5, length=2)
    barra.outline.set_linewidth(0.6)

    figura.savefig(destino, bbox_inches="tight", pad_inches=0.06, facecolor="white")
    plt.close(figura)
    return etiquetas


def _grupo_alto(componente):
    """Devuelve las etiquetas de uno de los dos bloques, partiendo la componente por su puente."""
    puentes = list(nx.bridges(componente))
    if not puentes:
        return set()
    recortada = componente.copy()
    recortada.remove_edge(*puentes[0])
    bloque = max(nx.connected_components(recortada), key=len)
    return {componente.nodes[n]["etiqueta"] for n in bloque}


def figura_pseudocodigo(destino):
    """Rinde el pseudocodigo como imagen, que es lo que pide el enunciado."""
    lineas = [
        "Entrada:  grafo bipartito G = (C ∪ M, E) con peso relationship_strength",
        "",
        "1.  P ← proyectar G sobre los comercios M",
        "2.  para cada arista (u,v) de P:",
        "3.       clientes_comunes(u,v) ← número de clientes que comparten u y v",
        "4.       distancia(u,v) ← 1 / clientes_comunes(u,v)",
        "",
        "    Árbol recubridor mínimo (Kruskal)",
        "5.  ordenar las aristas de P por distancia ascendente",
        "6.  T ← grafo vacío sobre los vértices de P",
        "7.  para cada arista (u,v) en ese orden:",
        "8.       si u y v están en componentes distintas de T:",
        "9.            agregar (u,v) a T",
        "10. devolver T y su costo total",
        "",
        "    Camino más corto (Dijkstra)",
        "11. d(origen) ← 0 y d(v) ← ∞ para todo v ≠ origen",
        "12. Q ← cola de prioridad con todos los vértices",
        "13. mientras Q no esté vacía:",
        "14.      u ← vértice de Q con d(u) mínima",
        "15.      para cada vecino v de u:",
        "16.           si d(u) + distancia(u,v) < d(v):",
        "17.                d(v) ← d(u) + distancia(u,v) y predecesor(v) ← u",
        "18. reconstruir la ruta desde destino siguiendo los predecesores",
        "",
        "Salida:   árbol recubridor mínimo, camino más corto y sus costos",
    ]
    altura = 0.26 * len(lineas) + 0.4
    figura, eje = plt.subplots(figsize=(6.6, altura), dpi=300)
    eje.axis("off")
    eje.text(0.01, 0.98, "\n".join(lineas), family="DejaVu Sans Mono", fontsize=8.2,
             color=TINTA, va="top", ha="left", linespacing=1.45)
    for lado in ["top", "bottom", "left", "right"]:
        eje.spines[lado].set_visible(True)
        eje.spines[lado].set_linewidth(0.8)
        eje.spines[lado].set_color(TINTA)
    eje.axis("on")
    eje.set_xticks([])
    eje.set_yticks([])
    figura.savefig(destino, bbox_inches="tight", pad_inches=0.06, facecolor="white")
    plt.close(figura)


def main():
    plt.rcParams["font.family"] = "DejaVu Sans"
    FIGURAS.mkdir(parents=True, exist_ok=True)

    bipartito, proyeccion = cargar_proyeccion()
    metricas_csv = pd.read_csv(SALIDAS / "graph_metrics.csv")
    pagerank = metricas_csv[metricas_csv["entity_type"] == "merchant"].set_index("entity_id")["pagerank"].to_dict()

    componente, tamanos_componentes = componente_principal(proyeccion)
    arbol, costo_arbol, grados = arbol_recubridor(componente)

    # El camino va del comercio mas central de la componente al que queda mas lejos de el en la
    # metrica de distancia, que es el par que de verdad obliga a atravesar la red.
    en_componente = {componente.nodes[n]["etiqueta"]: n for n in componente.nodes}
    orden = [par for par in sorted(pagerank.items(), key=lambda par: par[1], reverse=True)
             if par[0] in en_componente]
    origen = en_componente[orden[0][0]]
    distancias = nx.single_source_dijkstra_path_length(componente, origen, weight="distancia")
    destino = max(distancias, key=distancias.get)
    ruta, costo_ruta, saltos = camino_mas_corto(componente, origen, destino)

    posicion = figura_arbol(componente, arbol, pagerank, FIGURAS / "arbol_recubridor.png")
    figura_camino(componente, ruta, posicion, FIGURAS / "camino_mas_corto.png")
    figura_pseudocodigo(FIGURAS / "pseudocodigo.png")
    figura_bipartito(bipartito, FIGURAS / "modelo_bipartito.png")

    # Puentes: aristas cuya eliminacion parte la componente en dos. Es el hallazgo estructural que
    # conecta el arbol recubridor con las comunidades detectadas por Louvain.
    puentes = [(componente.nodes[u]["etiqueta"], componente.nodes[v]["etiqueta"],
                componente[u][v]["clientes_comunes"]) for u, v in nx.bridges(componente)]

    figura_matriz(componente, FIGURAS / "matriz_adyacencia.png",
                  puente=(puentes[0][0], puentes[0][1]) if puentes else None)
    etiquetas_camino, filas_camino = matriz_adyacencia(componente, ruta)

    resumen = {
        "proyeccion": {
            "comercios": proyeccion.number_of_nodes(),
            "relaciones": proyeccion.number_of_edges(),
            "densidad": round(nx.density(proyeccion), 4),
            "componentes": tamanos_componentes,
            "comercios_en_componente_principal": componente.number_of_nodes(),
            "clientes_comunes_max": max(d["clientes_comunes"] for _, _, d in proyeccion.edges(data=True)),
            "clientes_comunes_medio": round(
                sum(d["clientes_comunes"] for _, _, d in proyeccion.edges(data=True))
                / proyeccion.number_of_edges(), 2)},
        "arbol_recubridor": {
            "aristas": arbol.number_of_edges(),
            "costo_total": round(costo_arbol, 4),
            "costo_componente_completa": round(
                sum(d["distancia"] for _, _, d in componente.edges(data=True)), 2),
            "grado_maximo": [(componente.nodes[n]["etiqueta"], g) for n, g in grados[:5]]},
        "puentes": [{"de": a, "a": b, "clientes_comunes": int(c)} for a, b, c in puentes],
        "matriz_camino": {"comercios": etiquetas_camino, "filas": filas_camino},
        "camino_mas_corto": {
            "origen": orden[0][0],
            "destino": componente.nodes[destino]["etiqueta"],
            "saltos": len(ruta) - 1,
            "costo": round(costo_ruta, 4),
            "ruta": [componente.nodes[n]["etiqueta"] for n in ruta],
            "detalle": [{"de": a, "a": b, "clientes_comunes": int(c)} for a, b, c in saltos]}}

    (FIGURAS / "cifras_extension.json").write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
