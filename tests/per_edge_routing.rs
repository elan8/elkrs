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

fn route_points(edge: &Value) -> Vec<(f64, f64)> {
    let section = &edge["sections"][0];
    let point = |value: &Value| (value["x"].as_f64().unwrap(), value["y"].as_f64().unwrap());
    let mut points = vec![point(&section["startPoint"])];
    points.extend(
        section["bendPoints"]
            .as_array()
            .into_iter()
            .flatten()
            .map(point),
    );
    points.push(point(&section["endPoint"]));
    points
}

fn collinear_overlap(a: ((f64, f64), (f64, f64)), b: ((f64, f64), (f64, f64))) -> f64 {
    if a.0.1 == a.1.1 && b.0.1 == b.1.1 && a.0.1 == b.0.1 {
        return (a.0.0.max(a.1.0).min(b.0.0.max(b.1.0))
            - a.0.0.min(a.1.0).max(b.0.0.min(b.1.0)))
        .max(0.0);
    }
    if a.0.0 == a.1.0 && b.0.0 == b.1.0 && a.0.0 == b.0.0 {
        return (a.0.1.max(a.1.1).min(b.0.1.max(b.1.1))
            - a.0.1.min(a.1.1).max(b.0.1.min(b.1.1)))
        .max(0.0);
    }
    0.0
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

    let edges = separate["edges"].as_array().unwrap();
    for (left_index, left) in edges.iter().enumerate() {
        let left_points = route_points(left);
        for right in edges.iter().skip(left_index + 1) {
            let right_points = route_points(right);
            let max_overlap = left_points
                .windows(2)
                .flat_map(|left| {
                    right_points.windows(2).map(move |right| {
                        collinear_overlap((left[0], left[1]), (right[0], right[1]))
                    })
                })
                .fold(0.0, f64::max);
            assert!(
                max_overlap <= 16.001,
                "shared routes must separate after the short port stub: {max_overlap}"
            );
        }
    }
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
