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
    /// Generate deterministic anchorized compose output from hardened policy results.
    ComposeGenerate(ComposeGenerateArgs),
    /// Suggest reusable YAML anchors from hardened compose output.
    AnchorSuggest(AnchorSuggestArgs),
    /// Probe runtime tool availability for images and persist results in cache.
    Probe(ProbeArgs),
    /// Execute runtime verification and emit a machine-readable report.
    Verify(VerifyArgs),
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
    /// Probe image tool availability locally with `docker run`.
    #[arg(long, default_value_t = false)]
    pub probe_runtime_tools: bool,
    /// Tool names to probe when `--probe-runtime-tools` is enabled.
    #[arg(long = "probe-tool")]
    pub probe_tools: Vec<String>,
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
    /// Cache directory containing image-profiles.json.
    /// Required for compose policy evaluation and optional for dockerfile digest resolution.
    #[arg(long)]
    pub cache_dir: Option<PathBuf>,
    /// Deployment mode for compose policy heuristics (`compose` or `swarm`).
    #[arg(long, default_value = "compose")]
    pub mode: String,
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

/// Arguments for anchorized compose generation.
#[derive(Debug, Args)]
pub struct ComposeGenerateArgs {
    /// Input compose yaml file path.
    pub input: PathBuf,
    /// Policy pack yaml path.
    #[arg(long)]
    pub policy: PathBuf,
    /// Cache directory containing image-profiles.json.
    #[arg(long)]
    pub cache_dir: PathBuf,
    /// Output file path.
    #[arg(long)]
    pub output: PathBuf,
    /// Deploy mode for compose policy heuristics and defaults (`compose` or `swarm`).
    #[arg(long, default_value = "compose")]
    pub mode: String,
    /// Anchor emission mode (`auto`, `minimal`, `full`).
    #[arg(long, default_value = "auto")]
    pub anchors: String,
    /// Optional custom compose defaults file to extend/override built-in anchors.
    #[arg(long)]
    pub defaults_file: Option<PathBuf>,
}

/// Arguments for deterministic anchor suggestion reports.
#[derive(Debug, Args)]
pub struct AnchorSuggestArgs {
    /// Input compose yaml file path.
    pub input: PathBuf,
    /// Policy pack yaml path.
    #[arg(long)]
    pub policy: PathBuf,
    /// Cache directory containing image-profiles.json.
    #[arg(long)]
    pub cache_dir: PathBuf,
    /// Deploy mode for compose policy heuristics and defaults (`compose` or `swarm`).
    #[arg(long, default_value = "compose")]
    pub mode: String,
    /// Output format (`json` or `markdown`).
    #[arg(long, default_value = "json")]
    pub format: String,
    /// Optional minimum usage threshold override.
    #[arg(long)]
    pub min_usage: Option<usize>,
    /// Include sensitive/noisy key suggestions.
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    pub include_sensitive: bool,
    /// Maximum number of suggestions.
    #[arg(long, default_value_t = 50)]
    pub max_suggestions: usize,
    /// Optional output file path. When omitted, output is written to stdout.
    #[arg(long)]
    pub output: Option<PathBuf>,
}

/// Arguments for runtime tool probing.
#[derive(Debug, Args)]
pub struct ProbeArgs {
    /// Cache directory containing image-profiles.json.
    #[arg(long)]
    pub cache_dir: PathBuf,
    /// Tool names to probe in each image.
    #[arg(long = "tool")]
    pub tools: Vec<String>,
}

/// Arguments for runtime verification.
#[derive(Debug, Args)]
pub struct VerifyArgs {
    /// Input compose yaml path.
    pub input: PathBuf,
    /// Verification mode. Currently only `compose`.
    #[arg(long, default_value = "compose")]
    pub mode: String,
    /// Optional output file for machine-readable JSON report.
    #[arg(long)]
    pub output: Option<PathBuf>,
    /// Tear down resources after verification run.
    #[arg(long, default_value_t = true)]
    pub teardown: bool,
}
