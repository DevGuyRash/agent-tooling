//! File-based lock implementation for coordinating `_session.json` updates.
//!
//! The lock is represented by a file named `_session.json.lock` inside the session directory.
//! Lock acquisition uses `create_new(true)` for exclusivity and retries with exponential backoff.

use anyhow::Context;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::thread::sleep;
use std::time::Duration;

const DEFAULT_MAX_RETRIES: usize = 8;
const INITIAL_BACKOFF_MS: u64 = 100;
const MAX_BACKOFF_MS: u64 = 6_400;

#[derive(Debug, Clone, Copy)]
/// Configuration for [`acquire_lock`].
pub struct LockConfig {
    /// Maximum number of retry attempts when the lock file already exists.
    pub max_retries: usize,
}

impl Default for LockConfig {
    fn default() -> Self {
        Self {
            max_retries: DEFAULT_MAX_RETRIES,
        }
    }
}

#[derive(Debug)]
/// RAII-style guard for a held session lock.
///
/// When dropped, this will best-effort release the lock *only if* the lock file still contains
/// the same owner identifier.
pub struct LockGuard {
    lock_file: Option<PathBuf>,
    owner: String,
}

impl LockGuard {
    /// Release the lock early, consuming the guard.
    ///
    /// # Errors
    /// Returns an error if the lock file exists but cannot be read or removed.
    pub fn release(mut self) -> anyhow::Result<()> {
        self.release_inner()
    }

    fn release_inner(&mut self) -> anyhow::Result<()> {
        let Some(lock_file) = self.lock_file.take() else {
            return Ok(());
        };

        let owner = match fs::read_to_string(&lock_file) {
            Ok(s) => s.trim_end().to_string(),
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(err) => return Err(err).context("read lock file owner"),
        };

        if owner == self.owner {
            match fs::remove_file(&lock_file) {
                Ok(()) => Ok(()),
                Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(()),
                Err(err) => Err(err).context("remove lock file"),
            }
        } else {
            Ok(())
        }
    }
}

impl Drop for LockGuard {
    fn drop(&mut self) {
        let _ = self.release_inner();
    }
}

/// Compute the path to the lock file (`_session.json.lock`) for `session_dir`.
#[must_use]
pub fn lock_file_path(session_dir: &Path) -> PathBuf {
    session_dir.join("_session.json.lock")
}

/// Release the session lock if `owner` matches the contents of the lock file.
///
/// This is best-effort: if the lock file does not exist, the operation succeeds.
///
/// # Errors
/// Returns an error if the lock file exists but cannot be read or removed.
pub fn release_lock(session_dir: &Path, owner: impl Into<String>) -> anyhow::Result<()> {
    let mut guard = LockGuard {
        lock_file: Some(lock_file_path(session_dir)),
        owner: owner.into(),
    };
    guard.release_inner()
}

/// Acquire the session lock and return a guard that releases it on drop.
///
/// If the lock file already exists, this will retry up to `cfg.max_retries` times with exponential
/// backoff (100ms → 200ms → ... → 6400ms) and then return an error with the message `LOCK_TIMEOUT`.
///
/// # Errors
/// Returns an error if the lock file cannot be created or written after retries.
pub fn acquire_lock(
    session_dir: &Path,
    owner: impl Into<String>,
    cfg: LockConfig,
) -> anyhow::Result<LockGuard> {
    let owner = owner.into();
    let lock_file = lock_file_path(session_dir);

    let mut attempt: usize = 0;
    let mut wait_ms: u64 = INITIAL_BACKOFF_MS;

    loop {
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&lock_file)
        {
            Ok(mut f) => {
                writeln!(f, "{owner}").context("write lock owner")?;
                f.flush().context("flush lock owner")?;
                return Ok(LockGuard {
                    lock_file: Some(lock_file),
                    owner,
                });
            }
            Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {
                if attempt >= cfg.max_retries {
                    return Err(anyhow::anyhow!("LOCK_TIMEOUT"));
                }
                sleep(Duration::from_millis(wait_ms));
                attempt = attempt.saturating_add(1);
                wait_ms = (wait_ms.saturating_mul(2)).min(MAX_BACKOFF_MS);
            }
            Err(err) => {
                return Err(err)
                    .with_context(|| format!("create lock file {}", lock_file.display()))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn release_lock_handles_missing_and_mismatch() -> anyhow::Result<()> {
        let dir = tempfile::tempdir()?;
        let session_dir = dir.path();

        // Missing lock file should be ok.
        release_lock(session_dir, "deadbeef")?;

        // Mismatched owner should leave file intact.
        let lock_file = lock_file_path(session_dir);
        fs::write(&lock_file, "owner-a\n")?;
        release_lock(session_dir, "owner-b")?;
        assert!(lock_file.exists());

        // Matching owner should remove the lock file.
        release_lock(session_dir, "owner-a")?;
        assert!(!lock_file.exists());

        Ok(())
    }
}
