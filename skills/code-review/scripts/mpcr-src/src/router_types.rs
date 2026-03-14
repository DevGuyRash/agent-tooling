//! Shared routing inputs and helper types.
#![allow(missing_docs)]

use crate::artifacts::{ExecutionCapability, ModuleId, SurfaceId};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Weak history priors that may influence borderline routing decisions.
pub struct HistorySignals {
    pub prior_declines: u32,
    pub prior_reopens: u32,
}

impl Default for HistorySignals {
    fn default() -> Self {
        Self {
            prior_declines: 0,
            prior_reopens: 0,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Inputs required to build a semantic surface map and route decision.
pub struct RouteInputs {
    #[serde(default)]
    pub changed_files: Vec<String>,
    #[serde(default)]
    pub public_interfaces: Vec<String>,
    #[serde(default)]
    pub behavior_facing_artifacts: Vec<String>,
    pub execution_capability: ExecutionCapability,
    pub max_worker_count: u8,
    pub orchestrator_read_budget_lines: u16,
    pub orchestrator_read_budget_snippets: u16,
    #[serde(default)]
    pub history_signals: HistorySignals,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Signals that may justify simplification/scope-creep scrutiny.
pub struct ScopeSignals {
    pub scope_creep_detected: bool,
    pub overengineering_detected: bool,
}

impl ScopeSignals {
    /// Infer scope signals heuristically from changed file paths.
    #[must_use]
    pub fn from_changed_files(changed_files: &[String]) -> Self {
        let mut scope_creep_detected = changed_files.len() > 12;
        let mut overengineering_detected = false;
        for file in changed_files {
            let lower = file.to_ascii_lowercase();
            if lower.contains("refactor")
                || lower.contains("rewrite")
                || lower.contains("cleanup")
                || lower.contains("abstraction")
            {
                scope_creep_detected = true;
            }
            if lower.contains("framework")
                || lower.contains("builder")
                || lower.contains("adapter")
                || lower.contains("factory")
            {
                overengineering_detected = true;
            }
        }
        Self {
            scope_creep_detected,
            overengineering_detected,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Deterministic route revision request.
pub struct RouteRevisionRequest {
    #[serde(default)]
    pub discovered_surfaces: Vec<SurfaceId>,
    #[serde(default)]
    pub added_modules: Vec<ModuleId>,
    pub raise_rigor: bool,
    pub widen_architecture: bool,
}
