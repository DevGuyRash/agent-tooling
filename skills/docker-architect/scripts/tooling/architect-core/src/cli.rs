//! CLI argument definitions.

use clap::{Args, Subcommand};
use std::path::PathBuf;

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
    /// Validate generated markdown against output contract requirements.
    OutputCheck(OutputCheckArgs),
    /// Evaluate policy rules and emit deterministic violations.
    PolicyCheck(PolicyEvalArgs),
    /// Generate deterministic patch plan from policy evaluation.
    PolicyPlan(PolicyEvalArgs),
    /// Apply a deterministic patch plan.
    PolicyApply(PolicyApplyArgs),
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

/// Arguments for output contract validation.
#[derive(Debug, Args)]
pub struct OutputCheckArgs {
    /// Input markdown file to validate.
    pub input: PathBuf,
    /// Output mode contract.
    #[arg(long, default_value = "compose")]
    pub mode: String,
}

/// Arguments for policy check/plan.
#[derive(Debug, Args)]
pub struct PolicyEvalArgs {
    /// Input compose yaml or Dockerfile path.
    pub input: PathBuf,
    /// Policy pack yaml path.
    #[arg(long)]
    pub policy: PathBuf,
    /// Cache directory containing image-profiles.json (required for compose policy evaluation).
    #[arg(long)]
    pub cache_dir: Option<PathBuf>,
}

/// Arguments for patch plan application.
#[derive(Debug, Args)]
pub struct PolicyApplyArgs {
    /// Input compose yaml file path.
    pub input: PathBuf,
    /// Patch plan json file path.
    #[arg(long)]
    pub plan: PathBuf,
    /// Output file path.
    #[arg(long)]
    pub output: PathBuf,
    /// Apply mode. Currently only `compose`.
    #[arg(long, default_value = "compose")]
    pub mode: String,
}
