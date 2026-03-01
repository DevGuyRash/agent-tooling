//! `mpcr` is a small internal library backing the `mpcr` CLI binary.
//!
//! It provides deterministic primitives for coordinating code review sessions:
//! - ID generation for reviewer/session/lock identifiers
//! - A file-based lock for `_session.toml`
//! - Helpers for computing session paths and writing report files
//! - Typed read/modify/write operations on `_session.toml`

/// Language-agnostic static analysis checks for code review workers.
pub mod analyze;
/// Random identifier generation (id8 / hex).
pub mod id;
/// File-based lock for coordinating `_session.toml` writers.
pub mod lock;
/// Path helpers for session directories and report filenames.
pub mod paths;
/// Embedded protocol data for just-in-time phase guidance.
pub mod protocol;
/// Deterministic validation for review report artifacts.
pub mod report_validation;
/// Session file (`_session.toml`) schema and update operations.
pub mod session;
