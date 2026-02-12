//! CLI argument definitions.

use clap::{Args, Parser, Subcommand};
use std::path::PathBuf;

/// Top-level CLI parser.
#[derive(Debug, Parser)]
#[command(
    name = "piascs",
    about = "Deterministic helper for image architecture skill"
)]
pub struct Cli {
    /// Command to execute.
    #[command(subcommand)]
    pub command: Command,
}

/// Supported deterministic command set.
#[derive(Debug, Subcommand)]
pub enum Command {
    /// Extract image references from input text or YAML content.
    Extract(ExtractArgs),
    /// Refresh local cache entries from APIs (and optional scraping fallback).
    Refresh(RefreshArgs),
    /// Render image research from cached JSON profiles.
    Render(RenderArgs),
    /// Validate cached entries against required fields and strictness rules.
    Check(CheckArgs),
}

/// Arguments for extraction.
#[derive(Debug, Args)]
pub struct ExtractArgs {
    /// Input file path containing source text.
    pub input: PathBuf,
    /// Output format: `text` or `json`.
    #[arg(long, default_value = "text")]
    pub format: String,
}

/// Arguments for refresh.
#[derive(Debug, Args)]
pub struct RefreshArgs {
    /// Images to refresh.
    #[arg(long = "image")]
    pub images: Vec<String>,
    /// Input file containing image references (one per line).
    #[arg(long)]
    pub image_file: Option<PathBuf>,
    /// Cache directory.
    #[arg(long)]
    pub cache_dir: PathBuf,
    /// Allow HTML scraping fallback after API failure.
    #[arg(long, default_value_t = false)]
    pub allow_scrape_fallback: bool,
}

/// Arguments for rendering.
#[derive(Debug, Args)]
pub struct RenderArgs {
    /// Cache directory to read profiles from.
    #[arg(long)]
    pub cache_dir: PathBuf,
    /// Output format: `markdown` or `json`.
    #[arg(long, default_value = "markdown")]
    pub format: String,
}

/// Arguments for validation.
#[derive(Debug, Args)]
pub struct CheckArgs {
    /// Cache directory to validate.
    #[arg(long)]
    pub cache_dir: PathBuf,
    /// Strictness level: advisory, balanced, enforcing.
    #[arg(long, default_value = "balanced")]
    pub strictness: String,
}
