//! Random identifier generation utilities for `mpcr`.
//!
//! Identifiers are intended for:
//! - `reviewer_id` / `session_id` (8 characters)
//! - lock owners for `_session.json.lock` (8 characters)

use anyhow::Context;
use rand::RngCore;

fn hex_digit(nibble: u8) -> u8 {
    match nibble {
        0..=9 => b'0' + nibble,
        10..=15 => b'a' + (nibble - 10),
        // Defensive fallback; callers provide only 0..=15.
        _ => b'0',
    }
}

/// Generate a lowercase hex identifier of length `2 * bytes`.
///
/// This uses OS-backed randomness (`rand::rngs::OsRng`) and performs a manual hex encoding
/// to avoid pulling in an additional dependency.
pub fn random_hex_id(bytes: usize) -> anyhow::Result<String> {
    let mut raw = vec![0_u8; bytes];
    rand::rngs::OsRng
        .try_fill_bytes(&mut raw)
        .context("read OS randomness")?;

    // Manual hex encoding (avoid extra deps).
    let mut out = Vec::with_capacity(bytes.saturating_mul(2));
    for b in raw {
        out.push(hex_digit(b >> 4));
        out.push(hex_digit(b & 0x0f));
    }
    Ok(String::from_utf8_lossy(&out).into_owned())
}

/// Generate an 8-character lowercase hex identifier.
///
/// This is a convenience wrapper around `random_hex_id(4)`.
pub fn random_id8() -> anyhow::Result<String> {
    random_hex_id(4)
}
