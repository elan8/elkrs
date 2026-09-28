//!
//! Instances of this struct represent the "trunk" of a hyper edge. Segments and
//! their dependencies live in a
//! [`SegmentStore`] arena and reference each other through indices.

use std::collections::{BTreeSet, HashMap};

use crate::alg_layered::graph::{LEdgeId, LGraphArena, LPortId, NodeType};

use super::direction::BaseRoutingDirectionStrategy;
use super::hyper_edge_segment_dependency::{self as dependency, HyperEdgeSegmentDependency};

/// Index of a segment in the [`SegmentStore`].
pub type SegmentId = usize;
/// Index of a dependency in the [`SegmentStore`].
pub type DependencyId = usize;

/// Visual separation between lanes that fan out from the same port.
pub const PER_EDGE_LANE_SPACING: f64 = 4.0;

pub fn edge_lane_offset(a: &LGraphArena, port: LPortId, edge: LEdgeId) -> f64 {
    debug_assert!(a.port(port).incoming_edges.contains(&edge) || a.port(port).outgoing_edges.contains(&edge));
    let mut component = BTreeSet::new();
    let mut pending = vec![edge];
    while let Some(candidate) = pending.pop() {
        if a.edge_is_self_loop(candidate) || !component.insert(candidate) {
            continue;
        }
        for endpoint in [a.edge(candidate).source, a.edge(candidate).target]
            .into_iter()
            .flatten()
        {
            let mut connected_ports = vec![endpoint];
            let node = a.port(endpoint).node.unwrap();
            if a.node(node).node_type == NodeType::LONG_EDGE {
                connected_ports.extend(a.node(node).ports.iter().copied().filter(|p| *p != endpoint));
            }
            for connected_port in connected_ports {
                pending.extend(a.port(connected_port).incoming_edges.iter().copied());
                pending.extend(a.port(connected_port).outgoing_edges.iter().copied());
            }
        }
    }
    if component.len() <= 1 {
        return 0.0;
    }
    let index = component
        .iter()
        .position(|candidate| *candidate == edge)
        .expect("edge is not in its connected component");
    (index as f64 - (component.len() - 1) as f64 / 2.0) * PER_EDGE_LANE_SPACING
}

pub struct HyperEdgeSegment {
    /// When set, this segment belongs to exactly one modeled edge. `None`
    /// retains ELK's port-net/hyperedge behavior.
    pub edge: Option<LEdgeId>,
    /// ports represented by this hypernode.
    pub ports: Vec<LPortId>,
    /// mark value used for cycle breaking.
    pub mark: i32,
    /// the routing slot determines the horizontal distance to the preceding layer.
    pub routing_slot: i32,
    /// start position of this edge segment (NaN initially).
    pub start_position: f64,
    /// end position of this edge segment (NaN initially).
    pub end_position: f64,
    /// sorted list of coordinates where incoming connections enter this segment.
    pub incoming_connection_coordinates: Vec<f64>,
    /// sorted list of coordinates where outgoing connections leave this segment.
    pub outgoing_connection_coordinates: Vec<f64>,
    /// list of outgoing dependencies to other edge segments.
    pub outgoing_segment_dependencies: Vec<DependencyId>,
    /// combined weight of all outgoing dependencies.
    pub out_dep_weight: i32,
    /// combined weight of critical outgoing dependencies.
    pub critical_out_dep_weight: i32,
    /// list of incoming dependencies from other edge segments.
    pub incoming_segment_dependencies: Vec<DependencyId>,
    /// combined weight of all incoming dependencies.
    pub in_dep_weight: i32,
    /// combined weight of critical incoming dependencies.
    pub critical_in_dep_weight: i32,
    /// if this segment is the result of a split, the other segment.
    pub split_partner: Option<SegmentId>,
    /// the segment that caused this segment to be split, if any.
    pub split_by: Option<SegmentId>,
}

impl HyperEdgeSegment {
    fn new() -> Self {
        HyperEdgeSegment {
            edge: None,
            ports: Vec::new(),
            mark: 0,
            routing_slot: 0,
            start_position: f64::NAN,
            end_position: f64::NAN,
            incoming_connection_coordinates: Vec::new(),
            outgoing_connection_coordinates: Vec::new(),
            outgoing_segment_dependencies: Vec::new(),
            out_dep_weight: 0,
            critical_out_dep_weight: 0,
            incoming_segment_dependencies: Vec::new(),
            in_dep_weight: 0,
            critical_in_dep_weight: 0,
            split_partner: None,
            split_by: None,
        }
    }

    pub fn start_coordinate(&self) -> f64 {
        self.start_position
    }

    pub fn end_coordinate(&self) -> f64 {
        self.end_position
    }

    pub fn length(&self) -> f64 {
        self.end_coordinate() - self.start_coordinate()
    }

    pub fn represents_hyperedge(&self) -> bool {
        self.incoming_connection_coordinates.len() + self.outgoing_connection_coordinates.len() > 2
    }

    pub fn is_dummy(&self) -> bool {
        self.split_partner.is_some() && self.split_by.is_none()
    }

    pub fn recompute_extent(&mut self) {
        self.start_position = f64::NAN;
        self.end_position = f64::NAN;

        let (mut start, mut end) = (self.start_position, self.end_position);
        recompute_extent_with(&mut start, &mut end, &self.incoming_connection_coordinates);
        recompute_extent_with(&mut start, &mut end, &self.outgoing_connection_coordinates);
        self.start_position = start;
        self.end_position = end;
    }
}

/// Assumes the positions are sorted ascendingly.
fn recompute_extent_with(start_position: &mut f64, end_position: &mut f64, positions: &[f64]) {
    if !positions.is_empty() {
        let first = positions[0];
        let last = positions[positions.len() - 1];

        // set new start position
        if start_position.is_nan() {
            *start_position = first;
        } else {
            // min; operands are never NaN here
            *start_position = if *start_position <= first { *start_position } else { first };
        }

        // set new end position
        if end_position.is_nan() {
            *end_position = last;
        } else {
            // max; operands are never NaN here
            *end_position = if *end_position >= last { *end_position } else { last };
        }
    }
}

/// `insertSorted`. Note the quirk: each existing value is converted through
/// `Double.floatValue()` (a float cast) before being compared with the new
/// value.
pub(super) fn insert_sorted(list: &mut Vec<f64>, value: f64) {
    let mut insert_index = list.len();
    for (i, &existing) in list.iter().enumerate() {
        let next = existing as f32 as f64;
        if next == value {
            // an exactly equal value is already present in the list
            return;
        } else if next > value {
            insert_index = i;
            break;
        }
    }
    list.insert(insert_index, value);
}

/// Arena holding all hyperedge segments and their dependencies created while
/// routing one layer pair (plus temporary segments from split simulation).
#[derive(Default)]
pub struct SegmentStore {
    pub segments: Vec<HyperEdgeSegment>,
    pub dependencies: Vec<HyperEdgeSegmentDependency>,
}

impl SegmentStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn create_segment(&mut self) -> SegmentId {
        let id = self.segments.len();
        self.segments.push(HyperEdgeSegment::new());
        id
    }

    /// Adds the positions of the
    /// given port and all (transitively) connected ports.
    pub fn add_port_positions(
        &mut self,
        a: &LGraphArena,
        seg: SegmentId,
        port: LPortId,
        hyper_edge_segment_map: &mut HashMap<LPortId, SegmentId>,
        strategy: &BaseRoutingDirectionStrategy,
    ) {
        hyper_edge_segment_map.insert(port, seg);
        self.add_port_position(a, seg, port, strategy);

        // add connected ports (predecessor ports followed by successor ports)
        let mut connected_ports: Vec<LPortId> = Vec::new();
        for &edge in &a.port(port).incoming_edges {
            connected_ports.push(a.edge(edge).source.unwrap());
        }
        for &edge in &a.port(port).outgoing_edges {
            connected_ports.push(a.edge(edge).target.unwrap());
        }
        for other_port in connected_ports {
            if !hyper_edge_segment_map.contains_key(&other_port) {
                self.add_port_positions(a, seg, other_port, hyper_edge_segment_map, strategy);
            }
        }
    }

    /// Adds only this port to a segment. This is used by per-edge routing,
    /// where following every edge incident to a port would recreate a net.
    pub fn add_port_position(
        &mut self,
        a: &LGraphArena,
        seg: SegmentId,
        port: LPortId,
        strategy: &BaseRoutingDirectionStrategy,
    ) {
        self.add_port_position_with_offset(a, seg, port, strategy, 0.0);
    }

    pub fn add_port_position_with_offset(
        &mut self,
        a: &LGraphArena,
        seg: SegmentId,
        port: LPortId,
        strategy: &BaseRoutingDirectionStrategy,
        offset: f64,
    ) {
        if !self.segments[seg].ports.contains(&port) {
            self.segments[seg].ports.push(port);
        }
        let port_pos = strategy.port_position_on_hyper_node(a, port) + offset;
        if a.port(port).side == strategy.source_port_side() {
            insert_sorted(&mut self.segments[seg].incoming_connection_coordinates, port_pos);
        } else {
            insert_sorted(&mut self.segments[seg].outgoing_connection_coordinates, port_pos);
        }
        self.segments[seg].recompute_extent();
    }

    /// Returns `(newSplit,
    /// newSplitPartner)`. The new segments live in this store but are not part
    /// of any segment list.
    pub fn simulate_split(&mut self, seg: SegmentId) -> (SegmentId, SegmentId) {
        let new_split = self.create_segment();
        let new_split_partner = self.create_segment();

        let incoming = self.segments[seg].incoming_connection_coordinates.clone();
        let outgoing = self.segments[seg].outgoing_connection_coordinates.clone();
        let split_by = self.segments[seg].split_by;
        let edge = self.segments[seg].edge;

        {
            let s = &mut self.segments[new_split];
            s.incoming_connection_coordinates = incoming;
            s.edge = edge;
            s.split_by = split_by;
            s.split_partner = Some(new_split_partner);
            s.recompute_extent();
        }
        {
            let s = &mut self.segments[new_split_partner];
            s.outgoing_connection_coordinates = outgoing;
            s.edge = edge;
            s.split_partner = Some(new_split);
            s.recompute_extent();
        }

        (new_split, new_split_partner)
    }

    /// Splits this segment into two and returns the new segment.
    pub fn split_at(&mut self, seg: SegmentId, split_position: f64) -> SegmentId {
        let split_partner = self.create_segment();
        self.segments[split_partner].edge = self.segments[seg].edge;
        self.segments[seg].split_partner = Some(split_partner);
        self.segments[split_partner].split_partner = Some(seg);

        // Move all target positions over to the new segment
        let outgoing = std::mem::take(&mut self.segments[seg].outgoing_connection_coordinates);
        self.segments[split_partner].outgoing_connection_coordinates = outgoing;

        // Link the two
        self.segments[seg].outgoing_connection_coordinates.push(split_position);
        self.segments[split_partner].incoming_connection_coordinates.push(split_position);

        // Recompute their outer coordinates
        self.segments[seg].recompute_extent();
        self.segments[split_partner].recompute_extent();

        // Clear dependencies so they can be regenerated later
        while let Some(&dep) = self.segments[seg].incoming_segment_dependencies.first() {
            dependency::remove(self, dep);
        }
        while let Some(&dep) = self.segments[seg].outgoing_segment_dependencies.first() {
            dependency::remove(self, dep);
        }

        split_partner
    }
}
