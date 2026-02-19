//! Shared deterministic research toolkit for architecture skill outputs.
//!
//! # Overview
//! This crate provides deterministic extraction, metadata collection, cache management,
//! rendering, and validation primitives that are consumed by both `docker-architect-compose` and `docker-architect-image`.

use std::collections::BTreeMap;
use std::fs;

pub mod anchor_suggest;
pub mod cache;
pub mod check;
pub mod cli;
pub mod dockerfile;
pub mod error;
pub mod extract;
pub mod fetch;
pub mod generator;
pub mod heuristics;
pub mod knowledge;
pub mod model;
pub mod output_check;
pub mod policy;
pub mod probe;
pub mod render;
pub mod verify;

use crate::cli::Command;
use crate::error::AppError;
use crate::model::{CachedProfiles, ImageProfile, RuntimeToolDetail};

/// Runtime selector for CLI-specific behavior.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SkillVariant {
    /// Docker compose/swarm architecture assistant.
    Compose,
    /// Docker image architecture and supply-chain security assistant.
    Image,
}

impl SkillVariant {
    fn user_agent(self) -> &'static str {
        match self {
            SkillVariant::Compose => "agent-skills-docker-architect-compose/0.1",
            SkillVariant::Image => "agent-skills-docker-architect-image/0.1",
        }
    }
}

/// Execute one CLI command.
///
/// # Arguments
/// * `command` - Parsed command enum describing which deterministic workflow to execute.
/// * `variant` - Runtime selector for CLI-specific behavior such as user-agent text.
///
/// # Returns
/// * `Ok(String)` when the command completed successfully, containing stdout text.
/// * `Err(AppError)` when command validation, I/O, or network operations fail.
///
/// # Examples
/// ```no_run
/// use architect_core::cli::{Command, ExtractArgs};
/// use architect_core::{run, SkillVariant};
///
/// let command = Command::Extract(ExtractArgs {
///     input: "compose.yaml".into(),
///     format: "text".into(),
/// });
/// let _ = run(command, SkillVariant::Compose);
/// ```
pub fn run(command: Command, variant: SkillVariant) -> Result<String, AppError> {
    match command {
        Command::Extract(args) => {
            let content = fs::read_to_string(&args.input)
                .map_err(|error| AppError::io(&args.input, error.to_string()))?;
            let images = extract::extract_image_sets(&content)?;
            match args.format.as_str() {
                "text" => Ok(images.valid.join("\n")),
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

            let extracted = extract::classify_image_list(&all_images)?;
            let mut profiles = fetch::fetch_profiles(
                &extracted.valid,
                args.allow_scrape_fallback,
                variant.user_agent(),
            )?;
            if args.probe_runtime_tools {
                let tools = if args.probe_tools.is_empty() {
                    vec!["sh".to_string(), "curl".to_string(), "wget".to_string()]
                } else {
                    args.probe_tools
                };
                for profile in &mut profiles {
                    match probe::probe_runtime_tools(&profile.image, &tools) {
                        Ok(result) => {
                            apply_runtime_probe_results(profile, result);
                        }
                        Err(error) => {
                            note_runtime_probe_failure(profile, &error);
                        }
                    }
                }
            }
            for (index, profile) in profiles.iter_mut().enumerate() {
                profile.id = format!("IMG-{}", index + 1);
            }

            fs::create_dir_all(&args.cache_dir)
                .map_err(|error| AppError::io(&args.cache_dir, error.to_string()))?;
            let cache_path = args.cache_dir.join("image-profiles.json");
            let payload = CachedProfiles {
                schema_version: 3,
                profiles,
                unresolved_references: extracted.unresolved,
            };
            cache::write_cache(&cache_path, &payload)?;
            Ok(format!(
                "wrote {} profiles to {} (unresolved: {})",
                payload.profiles.len(),
                cache_path.display(),
                payload.unresolved_references.len()
            ))
        }
        Command::Render(args) => {
            let cache_path = args.cache_dir.join("image-profiles.json");
            let payload = cache::read_cache(&cache_path)?;
            match args.format.as_str() {
                "markdown" => Ok(render::render_markdown(&payload)),
                "json" => render::render_json(&payload)
                    .map_err(|error| AppError::serialization(&cache_path, error.to_string())),
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
        Command::OutputCheck(args) => {
            let content = fs::read_to_string(&args.input)
                .map_err(|error| AppError::io(&args.input, error.to_string()))?;
            let errors = output_check::validate_output_contract(&content, &args.mode)?;
            if errors.is_empty() {
                return Ok("ok: output contract passed".to_string());
            }

            let mut output = String::from("output contract violations:\n");
            for issue in errors {
                output.push_str("- ");
                output.push_str(&issue);
                output.push('\n');
            }
            Err(AppError::InvalidInput { reason: output })
        }
        Command::PolicyCheck(args) => match variant {
            SkillVariant::Compose => {
                let input_content = fs::read_to_string(&args.input)
                    .map_err(|error| AppError::io(&args.input, error.to_string()))?;
                let cache_dir = args
                    .cache_dir
                    .as_ref()
                    .ok_or_else(|| AppError::InvalidInput {
                        reason: "policy-check requires --cache-dir for compose workflow"
                            .to_string(),
                    })?;
                let cache_path = cache_dir.join("image-profiles.json");
                let cache = cache::read_cache(&cache_path)?;
                let policy_pack =
                    policy::load_policy_pack(&args.policy, policy::PolicyDomain::Compose)?;
                let mode = heuristics::DeployMode::parse(&args.mode)?;
                let evaluation = policy::evaluate_compose_policy_with_mode(
                    &input_content,
                    &cache,
                    &policy_pack,
                    mode,
                )?;
                let output = serde_json::json!({
                    "domain": evaluation.domain,
                    "mode": args.mode,
                    "strictness": evaluation.strictness,
                    "violations": evaluation.violations
                });
                serde_json::to_string_pretty(&output)
                    .map_err(|error| AppError::serialization(&args.input, error.to_string()))
            }
            SkillVariant::Image => {
                let input_content = fs::read_to_string(&args.input)
                    .map_err(|error| AppError::io(&args.input, error.to_string()))?;
                let cache_payload = if let Some(cache_dir) = args.cache_dir.as_ref() {
                    let cache_path = cache_dir.join("image-profiles.json");
                    Some(cache::read_cache(&cache_path)?)
                } else {
                    None
                };
                let policy_pack =
                    policy::load_policy_pack(&args.policy, policy::PolicyDomain::Dockerfile)?;
                let evaluation = policy::evaluate_dockerfile_policy_with_cache(
                    &input_content,
                    &policy_pack,
                    cache_payload.as_ref(),
                )?;
                let output = serde_json::json!({
                    "domain": evaluation.domain,
                    "strictness": evaluation.strictness,
                    "violations": evaluation.violations
                });
                serde_json::to_string_pretty(&output)
                    .map_err(|error| AppError::serialization(&args.input, error.to_string()))
            }
        },
        Command::PolicyPlan(args) => match variant {
            SkillVariant::Compose => {
                let input_content = fs::read_to_string(&args.input)
                    .map_err(|error| AppError::io(&args.input, error.to_string()))?;
                let cache_dir = args
                    .cache_dir
                    .as_ref()
                    .ok_or_else(|| AppError::InvalidInput {
                        reason: "policy-plan requires --cache-dir for compose workflow".to_string(),
                    })?;
                let cache_path = cache_dir.join("image-profiles.json");
                let cache = cache::read_cache(&cache_path)?;
                let policy_pack =
                    policy::load_policy_pack(&args.policy, policy::PolicyDomain::Compose)?;
                let mode = heuristics::DeployMode::parse(&args.mode)?;
                let evaluation = policy::evaluate_compose_policy_with_mode(
                    &input_content,
                    &cache,
                    &policy_pack,
                    mode,
                )?;
                serde_json::to_string_pretty(&evaluation.patch_plan)
                    .map_err(|error| AppError::serialization(&args.input, error.to_string()))
            }
            SkillVariant::Image => {
                let input_content = fs::read_to_string(&args.input)
                    .map_err(|error| AppError::io(&args.input, error.to_string()))?;
                let cache_payload = if let Some(cache_dir) = args.cache_dir.as_ref() {
                    let cache_path = cache_dir.join("image-profiles.json");
                    Some(cache::read_cache(&cache_path)?)
                } else {
                    None
                };
                let policy_pack =
                    policy::load_policy_pack(&args.policy, policy::PolicyDomain::Dockerfile)?;
                let evaluation = policy::evaluate_dockerfile_policy_with_cache(
                    &input_content,
                    &policy_pack,
                    cache_payload.as_ref(),
                )?;
                serde_json::to_string_pretty(&evaluation.patch_plan)
                    .map_err(|error| AppError::serialization(&args.input, error.to_string()))
            }
        },
        Command::PolicyApply(args) => {
            if args.mode != "compose" {
                return Err(AppError::InvalidInput {
                    reason: format!("unsupported policy-apply mode: {}", args.mode),
                });
            }

            let input_content = fs::read_to_string(&args.input)
                .map_err(|error| AppError::io(&args.input, error.to_string()))?;
            let patch_content = fs::read_to_string(&args.plan)
                .map_err(|error| AppError::io(&args.plan, error.to_string()))?;
            let patch_plan: Vec<policy::PatchOperation> = serde_json::from_str(&patch_content)
                .map_err(|error| {
                    AppError::serialization(&args.plan, format!("invalid patch plan json: {error}"))
                })?;
            let mode = heuristics::DeployMode::parse(&args.mode)?;
            let rendered = policy::apply_compose_patch_plan(&input_content, &patch_plan, mode)?;
            fs::write(&args.output, rendered)
                .map_err(|error| AppError::io(&args.output, error.to_string()))?;
            Ok(format!(
                "wrote patched compose output to {}",
                args.output.display()
            ))
        }
        Command::ComposeGenerate(args) => {
            if variant != SkillVariant::Compose {
                return Err(AppError::InvalidInput {
                    reason: "compose-generate is only supported in compose workflow".to_string(),
                });
            }
            let input_content = fs::read_to_string(&args.input)
                .map_err(|error| AppError::io(&args.input, error.to_string()))?;
            let cache_path = args.cache_dir.join("image-profiles.json");
            let cache = cache::read_cache(&cache_path)?;
            let policy_pack =
                policy::load_policy_pack(&args.policy, policy::PolicyDomain::Compose)?;
            let mode = heuristics::DeployMode::parse(&args.mode)?;
            let evaluation = policy::evaluate_compose_policy_with_mode(
                &input_content,
                &cache,
                &policy_pack,
                mode,
            )?;
            let hardened =
                policy::apply_compose_patch_plan(&input_content, &evaluation.patch_plan, mode)?;
            let anchor_mode = generator::AnchorMode::parse(&args.anchors)?;
            let rendered = generator::generate_anchored_compose(
                &hardened,
                mode,
                anchor_mode,
                args.defaults_file.as_deref(),
            )?;
            fs::write(&args.output, rendered)
                .map_err(|error| AppError::io(&args.output, error.to_string()))?;
            Ok(format!(
                "wrote anchorized compose output to {}",
                args.output.display()
            ))
        }
        Command::AnchorSuggest(args) => {
            if variant != SkillVariant::Compose {
                return Err(AppError::InvalidInput {
                    reason: "anchor-suggest is only supported in compose workflow".to_string(),
                });
            }
            let input_content = fs::read_to_string(&args.input)
                .map_err(|error| AppError::io(&args.input, error.to_string()))?;
            let cache_path = args.cache_dir.join("image-profiles.json");
            let cache = cache::read_cache(&cache_path)?;
            let policy_pack =
                policy::load_policy_pack(&args.policy, policy::PolicyDomain::Compose)?;
            let mode = heuristics::DeployMode::parse(&args.mode)?;
            let evaluation = policy::evaluate_compose_policy_with_mode(
                &input_content,
                &cache,
                &policy_pack,
                mode,
            )?;
            let hardened =
                policy::apply_compose_patch_plan(&input_content, &evaluation.patch_plan, mode)?;
            let report = anchor_suggest::suggest_anchors(
                &hardened,
                &anchor_suggest::SuggestionOptions {
                    mode,
                    min_usage_override: args.min_usage,
                    include_sensitive: args.include_sensitive,
                    max_suggestions: args.max_suggestions,
                },
            )?;
            let rendered = match args.format.as_str() {
                "json" => serde_json::to_string_pretty(&report)
                    .map_err(|error| AppError::serialization(&args.input, error.to_string()))?,
                "markdown" => anchor_suggest::render_markdown_report(&report)?,
                _ => {
                    return Err(AppError::InvalidInput {
                        reason: format!("unsupported anchor-suggest format: {}", args.format),
                    });
                }
            };
            if let Some(path) = args.output {
                fs::write(&path, &rendered)
                    .map_err(|error| AppError::io(&path, error.to_string()))?;
                Ok(format!(
                    "wrote anchor suggestion report to {}",
                    path.display()
                ))
            } else {
                Ok(rendered)
            }
        }
        Command::Probe(args) => {
            let cache_path = args.cache_dir.join("image-profiles.json");
            let mut payload = cache::read_cache(&cache_path)?;
            let tools = if args.tools.is_empty() {
                vec!["sh".to_string(), "curl".to_string(), "wget".to_string()]
            } else {
                args.tools
            };
            for profile in &mut payload.profiles {
                match probe::probe_runtime_tools(&profile.image, &tools) {
                    Ok(result) => {
                        apply_runtime_probe_results(profile, result);
                    }
                    Err(error) => {
                        note_runtime_probe_failure(profile, &error);
                    }
                }
            }
            cache::write_cache(&cache_path, &payload)?;
            Ok(format!(
                "updated runtime probe results for {} profiles in {}",
                payload.profiles.len(),
                cache_path.display()
            ))
        }
        Command::Verify(args) => {
            if args.mode != "compose" {
                return Err(AppError::InvalidInput {
                    reason: format!("unsupported verify mode: {}", args.mode),
                });
            }
            let report = verify::verify_compose(&args.input, args.teardown)?;
            let rendered = serde_json::to_string_pretty(&report)
                .map_err(|error| AppError::serialization(&args.input, error.to_string()))?;
            if let Some(path) = args.output {
                fs::write(&path, &rendered)
                    .map_err(|error| AppError::io(&path, error.to_string()))?;
                Ok(format!("wrote verify report to {}", path.display()))
            } else {
                Ok(rendered)
            }
        }
    }
}

fn apply_runtime_probe_results(
    profile: &mut ImageProfile,
    result: BTreeMap<String, RuntimeToolDetail>,
) {
    profile.runtime.tools = result
        .iter()
        .map(|(tool, detail)| (tool.clone(), detail.available))
        .collect();
    profile.runtime.tool_details = result;
    push_note_once(&mut profile.notes, "source:runtime-probe");

    if probe_detected_distroless_shell_missing(&profile.runtime.tool_details) {
        profile.runtime.signatures.distroless = true;
        push_note_once(
            &mut profile.notes,
            "runtime-signature:distroless-shell-missing",
        );
        push_note_once(
            &mut profile.notes,
            "advisory:distroless-avoid-cmd-shell-healthchecks-use-native-health-endpoint-or-dockerfile-healthcheck",
        );
    }
}

fn note_runtime_probe_failure(profile: &mut ImageProfile, error: &AppError) {
    push_note_once(&mut profile.notes, "runtime-probe-failed");
    let category = match error {
        AppError::Io { .. } => "io",
        AppError::InvalidInput { reason } => {
            if reason.to_ascii_lowercase().contains("timed out") {
                "timeout"
            } else {
                "invalid-input"
            }
        }
        AppError::Http { .. } => "http",
        AppError::Serialization { .. } => "serialization",
    };
    push_note_once(
        &mut profile.notes,
        &format!("runtime-probe-failed-reason:{category}"),
    );
}

fn probe_detected_distroless_shell_missing(details: &BTreeMap<String, RuntimeToolDetail>) -> bool {
    details.get("sh").is_some_and(|detail| {
        !detail.available && detail.strategy.as_deref() == Some("shell-missing-distroless-likely")
    })
}

fn push_note_once(notes: &mut Vec<String>, note: &str) {
    if !notes.iter().any(|item| item == note) {
        notes.push(note.to_string());
    }
}
