//! File-based lock implementation for coordinating `_session.json` updates.
//!
//! The lock is represented by a file named `_session.json.lock` inside the session directory.
//! Lock acquisition uses `create_new(true)` for exclusivity and retries with exponential backoff.
//!
//! Stale lock recovery: when a lock file is older than [`STALE_LOCK_SECS`], recovery
//! is attempted only if the embedded owner PID is no longer alive.

use anyhow::Context;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::thread::sleep;
use std::time::{Duration, SystemTime};

const DEFAULT_MAX_RETRIES: usize = 8;
const INITIAL_BACKOFF_MS: u64 = 100;
const MAX_BACKOFF_MS: u64 = 6_400;
const STALE_LOCK_SECS: u64 = 60;

#[derive(Debug, Clone, Copy)]
/// Configuration for [`acquire_lock`].
pub struct LockConfig {
    /// Maximum number of retry attempts when the lock file already exists.
    pub max_retries: usize,
    /// Seconds after which an existing lock file is considered stale and removed.
    pub stale_after_secs: u64,
}

impl Default for LockConfig {
    fn default() -> Self {
        Self {
            max_retries: DEFAULT_MAX_RETRIES,
            stale_after_secs: STALE_LOCK_SECS,
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

fn parse_lock_owner_and_pid(raw: &str) -> (String, Option<u32>) {
    let mut lines = raw.lines();
    let owner = lines
        .next()
        .map_or_else(String::new, |line| line.to_string());
    let pid = lines.next().and_then(|line| {
        line.strip_prefix("pid:")
            .and_then(|rest| rest.trim().parse::<u32>().ok())
    });
    (owner, pid)
}

fn read_lock_owner_and_pid(lock_file: &Path) -> std::io::Result<(String, Option<u32>)> {
    let raw = fs::read_to_string(lock_file)?;
    Ok(parse_lock_owner_and_pid(&raw))
}

fn is_pid_alive(pid: u32) -> bool {
    #[cfg(target_os = "linux")]
    {
        Path::new("/proc").join(pid.to_string()).exists()
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = pid;
        true
    }
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

        let owner = match read_lock_owner_and_pid(&lock_file) {
            Ok((owner, _pid)) => owner,
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

    /// Refresh the lock file mtime as a heartbeat signal.
    pub fn touch_lock(&self) -> anyhow::Result<()> {
        if let Some(ref lock_file) = self.lock_file {
            let mut f = std::fs::OpenOptions::new()
                .write(true)
                .truncate(true)
                .open(lock_file)
                .context("touch lock file")?;
            writeln!(f, "{}", self.owner).context("write lock owner")?;
            writeln!(f, "pid:{}", std::process::id()).context("write lock owner pid")?;
            f.flush().context("flush lock owner")?;
        }
        Ok(())
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

/// Attempt to remove a stale lock file if its modification time exceeds
/// `stale_after_secs` and the recorded PID is no longer alive.
///
/// This is best-effort: any I/O or time errors are silently ignored so the caller
/// falls back to the normal retry/timeout loop.
fn try_remove_stale_lock(lock_file: &Path, stale_after_secs: u64) -> bool {
    let Ok(metadata) = fs::metadata(lock_file) else {
        return false;
    };
    let Ok(modified) = metadata.modified() else {
        return false;
    };
    let Ok(age) = SystemTime::now().duration_since(modified) else {
        return false;
    };
    if age.as_secs() < stale_after_secs {
        return false;
    }
    let Ok((_owner, lock_pid)) = read_lock_owner_and_pid(lock_file) else {
        return false;
    };
    let Some(lock_pid) = lock_pid else {
        return false;
    };
    if is_pid_alive(lock_pid) {
        return false;
    }
    // Double-check: sleep briefly and re-verify mtime hasn't been refreshed (heartbeat).
    std::thread::sleep(Duration::from_millis(200));
    let Ok(metadata2) = fs::metadata(lock_file) else {
        return false;
    };
    let Ok(modified2) = metadata2.modified() else {
        return false;
    };
    if modified2 != modified {
        return false;
    }
    fs::remove_file(lock_file).is_ok()
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
                writeln!(f, "pid:{}", std::process::id()).context("write lock owner pid")?;
                f.flush().context("flush lock owner")?;
                return Ok(LockGuard {
                    lock_file: Some(lock_file),
                    owner,
                });
            }
            Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {
                if attempt == 0 && try_remove_stale_lock(&lock_file, cfg.stale_after_secs) {
                    continue;
                }
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
    use anyhow::ensure;

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
        ensure!(lock_file.exists());

        // Matching owner should remove the lock file.
        release_lock(session_dir, "owner-a")?;
        ensure!(!lock_file.exists());

        Ok(())
    }

    #[test]
    fn stale_lock_is_recovered_on_acquire() -> anyhow::Result<()> {
        let dir = tempfile::tempdir()?;
        let session_dir = dir.path();
        let lock_file = lock_file_path(session_dir);

        fs::write(&lock_file, "crashed-owner\npid:999999\n")?;

        // Use stale_after_secs=0 so ANY existing file is considered stale.
        let cfg = LockConfig {
            max_retries: 0,
            stale_after_secs: 0,
        };
        let guard = acquire_lock(session_dir, "new-owner", cfg)?;
        ensure!(lock_file.exists(), "lock should be held");

        let raw_owner = fs::read_to_string(&lock_file)?;
        let (owner, pid) = parse_lock_owner_and_pid(&raw_owner);
        ensure!(
            owner == "new-owner",
            "lock should be owned by new-owner, got: {raw_owner:?}"
        );
        ensure!(pid.is_some(), "lock metadata should include owner pid");
        guard.release()?;
        Ok(())
    }

    #[test]
    fn stale_lock_with_live_pid_is_not_recovered() -> anyhow::Result<()> {
        let dir = tempfile::tempdir()?;
        let session_dir = dir.path();
        let lock_file = lock_file_path(session_dir);

        fs::write(
            &lock_file,
            format!("active-owner\npid:{}\n", std::process::id()),
        )?;

        let cfg = LockConfig {
            max_retries: 0,
            stale_after_secs: 0,
        };
        let result = acquire_lock(session_dir, "new-owner", cfg);
        ensure!(result.is_err(), "live owner lock should not be reclaimed");
        ensure!(lock_file.exists(), "live owner lock should remain");
        Ok(())
    }

    #[test]
    fn fresh_lock_is_not_removed_as_stale() -> anyhow::Result<()> {
        let dir = tempfile::tempdir()?;
        let session_dir = dir.path();
        let lock_file = lock_file_path(session_dir);

        fs::write(&lock_file, "active-owner\n")?;

        let cfg = LockConfig {
            max_retries: 0,
            stale_after_secs: 60,
        };
        let result = acquire_lock(session_dir, "new-owner", cfg);
        ensure!(result.is_err(), "should fail — lock is fresh, not stale");
        ensure!(lock_file.exists(), "fresh lock should still exist");

        let owner = fs::read_to_string(&lock_file)?;
        ensure!(
            owner.trim() == "active-owner",
            "lock should still belong to active-owner"
        );
        Ok(())
    }
}
