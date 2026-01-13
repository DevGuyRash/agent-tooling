//! Random identifier generation utilities for `mpcr`.
//!
//! Identifiers are intended for:
//! - `reviewer_id` / `session_id` (8 characters)
//! - lock owners for `_session.json.lock` (8 characters)

use anyhow::Context;
use rand::RngCore;

const fn hex_digit(nibble: u8) -> u8 {
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
///
/// # Errors
/// Returns an error if OS randomness cannot be read.
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
///
/// # Errors
/// Returns an error if OS randomness cannot be read.
pub fn random_id8() -> anyhow::Result<String> {
    random_hex_id(4)
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::ensure;

    #[test]
    fn hex_digit_and_random_id_shape() -> anyhow::Result<()> {
        ensure!(hex_digit(0) == b'0');
        ensure!(hex_digit(9) == b'9');
        ensure!(hex_digit(10) == b'a');
        ensure!(hex_digit(15) == b'f');
        ensure!(hex_digit(16) == b'0');

        let empty = random_hex_id(0)?;
        ensure!(empty == "");

        let one = random_hex_id(1)?;
        ensure!(one.len() == 2);
        ensure!(one.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')));

        let id8 = random_id8()?;
        ensure!(id8.len() == 8);
        ensure!(id8.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')));

        Ok(())
    }
}
