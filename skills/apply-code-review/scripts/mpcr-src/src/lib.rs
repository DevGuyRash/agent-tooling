//! `mpcr` is a small internal library backing the `mpcr` CLI binary.
//!
//! It provides deterministic primitives for coordinating code review sessions:
//! - ID generation for reviewer/session/lock identifiers
//! - A file-based lock for `_session.json`
//! - Helpers for computing session paths and writing report files
//! - Typed read/modify/write operations on `_session.json`

/// Random identifier generation (id8 / hex).
pub mod id;
/// File-based lock for coordinating `_session.json` writers.
pub mod lock;
/// Path helpers for session directories and report filenames.
pub mod paths;
/// Session file (`_session.json`) schema and update operations.
pub mod session;
