//! Cache persistence helpers.

use std::fs;
use std::fs::{File, OpenOptions};
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::Duration;
use std::time::{SystemTime, UNIX_EPOCH};

use fs2::FileExt;

use crate::error::AppError;
use crate::model::CachedProfiles;
use crate::read_utf8_file_with_size_limit;

const MAX_CACHE_FILE_BYTES: u64 = 8 * 1024 * 1024;
pub(crate) const CURRENT_CACHE_SCHEMA_VERSION: u32 = 3;
const LEGACY_CACHE_SCHEMA_VERSION_V2: u32 = 2;
static TMP_FILE_NONCE_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Write cached profiles to disk.
///
/// # Arguments
/// * `cache_path` - Target JSON file path.
/// * `profiles` - Serializable profiles payload.
///
/// # Returns
/// * `Ok(())` if file write succeeded.
/// * `Err(AppError)` if serialization or file I/O fails.
///
/// # Examples
/// ```no_run
/// use architect_core::cache::write_cache;
/// use architect_core::model::CachedProfiles;
/// use std::path::Path;
///
/// let payload = CachedProfiles {
///     schema_version: 3,
///     profiles: Vec::new(),
///     unresolved_references: Vec::new(),
/// };
/// let _ = write_cache(Path::new("cache.json"), &payload);
/// ```
pub fn write_cache(cache_path: &Path, profiles: &CachedProfiles) -> Result<(), AppError> {
    const MAX_TMP_FILE_CREATE_ATTEMPTS: usize = 16;

    reject_symlink_target(cache_path)?;
    let json = serde_json::to_string_pretty(profiles)
        .map_err(|error| AppError::serialization(cache_path, error.to_string()))?;
    let mut tmp_path = None;
    for _ in 0..MAX_TMP_FILE_CREATE_ATTEMPTS {
        let candidate = cache_path.with_extension(format!("json.tmp.{}", next_tmp_file_nonce()));
        let mut tmp_file = match OpenOptions::new()
            .create_new(true)
            .write(true)
            .truncate(false)
            .open(&candidate)
        {
            Ok(file) => file,
            Err(error) if error.kind() == ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(AppError::io(&candidate, error.to_string())),
        };
        if let Err(error) = tmp_file.write_all(json.as_bytes()) {
            let _ = fs::remove_file(&candidate);
            return Err(AppError::io(&candidate, error.to_string()));
        }
        tmp_path = Some(candidate);
        break;
    }
    let tmp_path = tmp_path.ok_or_else(|| AppError::InvalidInput {
        reason: format!(
            "failed to create unique cache temp file after {} attempts for {}",
            MAX_TMP_FILE_CREATE_ATTEMPTS,
            cache_path.display()
        ),
    })?;

    fs::rename(&tmp_path, cache_path).map_err(|error| {
        let _ = fs::remove_file(&tmp_path);
        AppError::io(cache_path, error.to_string())
    })
}

fn next_tmp_file_nonce() -> String {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |duration| duration.as_nanos());
    let sequence = TMP_FILE_NONCE_COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("{timestamp}-{}-{sequence}", std::process::id())
}

/// Read cached profiles from disk.
///
/// # Arguments
/// * `cache_path` - Source JSON file path.
///
/// # Returns
/// * `Ok(CachedProfiles)` when parsing succeeds.
/// * `Err(AppError)` if file read or parse fails.
///
/// # Examples
/// ```no_run
/// use architect_core::cache::read_cache;
/// use std::path::Path;
///
/// let _ = read_cache(Path::new("cache.json"));
/// ```
pub fn read_cache(cache_path: &Path) -> Result<CachedProfiles, AppError> {
    reject_symlink_target(cache_path)?;
    let payload = read_utf8_file_with_size_limit(cache_path, MAX_CACHE_FILE_BYTES, "cache file")?;
    let mut parsed: CachedProfiles = serde_json::from_str(&payload)
        .map_err(|error| AppError::serialization(cache_path, error.to_string()))?;
    if parsed.schema_version == CURRENT_CACHE_SCHEMA_VERSION {
        return Ok(parsed);
    }
    if parsed.schema_version == LEGACY_CACHE_SCHEMA_VERSION_V2 {
        // Schema v2 payloads remain structurally compatible; normalize in-memory.
        parsed.schema_version = CURRENT_CACHE_SCHEMA_VERSION;
        return Ok(parsed);
    }
    Err(AppError::InvalidInput {
        reason: format!(
            "unsupported cache schema_version {} in {}; expected {}. run refresh to regenerate the cache file",
            parsed.schema_version,
            cache_path.display(),
            CURRENT_CACHE_SCHEMA_VERSION
        ),
    })
}

fn path_is_symlink(path: &Path) -> Result<bool, AppError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => Ok(metadata.file_type().is_symlink()),
        Err(error) if error.kind() == ErrorKind::NotFound => Ok(false),
        Err(error) => Err(AppError::io(path, error.to_string())),
    }
}

/// Execute an operation while holding an exclusive lock for the cache path.
///
/// The lock file is `<cache_path>.lock`. Symlink lock targets are rejected to
/// avoid lock redirection.
///
/// Returns `AppError::InvalidInput` on platforms where lock-file identity
/// checks are unavailable.
pub fn with_cache_lock<T, F>(cache_path: &Path, operation: F) -> Result<T, AppError>
where
    F: FnOnce() -> Result<T, AppError>,
{
    const MAX_LOCK_ACQUIRE_ATTEMPTS: usize = 50;
    const LOCK_RETRY_DELAY_MS: u64 = 25;

    ensure_lock_identity_supported(cache_path)?;
    let lock_path = lock_path_for_cache(cache_path);
    let mut operation = Some(operation);

    for _attempt in 0..MAX_LOCK_ACQUIRE_ATTEMPTS {
        reject_symlink_target(&lock_path)?;
        let lock_file = open_lock_file(&lock_path)?;
        match lock_file.try_lock_exclusive() {
            Ok(()) => {}
            Err(error) if is_lock_contention(&error) => {
                thread::sleep(Duration::from_millis(LOCK_RETRY_DELAY_MS));
                continue;
            }
            Err(error) => return Err(AppError::io(&lock_path, error.to_string())),
        }

        if !lock_path_matches_file(&lock_path, &lock_file)? {
            lock_file
                .unlock()
                .map_err(|error| AppError::io(&lock_path, error.to_string()))?;
            thread::sleep(Duration::from_millis(LOCK_RETRY_DELAY_MS));
            continue;
        }

        let outcome = operation
            .take()
            // INVARIANT: `operation` is consumed exactly once on the successful lock path.
            .expect("cache lock operation should only run once")();
        lock_file
            .unlock()
            .map_err(|error| AppError::io(&lock_path, error.to_string()))?;
        return outcome;
    }

    Err(AppError::InvalidInput {
        reason: format!(
            "failed to acquire stable cache lock after {} attempts for {}",
            MAX_LOCK_ACQUIRE_ATTEMPTS,
            lock_path.display()
        ),
    })
}

fn is_lock_contention(error: &std::io::Error) -> bool {
    error.kind() == ErrorKind::WouldBlock
}

fn lock_path_for_cache(cache_path: &Path) -> PathBuf {
    let mut lock_path = cache_path.as_os_str().to_os_string();
    lock_path.push(".lock");
    PathBuf::from(lock_path)
}

fn open_lock_file(lock_path: &Path) -> Result<File, AppError> {
    OpenOptions::new()
        .create(true)
        .read(true)
        .write(true)
        .truncate(false)
        .open(lock_path)
        .map_err(|error| AppError::io(lock_path, error.to_string()))
}

#[cfg(any(unix, windows))]
fn ensure_lock_identity_supported(_cache_path: &Path) -> Result<(), AppError> {
    Ok(())
}

#[cfg(all(not(unix), not(windows)))]
fn ensure_lock_identity_supported(cache_path: &Path) -> Result<(), AppError> {
    Err(AppError::InvalidInput {
        reason: format!(
            "cache locking for {} requires supported lock-file identity checks; this platform is unsupported",
            cache_path.display()
        ),
    })
}

#[cfg(unix)]
fn lock_path_matches_file(lock_path: &Path, lock_file: &File) -> Result<bool, AppError> {
    use std::os::unix::fs::MetadataExt;

    if path_is_symlink(lock_path)? {
        return Err(AppError::InvalidInput {
            reason: format!(
                "refusing to lock cache through symlink path {}",
                lock_path.display()
            ),
        });
    }

    let path_meta =
        fs::metadata(lock_path).map_err(|error| AppError::io(lock_path, error.to_string()))?;
    let file_meta = lock_file
        .metadata()
        .map_err(|error| AppError::io(lock_path, error.to_string()))?;
    Ok(path_meta.dev() == file_meta.dev() && path_meta.ino() == file_meta.ino())
}

#[cfg(windows)]
fn lock_path_matches_file(lock_path: &Path, lock_file: &File) -> Result<bool, AppError> {
    use std::os::windows::fs::MetadataExt;

    if path_is_symlink(lock_path)? {
        return Err(AppError::InvalidInput {
            reason: format!(
                "refusing to lock cache through symlink path {}",
                lock_path.display()
            ),
        });
    }

    let path_meta =
        fs::metadata(lock_path).map_err(|error| AppError::io(lock_path, error.to_string()))?;
    let file_meta = lock_file
        .metadata()
        .map_err(|error| AppError::io(lock_path, error.to_string()))?;
    let path_volume = path_meta.volume_serial_number();
    let file_volume = file_meta.volume_serial_number();
    let path_index = path_meta.file_index();
    let file_index = file_meta.file_index();
    Ok(path_volume.is_some()
        && path_index.is_some()
        && path_volume == file_volume
        && path_index == file_index)
}

fn reject_symlink_target(path: &Path) -> Result<(), AppError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink() {
                return Err(AppError::InvalidInput {
                    reason: format!(
                        "refusing to access cache through symlink path {}",
                        path.display()
                    ),
                });
            }
            Ok(())
        }
        Err(error) if error.kind() == ErrorKind::NotFound => Ok(()),
        Err(error) => Err(AppError::io(path, error.to_string())),
    }
}

#[cfg(all(not(unix), not(windows)))]
fn lock_path_matches_file(lock_path: &Path, _lock_file: &File) -> Result<bool, AppError> {
    Err(AppError::InvalidInput {
        reason: format!(
            "cache lock identity verification for {} requires supported platform metadata checks",
            lock_path.display()
        ),
    })
}

#[cfg(test)]
mod tests {
    use tempfile::tempdir;

    use super::*;
    use crate::model::{ImageProfile, Platform, RuntimeProfile};

    #[test]
    fn write_cache_persists_payload_for_valid_path() {
        let tmp = tempdir().expect("tempdir should be created");
        let cache_path = tmp.path().join("cache.json");
        let payload = CachedProfiles {
            schema_version: 3,
            profiles: vec![ImageProfile {
                id: "IMG-1".to_string(),
                image: "docker.io/library/nginx:1.27".to_string(),
                docs_url: Some("https://hub.docker.com/_/nginx".to_string()),
                dockerfile_url: None,
                digest: Some("sha256:123".to_string()),
                config_digest: Some("sha256:456".to_string()),
                platforms: vec![Platform {
                    os: "linux".to_string(),
                    arch: "amd64".to_string(),
                }],
                runtime: RuntimeProfile::default(),
                sources: Vec::new(),
                notes: vec!["unit-test".to_string()],
                researched_config: Default::default(),
            }],
            unresolved_references: vec!["nginx:${TAG}".to_string()],
        };

        write_cache(&cache_path, &payload).expect("cache write should succeed");
        let reparsed = read_cache(&cache_path).expect("cache read should succeed");
        assert_eq!(reparsed, payload);
    }

    #[test]
    fn read_cache_returns_error_for_missing_file() {
        let tmp = tempdir().expect("tempdir should be created");
        let missing = tmp.path().join("missing.json");
        let result = read_cache(&missing);
        assert!(matches!(result, Err(AppError::Io { .. })));
    }

    #[test]
    fn read_cache_rejects_oversized_file() {
        let tmp = tempdir().expect("tempdir should be created");
        let cache_path = tmp.path().join("cache.json");
        let file = File::create(&cache_path).expect("cache file should be created");
        file.set_len(MAX_CACHE_FILE_BYTES + 1)
            .expect("cache file should be sized");

        let result = read_cache(&cache_path);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[cfg(unix)]
    #[test]
    fn write_cache_rejects_symlink_target() {
        use std::os::unix::fs::symlink;

        let tmp = tempdir().expect("tempdir should be created");
        let target = tmp.path().join("target.json");
        let symlink_path = tmp.path().join("cache.json");
        symlink(&target, &symlink_path).expect("symlink should be created");
        let payload = CachedProfiles {
            schema_version: 3,
            profiles: Vec::new(),
            unresolved_references: Vec::new(),
        };

        let result = write_cache(&symlink_path, &payload);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[cfg(unix)]
    #[test]
    fn read_cache_rejects_symlink_target() {
        use std::os::unix::fs::symlink;

        let tmp = tempdir().expect("tempdir should be created");
        let target = tmp.path().join("target.json");
        fs::write(
            &target,
            r#"{"schema_version":3,"profiles":[],"unresolved_references":[]}"#,
        )
        .expect("target cache should be written");
        let symlink_path = tmp.path().join("cache.json");
        symlink(&target, &symlink_path).expect("symlink should be created");

        let result = read_cache(&symlink_path);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn read_cache_upgrades_schema_version_2_payload() {
        let tmp = tempdir().expect("tempdir should be created");
        let cache_path = tmp.path().join("cache.json");
        fs::write(
            &cache_path,
            r#"{"schema_version":2,"profiles":[],"unresolved_references":[]}"#,
        )
        .expect("cache file should be written");

        let result = read_cache(&cache_path).expect("schema v2 should be accepted");
        assert_eq!(result.schema_version, CURRENT_CACHE_SCHEMA_VERSION);
    }

    #[test]
    fn read_cache_rejects_unknown_schema_version() {
        let tmp = tempdir().expect("tempdir should be created");
        let cache_path = tmp.path().join("cache.json");
        fs::write(
            &cache_path,
            r#"{"schema_version":99,"profiles":[],"unresolved_references":[]}"#,
        )
        .expect("cache file should be written");

        let result = read_cache(&cache_path);
        match result {
            Err(AppError::InvalidInput { reason }) => {
                assert!(reason.contains("schema_version 99"));
                assert!(reason.contains("run refresh"));
            }
            other => panic!("expected InvalidInput for unsupported schema, got {other:?}"),
        }
    }

    #[test]
    fn with_cache_lock_runs_operation_once() {
        let tmp = tempdir().expect("tempdir should be created");
        let cache_path = tmp.path().join("cache.json");
        let mut invoked = 0usize;
        let outcome = with_cache_lock(&cache_path, || {
            invoked += 1;
            Ok::<usize, AppError>(42)
        })
        .expect("lock operation should succeed");
        assert_eq!(outcome, 42);
        assert_eq!(invoked, 1);
    }

    #[test]
    fn with_cache_lock_retries_when_lock_is_temporarily_contended() {
        let tmp = tempdir().expect("tempdir should be created");
        let cache_path = tmp.path().join("cache.json");
        let lock_path = lock_path_for_cache(&cache_path);
        let held_lock = open_lock_file(&lock_path).expect("lock file should be opened");
        held_lock
            .lock_exclusive()
            .expect("initial lock should be acquired");

        let lock_path_clone = cache_path.clone();
        let worker = thread::spawn(move || with_cache_lock(&lock_path_clone, || Ok(7usize)));
        thread::sleep(Duration::from_millis(30));
        held_lock.unlock().expect("held lock should be released");

        let outcome = worker
            .join()
            .expect("lock worker should complete")
            .expect("lock worker should eventually acquire lock");
        assert_eq!(outcome, 7);
    }

    #[test]
    fn with_cache_lock_tolerates_longer_lock_contention_windows() {
        let tmp = tempdir().expect("tempdir should be created");
        let cache_path = tmp.path().join("cache.json");
        let lock_path = lock_path_for_cache(&cache_path);
        let held_lock = open_lock_file(&lock_path).expect("lock file should be opened");
        held_lock
            .lock_exclusive()
            .expect("initial lock should be acquired");

        let lock_path_clone = cache_path.clone();
        let worker = thread::spawn(move || with_cache_lock(&lock_path_clone, || Ok(11usize)));
        thread::sleep(Duration::from_millis(180));
        held_lock.unlock().expect("held lock should be released");

        let outcome = worker
            .join()
            .expect("lock worker should complete")
            .expect("lock worker should eventually acquire lock");
        assert_eq!(outcome, 11);
    }

    #[cfg(unix)]
    #[test]
    fn is_lock_contention_does_not_treat_ebusy_as_flock_contention() {
        let error = std::io::Error::from_raw_os_error(16);
        assert!(!is_lock_contention(&error));
    }

    #[cfg(unix)]
    #[test]
    fn with_cache_lock_rejects_symlink_lock_path() {
        use std::os::unix::fs::symlink;

        let tmp = tempdir().expect("tempdir should be created");
        let cache_path = tmp.path().join("cache.json");
        let lock_path = lock_path_for_cache(&cache_path);
        let lock_target = tmp.path().join("lock-target");
        fs::write(&lock_target, "").expect("lock target should be created");
        symlink(&lock_target, &lock_path).expect("lock symlink should be created");

        let result = with_cache_lock(&cache_path, || Ok::<(), AppError>(()));
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[cfg(all(not(unix), not(windows)))]
    #[test]
    fn with_cache_lock_rejects_unsupported_platform() {
        let tmp = tempdir().expect("tempdir should be created");
        let cache_path = tmp.path().join("cache.json");

        let result = with_cache_lock(&cache_path, || Ok::<usize, AppError>(9));
        match result {
            Err(AppError::InvalidInput { reason }) => {
                assert!(reason.contains("requires supported"));
            }
            other => panic!("expected InvalidInput for unsupported platform, got {other:?}"),
        }
    }
}
