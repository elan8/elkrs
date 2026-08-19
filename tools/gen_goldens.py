#!/usr/bin/env python3
"""Generate a corpus of random ELK graphs into goldens/cases/, one shape
per algorithm elkrs implements. Deterministic given --seed, so the corpus
is reproducible.

`layered` categories are chosen to exercise the parts of the algorithm most
likely to diverge (cycle breaking, crossing minimization, direction
handling, compound hierarchy / external ports), including targeted cases
for the two narrow divergences elkrs's own README documents: the
merged-external-port ordering case (k=2..5 interior nodes) and the
nodeLabels.placement echo under direction=UP.

The other 11 algorithms get graph shapes appropriate to what they actually
do (see oracle/README.md for the gotchas this accounts for):
  - random: needs an explicit non-zero randomSeed to be reproducible.
  - sporeOverlap / sporeCompaction: operate on *existing* node positions,
    so nodes get explicit x/y (overlapping, or spread out to compact).
  - disco: needs multiple disconnected components (its whole purpose).
  - radial / mrtree: need tree-shaped input.
"""
import argparse
import json
import random
from pathlib import Path

DIRECTIONS = ["RIGHT", "LEFT", "DOWN", "UP"]


def node(nid, w=30, h=30, x=None, y=None, labels=None, layout_options=None):
    n = {"id": nid, "width": w, "height": h}
    if x is not None:
        n["x"] = x
    if y is not None:
        n["y"] = y
    if labels:
        n["labels"] = [{"text": t, "width": 8 * len(t), "height": 12} for t in labels]
    if layout_options:
        n["layoutOptions"] = layout_options
    return n


def edge(eid, src, tgt):
    return {"id": eid, "sources": [src], "targets": [tgt]}


def base_graph(gid, algorithm, algorithm_options=None):
    return {
        "id": gid,
        "layoutOptions": {"org.eclipse.elk.algorithm": algorithm, **(algorithm_options or {})},
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


def gen_tree(rng, n_nodes, prefix="n"):
    """A random tree: each new node attaches to a uniformly random earlier
    node. Returns (nodes, edges), edge i always parent->child."""
    ids = [f"{prefix}{i}" for i in range(n_nodes)]
    nodes = [node(nid) for nid in ids]
    edges = []
    for i in range(1, n_nodes):
        parent = ids[rng.randint(0, i - 1)]
        edges.append(edge(f"{prefix}e{i}", parent, ids[i]))
    return nodes, edges


def gen_forest(rng, n_nodes, n_roots):
    """n_roots independent random trees, roots named r0.. so a multi-root
    algorithm (mrtree) has something to do."""
    nodes, edges = [], []
    per_root = max(1, n_nodes // n_roots)
    for r in range(n_roots):
        count = per_root if r < n_roots - 1 else n_nodes - per_root * (n_roots - 1)
        count = max(1, count)
        tn, te = gen_tree(rng, count, prefix=f"t{r}_")
        nodes += tn
        edges += te
    return nodes, edges


# ---- layered -----------------------------------------------------------

def case_chain(rng, idx):
    n_nodes = rng.randint(3, 8)
    g = base_graph("g", "org.eclipse.elk.layered")
    g["children"] = [node(f"n{i}") for i in range(n_nodes)]
    g["edges"] = [edge(f"e{i}", f"n{i}", f"n{i+1}") for i in range(n_nodes - 1)]
    return f"chain_{idx:03d}", g


def case_dag_crossing(rng, idx):
    n_nodes = rng.randint(5, 14)
    nodes, edges = gen_dag(rng, n_nodes, extra_edge_prob=0.15, back_edge_prob=0.0)
    g = base_graph("g", "org.eclipse.elk.layered")
    g["children"] = nodes
    g["edges"] = edges
    return f"dag_{idx:03d}", g


def case_cycle(rng, idx):
    n_nodes = rng.randint(4, 10)
    nodes, edges = gen_dag(rng, n_nodes, extra_edge_prob=0.1, back_edge_prob=0.12)
    g = base_graph("g", "org.eclipse.elk.layered")
    g["children"] = nodes
    g["edges"] = edges
    return f"cycle_{idx:03d}", g


def case_direction(rng, idx):
    n_nodes = rng.randint(5, 10)
    direction = DIRECTIONS[idx % len(DIRECTIONS)]
    nodes, edges = gen_dag(rng, n_nodes, extra_edge_prob=0.12, back_edge_prob=0.05)
    g = base_graph("g", "org.eclipse.elk.layered", {"org.eclipse.elk.direction": direction})
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
    g = base_graph("g", "org.eclipse.elk.layered", {"org.eclipse.elk.direction": "UP"})
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
    g = base_graph("g", "org.eclipse.elk.layered", {"org.eclipse.elk.hierarchyHandling": "INCLUDE_CHILDREN"})
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
    g = base_graph("g", "org.eclipse.elk.layered", {"org.eclipse.elk.hierarchyHandling": "INCLUDE_CHILDREN"})
    g["children"] = outer_nodes + [compound]
    g["edges"] = [edge(f"oe{i}", f"o{i}", f"o{i+1}") for i in range(n_outer - 1)]
    g["edges"].append(edge("oe_link", f"o{n_outer-1}", "compound"))
    if n_outer > 0:
        g["edges"].append(edge("oe_into", "o0", "i0"))
    return f"compound_nested_{idx:03d}", g


# ---- fixed / box / random -----------------------------------------------

def case_fixed(rng, idx):
    n_nodes = rng.randint(3, 10)
    nodes = []
    x = 0.0
    for i in range(n_nodes):
        y = rng.uniform(0, 200)
        w, h = rng.choice([20, 30, 40]), rng.choice([20, 30, 40])
        nodes.append(node(f"n{i}", w=w, h=h, x=x, y=y))
        x += w + rng.uniform(5, 30)
    edges = [edge(f"e{i}", f"n{i}", f"n{i+1}") for i in range(n_nodes - 1) if rng.random() < 0.6]
    g = base_graph("g", "org.eclipse.elk.fixed")
    g["children"] = nodes
    g["edges"] = edges
    return f"fixed_{idx:03d}", g


def case_box(rng, idx):
    n_nodes = rng.randint(4, 20)
    nodes = [node(f"n{i}", w=rng.choice([15, 25, 35, 50]), h=rng.choice([15, 25, 35, 50])) for i in range(n_nodes)]
    g = base_graph("g", "org.eclipse.elk.box")
    g["children"] = nodes
    return f"box_{idx:03d}", g


def case_random(rng, idx):
    n_nodes = rng.randint(4, 15)
    nodes = [node(f"n{i}") for i in range(n_nodes)]
    edges = [edge(f"e{i}", f"n{i}", f"n{i+1}") for i in range(n_nodes - 1) if rng.random() < 0.7]
    seed = rng.randint(1, 1_000_000)  # must be non-zero: 0 means clock-seeded in real ELK
    g = base_graph("g", "org.eclipse.elk.random", {"org.eclipse.elk.randomSeed": str(seed)})
    g["children"] = nodes
    g["edges"] = edges
    return f"random_{idx:03d}", g


# ---- force / stress -------------------------------------------------------

def case_force_like(rng, idx, algorithm, name_prefix):
    n_nodes = rng.randint(4, 15)
    nodes, edges = gen_dag(rng, n_nodes, extra_edge_prob=0.1, back_edge_prob=0.0)
    seed = rng.randint(1, 1_000_000)  # force/stress default to seed=1 (non-zero); vary it for coverage
    g = base_graph("g", algorithm, {"org.eclipse.elk.randomSeed": str(seed)})
    g["children"] = nodes
    g["edges"] = edges
    return f"{name_prefix}_{idx:03d}", g


def case_force(rng, idx):
    return case_force_like(rng, idx, "org.eclipse.elk.force", "force")


def case_stress(rng, idx):
    return case_force_like(rng, idx, "org.eclipse.elk.stress", "stress")


# ---- radial / mrtree (tree-shaped input) ---------------------------------

def case_radial(rng, idx):
    n_nodes = rng.randint(5, 20)
    nodes, edges = gen_tree(rng, n_nodes)
    g = base_graph("g", "org.eclipse.elk.radial")
    g["children"] = nodes
    g["edges"] = edges
    return f"radial_{idx:03d}", g


def case_mrtree(rng, idx):
    n_nodes = rng.randint(5, 20)
    n_roots = rng.choice([1, 1, 2, 3])
    nodes, edges = gen_forest(rng, n_nodes, n_roots)
    g = base_graph("g", "org.eclipse.elk.mrtree")
    g["children"] = nodes
    g["edges"] = edges
    return f"mrtree_{idx:03d}", g


# ---- rectpacking / topdownpacking (sized nodes, no edges needed) --------

def case_rectpacking(rng, idx):
    n_nodes = rng.randint(4, 20)
    nodes = [node(f"n{i}", w=rng.choice([10, 20, 30, 40, 60]), h=rng.choice([10, 20, 30, 40, 60])) for i in range(n_nodes)]
    g = base_graph("g", "org.eclipse.elk.rectpacking")
    g["children"] = nodes
    return f"rectpacking_{idx:03d}", g


def case_topdownpacking(rng, idx):
    n_nodes = rng.randint(4, 15)
    nodes = [node(f"n{i}", w=rng.choice([20, 30, 40]), h=rng.choice([20, 30, 40])) for i in range(n_nodes)]
    g = base_graph("g", "org.eclipse.elk.topdownpacking")
    g["children"] = nodes
    return f"topdownpacking_{idx:03d}", g


# ---- spore (needs existing, non-degenerate node positions) --------------

def case_spore_overlap(rng, idx):
    n_nodes = rng.randint(3, 10)
    nodes = []
    for i in range(n_nodes):
        # deliberately clustered so overlaps are likely
        x = rng.uniform(0, 60)
        y = rng.uniform(0, 60)
        nodes.append(node(f"n{i}", w=30, h=30, x=x, y=y))
    edges = [edge(f"e{i}", f"n{i}", f"n{i+1}") for i in range(n_nodes - 1) if rng.random() < 0.5]
    g = base_graph("g", "org.eclipse.elk.sporeOverlap")
    g["children"] = nodes
    g["edges"] = edges
    return f"sporeoverlap_{idx:03d}", g


def case_spore_compaction(rng, idx):
    n_nodes = rng.randint(3, 10)
    nodes = []
    for i in range(n_nodes):
        # deliberately spread out so there's something to compact
        x = rng.uniform(0, 400)
        y = rng.uniform(0, 400)
        nodes.append(node(f"n{i}", w=30, h=30, x=x, y=y))
    edges = [edge(f"e{i}", f"n{i}", f"n{i+1}") for i in range(n_nodes - 1) if rng.random() < 0.5]
    g = base_graph("g", "org.eclipse.elk.sporeCompaction")
    g["children"] = nodes
    g["edges"] = edges
    return f"sporecompaction_{idx:03d}", g


# ---- disco (needs multiple disconnected components) ----------------------

def case_disco(rng, idx):
    n_components = rng.randint(2, 4)
    nodes, edges = [], []
    for c in range(n_components):
        n_nodes = rng.randint(2, 5)
        cn, ce = gen_tree(rng, n_nodes, prefix=f"c{c}_")
        nodes += cn
        edges += ce
    g = base_graph("g", "org.eclipse.elk.disco")
    g["children"] = nodes
    g["edges"] = edges
    return f"disco_{idx:03d}", g


CATEGORIES = {
    "chain": case_chain,
    "dag": case_dag_crossing,
    "cycle": case_cycle,
    "direction": case_direction,
    "labels_up": case_labels_direction_up,
    "compound_nested": case_compound_nested,
    "fixed": case_fixed,
    "box": case_box,
    "random": case_random,
    "force": case_force,
    "stress": case_stress,
    "radial": case_radial,
    "mrtree": case_mrtree,
    "rectpacking": case_rectpacking,
    "topdownpacking": case_topdownpacking,
    "sporeoverlap": case_spore_overlap,
    "sporecompaction": case_spore_compaction,
    "disco": case_disco,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "goldens" / "cases")
    ap.add_argument("--n-per-category", type=int, default=8)
    ap.add_argument("--categories", nargs="*", default=None,
                     help=f"subset of {sorted(CATEGORIES)} (default: all)")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)

    selected = args.categories or list(CATEGORIES)
    unknown = set(selected) - set(CATEGORIES)
    if unknown:
        raise SystemExit(f"unknown categories: {sorted(unknown)}")

    count = 0
    for cat in selected:
        gen = CATEGORIES[cat]
        for i in range(args.n_per_category):
            name, g = gen(rng, i)
            (args.out / f"{name}.json").write_text(json.dumps(g, indent=2), encoding="utf-8")
            count += 1

    if args.categories is None:
        for k in (2, 3, 4, 5):
            for i in range(3):
                name, g = case_compound_external_port(rng, k, i)
                (args.out / f"{name}.json").write_text(json.dumps(g, indent=2), encoding="utf-8")
                count += 1

    print(f"wrote {count} cases to {args.out}")


if __name__ == "__main__":
    main()
