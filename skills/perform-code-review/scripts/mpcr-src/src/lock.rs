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
pub struct LockConfig {
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
pub struct LockGuard {
    lock_file: Option<PathBuf>,
    owner: String,
}

impl LockGuard {
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

pub fn lock_file_path(session_dir: &Path) -> PathBuf {
    session_dir.join("_session.json.lock")
}

pub fn release_lock(session_dir: &Path, owner: impl Into<String>) -> anyhow::Result<()> {
    let mut guard = LockGuard {
        lock_file: Some(lock_file_path(session_dir)),
        owner: owner.into(),
    };
    guard.release_inner()
}

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
