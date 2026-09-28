use serde_json::{Value, json};

const PER_EDGE_ROUTING: &str = "elkrs.layered.orthogonal.perEdgeRouting";

fn shared_port_graph(per_edge_routing: bool) -> Value {
    json!({
        "id": "graph",
        "layoutOptions": {
            "org.eclipse.elk.algorithm": "org.eclipse.elk.layered",
            "org.eclipse.elk.edgeRouting": "ORTHOGONAL",
            "org.eclipse.elk.direction": "RIGHT",
            "org.eclipse.elk.layered.spacing.edgeEdgeBetweenLayers": "12",
            PER_EDGE_ROUTING: per_edge_routing.to_string()
        },
        "children": [
            {
                "id": "a", "width": 60, "height": 80,
                "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_SIDE"},
                "ports": [{
                    "id": "a.p", "width": 8, "height": 8,
                    "layoutOptions": {"org.eclipse.elk.port.side": "EAST"}
                }]
            },
            {
                "id": "b", "width": 60, "height": 80,
                "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_SIDE"},
                "ports": [{
                    "id": "b.p", "width": 8, "height": 8,
                    "layoutOptions": {"org.eclipse.elk.port.side": "WEST"}
                }]
            },
            {
                "id": "c", "width": 60, "height": 80,
                "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_SIDE"},
                "ports": [{
                    "id": "c.p", "width": 8, "height": 8,
                    "layoutOptions": {"org.eclipse.elk.port.side": "WEST"}
                }]
            },
            {
                "id": "d", "width": 60, "height": 80,
                "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_SIDE"},
                "ports": [{
                    "id": "d.p", "width": 8, "height": 8,
                    "layoutOptions": {"org.eclipse.elk.port.side": "WEST"}
                }]
            }
        ],
        "edges": [
            {"id": "a-b", "sources": ["a.p"], "targets": ["b.p"]},
            {"id": "a-c", "sources": ["a.p"], "targets": ["c.p"]},
            {"id": "a-d", "sources": ["a.p"], "targets": ["d.p"]}
        ]
    })
}

fn layout(per_edge_routing: bool) -> Value {
    let input = shared_port_graph(per_edge_routing);
    elkrs::create_elk()
        .layout_json(&input.to_string())
        .expect("layout failed")
}

fn trunk_coordinates(output: &Value) -> Vec<f64> {
    output["edges"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|edge| edge["sections"][0]["bendPoints"][0]["x"].as_f64())
        .collect()
}

#[test]
fn shared_port_edges_get_individual_routing_channels() {
    let merged = layout(false);
    let merged_trunks = trunk_coordinates(&merged);
    assert!(merged_trunks.len() >= 2);
    assert!(
        merged_trunks.windows(2).all(|pair| pair[0] == pair[1]),
        "the default remains ELK-compatible port-net routing: {merged_trunks:?}"
    );

    let separate = layout(true);
    let separate_trunks = trunk_coordinates(&separate);
    assert!(separate_trunks.len() >= 2);
    assert!(
        separate_trunks.windows(2).any(|pair| pair[0] != pair[1]),
        "per-edge routing must give each modeled edge its own channel: {separate_trunks:?}"
    );
}

#[test]
fn per_edge_routing_is_deterministic() {
    assert_eq!(layout(true), layout(true));
}

fn compound_shared_port_graph() -> Value {
    json!({
        "id": "root",
        "layoutOptions": {
            "org.eclipse.elk.algorithm": "org.eclipse.elk.layered",
            "org.eclipse.elk.hierarchyHandling": "INCLUDE_CHILDREN",
            "org.eclipse.elk.edgeRouting": "ORTHOGONAL",
            PER_EDGE_ROUTING: "true"
        },
        "children": [
            {"id": "outside-a", "width": 50, "height": 50},
            {"id": "outside-b", "width": 50, "height": 50},
            {"id": "outside-c", "width": 50, "height": 50},
            {
                "id": "container",
                "width": 80,
                "height": 80,
                "layoutOptions": {
                    "org.eclipse.elk.algorithm": "org.eclipse.elk.layered",
                    PER_EDGE_ROUTING: "true"
                },
                "children": [{
                    "id": "nested", "width": 50, "height": 70,
                    "ports": [{"id": "nested.p", "width": 8, "height": 8}]
                }]
            }
        ],
        "edges": [
            {"id": "nested-a", "sources": ["nested.p"], "targets": ["outside-a"]},
            {"id": "nested-b", "sources": ["nested.p"], "targets": ["outside-b"]},
            {"id": "nested-c", "sources": ["nested.p"], "targets": ["outside-c"]}
        ]
    })
}

#[test]
fn compound_shared_port_layout_is_supported_and_deterministic() {
    let input = compound_shared_port_graph().to_string();
    let first = elkrs::create_elk()
        .layout_json(&input)
        .expect("compound layout failed");
    let second = elkrs::create_elk()
        .layout_json(&input)
        .expect("compound layout failed");
    assert_eq!(first, second);
    assert_eq!(first["edges"].as_array().unwrap().len(), 3);
    for edge in first["edges"].as_array().unwrap() {
        assert!(
            edge["sections"]
                .as_array()
                .is_some_and(|sections| !sections.is_empty())
        );
    }
    let trunks = trunk_coordinates(&first);
    assert!(
        trunks.len() >= 2,
        "compound edges must have routed trunks: {trunks:?}"
    );
    assert!(
        trunks.windows(2).any(|pair| pair[0] != pair[1]),
        "compound edges sharing a nested port need separate channels: {trunks:?}"
    );
}
