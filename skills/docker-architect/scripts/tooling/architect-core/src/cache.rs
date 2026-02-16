//! Cache persistence helpers.

use std::fs;
use std::io::ErrorKind;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::error::AppError;
use crate::model::CachedProfiles;

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
///     schema_version: 2,
///     profiles: Vec::new(),
///     unresolved_references: Vec::new(),
/// };
/// let _ = write_cache(Path::new("cache.json"), &payload);
/// ```
pub fn write_cache(cache_path: &Path, profiles: &CachedProfiles) -> Result<(), AppError> {
    reject_symlink_target(cache_path)?;
    let json = serde_json::to_string_pretty(profiles)
        .map_err(|error| AppError::serialization(cache_path, error.to_string()))?;
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |duration| duration.as_nanos());
    let tmp_path = cache_path.with_extension(format!("json.tmp.{nonce}"));
    fs::write(&tmp_path, json).map_err(|error| AppError::io(&tmp_path, error.to_string()))?;
    fs::rename(&tmp_path, cache_path).map_err(|error| {
        let _ = fs::remove_file(&tmp_path);
        AppError::io(cache_path, error.to_string())
    })
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
    let payload = fs::read_to_string(cache_path)
        .map_err(|error| AppError::io(cache_path, error.to_string()))?;
    serde_json::from_str(&payload)
        .map_err(|error| AppError::serialization(cache_path, error.to_string()))
}

fn reject_symlink_target(path: &Path) -> Result<(), AppError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink() {
                return Err(AppError::InvalidInput {
                    reason: format!(
                        "refusing to write cache through symlink path {}",
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
            schema_version: 2,
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

    #[cfg(unix)]
    #[test]
    fn write_cache_rejects_symlink_target() {
        use std::os::unix::fs::symlink;

        let tmp = tempdir().expect("tempdir should be created");
        let target = tmp.path().join("target.json");
        let symlink_path = tmp.path().join("cache.json");
        symlink(&target, &symlink_path).expect("symlink should be created");
        let payload = CachedProfiles {
            schema_version: 2,
            profiles: Vec::new(),
            unresolved_references: Vec::new(),
        };

        let result = write_cache(&symlink_path, &payload);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }
}
