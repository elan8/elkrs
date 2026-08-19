#!/usr/bin/env python3
"""Generate a corpus of random `layered`-algorithm ELK graphs into
goldens/cases/. Deterministic given --seed, so the corpus is reproducible.

Categories are chosen to exercise the parts of the algorithm most likely to
diverge (cycle breaking, crossing minimization, direction handling, compound
hierarchy / external ports) rather than just uniform random graphs, including
targeted cases for the two narrow divergences elkrs's own README documents:
the merged-external-port ordering case (k=2..5 interior nodes) and the
nodeLabels.placement echo under direction=UP.
"""
import argparse
import json
import random
from pathlib import Path

DIRECTIONS = ["RIGHT", "LEFT", "DOWN", "UP"]


def node(nid, w=30, h=30, labels=None, layout_options=None):
    n = {"id": nid, "width": w, "height": h}
    if labels:
        n["labels"] = [{"text": t, "width": 8 * len(t), "height": 12} for t in labels]
    if layout_options:
        n["layoutOptions"] = layout_options
    return n


def edge(eid, src, tgt):
    return {"id": eid, "sources": [src], "targets": [tgt]}


def base_graph(gid, algorithm_options):
    return {
        "id": gid,
        "layoutOptions": {"org.eclipse.elk.algorithm": "org.eclipse.elk.layered", **algorithm_options},
        "children": [],
        "edges": [],
    }


def gen_dag(rng, n_nodes, extra_edge_prob, back_edge_prob):
    """A random DAG over a random topological order, plus some back-edges
    (creating cycles) and some extra forward edges (creating crossings)."""
    order = [f"n{i}" for i in range(n_nodes)]
    rng.shuffle(order)
    nodes = [node(nid) for nid in order]
    edges = []
    eid = 0
    # A spanning chain over the (fixed, pre-shuffle) node list guarantees connectivity,
    # while edges reference the shuffled `order` to get varied layer assignments.
    for i in range(n_nodes - 1):
        edges.append(edge(f"e{eid}", order[i], order[i + 1]))
        eid += 1
    # Extra forward edges among order[i] -> order[j], i<j (creates crossings)
    for i in range(n_nodes):
        for j in range(i + 2, n_nodes):
            if rng.random() < extra_edge_prob:
                edges.append(edge(f"e{eid}", order[i], order[j]))
                eid += 1
    # Back-edges order[j] -> order[i], i<j (creates cycles)
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            if rng.random() < back_edge_prob:
                edges.append(edge(f"e{eid}", order[j], order[i]))
                eid += 1
    return nodes, edges


def case_chain(rng, idx):
    n_nodes = rng.randint(3, 8)
    g = base_graph("g", {})
    g["children"] = [node(f"n{i}") for i in range(n_nodes)]
    g["edges"] = [edge(f"e{i}", f"n{i}", f"n{i+1}") for i in range(n_nodes - 1)]
    return f"chain_{idx:03d}", g


def case_dag_crossing(rng, idx):
    n_nodes = rng.randint(5, 14)
    nodes, edges = gen_dag(rng, n_nodes, extra_edge_prob=0.15, back_edge_prob=0.0)
    g = base_graph("g", {})
    g["children"] = nodes
    g["edges"] = edges
    return f"dag_{idx:03d}", g


def case_cycle(rng, idx):
    n_nodes = rng.randint(4, 10)
    nodes, edges = gen_dag(rng, n_nodes, extra_edge_prob=0.1, back_edge_prob=0.12)
    g = base_graph("g", {})
    g["children"] = nodes
    g["edges"] = edges
    return f"cycle_{idx:03d}", g


def case_direction(rng, idx):
    n_nodes = rng.randint(5, 10)
    direction = DIRECTIONS[idx % len(DIRECTIONS)]
    nodes, edges = gen_dag(rng, n_nodes, extra_edge_prob=0.12, back_edge_prob=0.05)
    g = base_graph("g", {"org.eclipse.elk.direction": direction})
    g["children"] = nodes
    g["edges"] = edges
    return f"direction_{direction.lower()}_{idx:03d}", g


def case_labels_direction_up(rng, idx):
    """Targets the documented nodeLabels.placement echo divergence under UP."""
    n_nodes = rng.randint(4, 8)
    placements = ["H_LEFT V_TOP", "H_CENTER V_TOP", "H_RIGHT V_BOTTOM", "H_CENTER V_CENTER"]
    placement = placements[idx % len(placements)]
    nodes = [
        node(f"n{i}", labels=[f"node{i}"], layout_options={"org.eclipse.elk.nodeLabels.placement": placement})
        for i in range(n_nodes)
    ]
    edges = [edge(f"e{i}", f"n{i}", f"n{i+1}") for i in range(n_nodes - 1)]
    g = base_graph("g", {"org.eclipse.elk.direction": "UP"})
    g["children"] = nodes
    g["edges"] = edges
    return f"labels_up_{idx:03d}", g


def case_compound_external_port(rng, k, idx):
    """One boundary port on a compound node feeding k interior children —
    the exact shape of the documented merged-external-port ordering divergence."""
    outer_a = node("a")
    children = [node(f"c{i}") for i in range(k)]
    compound = {
        "id": "compound",
        "width": 10,
        "height": 10,
        "layoutOptions": {"org.eclipse.elk.algorithm": "org.eclipse.elk.layered"},
        "children": children,
        "edges": [],
    }
    outer_b = node("b")
    g = base_graph("g", {"org.eclipse.elk.hierarchyHandling": "INCLUDE_CHILDREN"})
    g["children"] = [outer_a, compound, outer_b]
    g["edges"] = [edge("e_out", "compound", "b")]
    for i in range(k):
        g["edges"].append(edge(f"e_in{i}", "a", f"c{i}"))
    return f"compound_extport_k{k}_{idx:03d}", g


def case_compound_nested(rng, idx):
    n_outer = rng.randint(2, 4)
    n_inner = rng.randint(2, 5)
    outer_nodes = [node(f"o{i}") for i in range(n_outer)]
    inner_nodes = [node(f"i{i}") for i in range(n_inner)]
    inner_edges = [edge(f"ie{i}", f"i{i}", f"i{i+1}") for i in range(n_inner - 1)]
    compound = {
        "id": "compound",
        "width": 10,
        "height": 10,
        "layoutOptions": {"org.eclipse.elk.algorithm": "org.eclipse.elk.layered"},
        "children": inner_nodes,
        "edges": inner_edges,
    }
    g = base_graph("g", {"org.eclipse.elk.hierarchyHandling": "INCLUDE_CHILDREN"})
    g["children"] = outer_nodes + [compound]
    g["edges"] = [edge(f"oe{i}", f"o{i}", f"o{i+1}") for i in range(n_outer - 1)]
    g["edges"].append(edge("oe_link", f"o{n_outer-1}", "compound"))
    if n_outer > 0:
        g["edges"].append(edge("oe_into", "o0", "i0"))
    return f"compound_nested_{idx:03d}", g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "goldens" / "cases")
    ap.add_argument("--n-per-category", type=int, default=8)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)

    generators = [
        case_chain,
        case_dag_crossing,
        case_cycle,
        case_direction,
        case_labels_direction_up,
        case_compound_nested,
    ]

    count = 0
    for gen in generators:
        for i in range(args.n_per_category):
            name, g = gen(rng, i)
            (args.out / f"{name}.json").write_text(json.dumps(g, indent=2), encoding="utf-8")
            count += 1

    for k in (2, 3, 4, 5):
        for i in range(3):
            name, g = case_compound_external_port(rng, k, i)
            (args.out / f"{name}.json").write_text(json.dumps(g, indent=2), encoding="utf-8")
            count += 1

    print(f"wrote {count} cases to {args.out}")


if __name__ == "__main__":
    main()
