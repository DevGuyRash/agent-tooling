//! Structured error types for PIASCS flows.

use std::path::Path;

use thiserror::Error;

/// Error type for all public operations.
#[derive(Debug, Error)]
pub enum AppError {
    /// I/O failure.
    #[error("io operation failed for {path}: {reason}")]
    Io { path: String, reason: String },
    /// Input validation failure.
    #[error("invalid input: {reason}")]
    InvalidInput { reason: String },
    /// HTTP request failure.
    #[error("http request failed for {url}: {reason}")]
    Http { url: String, reason: String },
    /// Serialization or parsing failure.
    #[error("serialization failed for {path}: {reason}")]
    Serialization { path: String, reason: String },
}

impl AppError {
    /// Build an I/O error variant.
    ///
    /// # Arguments
    /// * `path` - Path involved in the failing operation.
    /// * `reason` - Lower-level error converted to string.
    ///
    /// # Returns
    /// * `AppError::Io` with stable message fields.
    ///
    /// # Examples
    /// ```
    /// use std::path::Path;
    /// use piascs::error::AppError;
    ///
    /// let err = AppError::io(Path::new("cache.json"), "permission denied".to_string());
    /// assert!(matches!(err, AppError::Io { .. }));
    /// ```
    pub fn io(path: &Path, reason: String) -> Self {
        Self::Io {
            path: path.display().to_string(),
            reason,
        }
    }

    /// Build a serialization error variant.
    ///
    /// # Arguments
    /// * `path` - Path involved in serialization/parsing operation.
    /// * `reason` - Lower-level error converted to string.
    ///
    /// # Returns
    /// * `AppError::Serialization` with stable message fields.
    pub fn serialization(path: &Path, reason: String) -> Self {
        Self::Serialization {
            path: path.display().to_string(),
            reason,
        }
    }
}
