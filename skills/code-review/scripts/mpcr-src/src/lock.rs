//! File-based lock implementation for coordinating session and agent updates.
//!
//! The canonical lock is `_session.lock`. Older runtimes may still leave behind
//! `_session.toml.lock` or `_session.json.lock`; those are treated as compatibility
//! lock files so new writers do not trample an older in-flight mutation.

use crate::paths;
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
/// RAII-style guard for a held lock.
///
/// When dropped, this best-effort releases the canonical or compatibility lock file
/// only if it still contains the same owner identifier.
pub struct LockGuard {
    lock_file: Option<PathBuf>,
    owner: String,
}

fn parse_lock_owner_and_pid(raw: &str) -> (String, Option<u32>) {
    let mut lines = raw.lines();
    let owner = lines.next().map_or_else(String::new, ToString::to_string);
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

#[allow(clippy::missing_const_for_fn)]
fn is_pid_alive(pid: u32) -> bool {
    #[cfg(target_os = "linux")]
    {
        Path::new("/proc").join(pid.to_string()).exists()
    }
    #[cfg(all(unix, not(target_os = "linux")))]
    {
        let status = std::process::Command::new("kill")
            .arg("-0")
            .arg(pid.to_string())
            .status();
        matches!(status, Ok(exit) if exit.success())
    }
    #[cfg(not(unix))]
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
    ///
    /// # Errors
    /// Returns an error if the lock file exists and cannot be opened, written, or flushed.
    pub fn touch_lock(&self) -> anyhow::Result<()> {
        if let Some(ref lock_file) = self.lock_file {
            let mut file = std::fs::OpenOptions::new()
                .write(true)
                .truncate(true)
                .open(lock_file)
                .context("touch lock file")?;
            writeln!(file, "{}", self.owner).context("write lock owner")?;
            writeln!(file, "pid:{}", std::process::id()).context("write lock owner pid")?;
            file.flush().context("flush lock owner")?;
        }
        Ok(())
    }
}

impl Drop for LockGuard {
    fn drop(&mut self) {
        let _ = self.release_inner();
    }
}

fn compatibility_lock_paths(dir: &Path) -> Vec<PathBuf> {
    let mut paths = vec![lock_file_path(dir)];
    paths.extend(paths::legacy_lock_paths(dir));
    paths
}

/// Compute the canonical lock file path (`_session.lock`) for `dir`.
#[must_use]
pub fn lock_file_path(dir: &Path) -> PathBuf {
    dir.join("_session.lock")
}

/// Release the canonical or compatibility lock if `owner` matches the file contents.
///
/// This is best-effort: if no known lock file exists, the operation succeeds.
///
/// # Errors
/// Returns an error if a matching lock file exists but cannot be read or removed.
pub fn release_lock(dir: &Path, owner: impl Into<String>) -> anyhow::Result<()> {
    let owner = owner.into();
    for path in compatibility_lock_paths(dir) {
        let mut guard = LockGuard {
            lock_file: Some(path),
            owner: owner.clone(),
        };
        guard.release_inner()?;
    }
    Ok(())
}

/// Attempt to remove a stale lock file if its modification time exceeds
/// `stale_after_secs` and the recorded PID is no longer alive.
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
    sleep(Duration::from_millis(200));
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

fn conflicting_lock_paths(dir: &Path, canonical: &Path) -> Vec<PathBuf> {
    compatibility_lock_paths(dir)
        .into_iter()
        .filter(|path| path != canonical && path.exists())
        .collect()
}

/// Acquire the canonical lock and return a guard that releases it on drop.
///
/// If the canonical or compatibility lock file already exists, this retries up to
/// `cfg.max_retries` times with exponential backoff before returning `LOCK_TIMEOUT`.
///
/// # Errors
/// Returns an error if the lock file cannot be created or written after retries.
pub fn acquire_lock(
    dir: &Path,
    owner: impl Into<String>,
    cfg: LockConfig,
) -> anyhow::Result<LockGuard> {
    let owner = owner.into();
    let lock_file = lock_file_path(dir);
    let mut attempt: usize = 0;
    let mut wait_ms: u64 = INITIAL_BACKOFF_MS;

    loop {
        let mut blocked = false;
        for path in conflicting_lock_paths(dir, &lock_file) {
            if attempt == 0 && try_remove_stale_lock(&path, cfg.stale_after_secs) {
                continue;
            }
            blocked = true;
        }
        if blocked {
            if attempt >= cfg.max_retries {
                return Err(anyhow::anyhow!("LOCK_TIMEOUT"));
            }
            sleep(Duration::from_millis(wait_ms));
            attempt = attempt.saturating_add(1);
            wait_ms = (wait_ms.saturating_mul(2)).min(MAX_BACKOFF_MS);
            continue;
        }

        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&lock_file)
        {
            Ok(mut file) => {
                writeln!(file, "{owner}").context("write lock owner")?;
                writeln!(file, "pid:{}", std::process::id()).context("write lock owner pid")?;
                file.flush().context("flush lock owner")?;
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
    use tempfile::tempdir;

    #[test]
    fn uses_canonical_lock_name_and_releases_compatibility_files() -> anyhow::Result<()> {
        let temp = tempdir()?;
        let dir = temp.path();
        ensure!(lock_file_path(dir) == dir.join("_session.lock"));

        let legacy = dir.join("_session.toml.lock");
        fs::write(&legacy, "owner1234\npid:1\n")?;
        release_lock(dir, "owner1234")?;
        ensure!(!legacy.exists());
        Ok(())
    }

    #[test]
    fn acquire_fails_while_compatibility_lock_exists() -> anyhow::Result<()> {
        let temp = tempdir()?;
        let dir = temp.path();
        fs::write(dir.join("_session.toml.lock"), "owner1234\npid:999999\n")?;
        let err = acquire_lock(
            dir,
            "owner5678",
            LockConfig {
                max_retries: 0,
                stale_after_secs: u64::MAX,
            },
        )
        .expect_err("compatibility lock should block acquisition");
        ensure!(err.to_string().contains("LOCK_TIMEOUT"));
        Ok(())
    }
}
