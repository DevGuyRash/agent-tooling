//! Deterministic research toolkit for container architecture skill outputs.
//!
//! # Overview
//! This crate provides deterministic extraction, metadata collection, cache management,
//! rendering, and validation primitives that are consumed by the `pca` CLI.

use std::fs;

pub mod cache;
pub mod check;
pub mod cli;
pub mod error;
pub mod extract;
pub mod fetch;
pub mod model;
pub mod render;

use crate::cli::Command;
use crate::error::AppError;
use crate::model::CachedProfiles;

/// Execute one CLI command.
///
/// # Arguments
/// * `command` - Parsed command enum describing which deterministic workflow to execute.
///
/// # Returns
/// * `Ok(String)` when the command completed successfully, containing stdout text.
/// * `Err(AppError)` when command validation, I/O, or network operations fail.
///
/// # Examples
/// ```no_run
/// use pca::cli::{Command, ExtractArgs};
/// use pca::run;
///
/// let command = Command::Extract(ExtractArgs {
///     input: "compose.yaml".into(),
///     format: "text".into(),
/// });
/// let _ = run(command);
/// ```
pub fn run(command: Command) -> Result<String, AppError> {
    match command {
        Command::Extract(args) => {
            let content = fs::read_to_string(&args.input)
                .map_err(|error| AppError::io(&args.input, error.to_string()))?;
            let images = extract::extract_images(&content)?;
            match args.format.as_str() {
                "text" => Ok(images.join("\n")),
                "json" => serde_json::to_string_pretty(&images)
                    .map_err(|error| AppError::serialization(&args.input, error.to_string())),
                _ => Err(AppError::InvalidInput {
                    reason: format!("unsupported extract format: {}", args.format),
                }),
            }
        }
        Command::Refresh(args) => {
            let mut all_images = args.images;
            if let Some(path) = args.image_file {
                let file_content = fs::read_to_string(&path)
                    .map_err(|error| AppError::io(&path, error.to_string()))?;
                for line in file_content.lines() {
                    let trimmed = line.trim();
                    if !trimmed.is_empty() && !trimmed.starts_with('#') {
                        all_images.push(trimmed.to_string());
                    }
                }
            }

            if all_images.is_empty() {
                return Err(AppError::InvalidInput {
                    reason: "refresh requires --image or --image-file".to_string(),
                });
            }

            let normalized = extract::normalize_images(&all_images)?;
            let ordered: Vec<String> = normalized.into_iter().collect();
            let mut profiles = fetch::fetch_profiles(&ordered, args.allow_scrape_fallback)?;
            for (index, profile) in profiles.iter_mut().enumerate() {
                profile.id = format!("IMG-{}", index + 1);
            }

            fs::create_dir_all(&args.cache_dir)
                .map_err(|error| AppError::io(&args.cache_dir, error.to_string()))?;
            let cache_path = args.cache_dir.join("image-profiles.json");
            let payload = CachedProfiles {
                schema_version: 1,
                profiles,
            };
            cache::write_cache(&cache_path, &payload)?;
            Ok(format!(
                "wrote {} profiles to {}",
                payload.profiles.len(),
                cache_path.display()
            ))
        }
        Command::Render(args) => {
            let cache_path = args.cache_dir.join("image-profiles.json");
            let payload = cache::read_cache(&cache_path)?;
            match args.format.as_str() {
                "markdown" => Ok(render::render_markdown(&payload)),
                "json" => Ok(render::render_json(&payload)),
                _ => Err(AppError::InvalidInput {
                    reason: format!("unsupported render format: {}", args.format),
                }),
            }
        }
        Command::Check(args) => {
            let cache_path = args.cache_dir.join("image-profiles.json");
            let payload = cache::read_cache(&cache_path)?;
            let warnings = check::validate_cache(&payload, &args.strictness)?;
            if warnings.is_empty() {
                return Ok("ok: cache passed validation".to_string());
            }

            let mut output = String::from("validation warnings:\n");
            for warning in warnings {
                output.push_str("- ");
                output.push_str(&warning);
                output.push('\n');
            }
            Ok(output)
        }
    }
}
