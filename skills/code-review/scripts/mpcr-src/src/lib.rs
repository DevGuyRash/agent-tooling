//! `mpcr` v2 is a machine-first coordination library for the `code-review` skill.
//!
//! The crate centers on:
//! - structured, canonical v2 artifacts,
//! - compact session ledgers that store only references,
//! - deterministic policy retrieval and rendering,
//! - hard/soft validation layers,
//! - adaptive semantic routing and convergence planning.
#![allow(
    clippy::all,
    clippy::pedantic,
    clippy::nursery,
    clippy::cargo,
    clippy::expect_used,
    clippy::indexing_slicing
)]

/// Language-agnostic static analysis helpers for optional pre-screening.
pub mod analyze;
/// Canonical v2 artifact contracts, enums, and identity helpers.
pub mod artifacts;
/// Convergence-state planning for the full-cycle workflow.
pub mod fullcycle_plan;
/// Random identifier generation (id8 / hex).
pub mod id;
/// File-based lock for coordinating `_session.toml` writers.
pub mod lock;
/// Telemetry aggregation utilities.
pub mod metrics;
/// Session and artifact path helpers.
pub mod paths;
/// Structured policy store loader and view rendering.
pub mod policy_store;
/// Static `mpcr protocol ...` retrieval surface built on the policy store.
pub mod protocol;
/// Deterministic markdown rendering from machine artifacts.
pub mod render;
/// Adaptive semantic routing and route revision handling.
pub mod router;
/// Shared routing types separated from artifact persistence.
pub mod router_types;
/// Compact v2 session ledger and reviewer/applicator operations.
pub mod session;
/// Hard/soft artifact validation.
pub mod validate;
