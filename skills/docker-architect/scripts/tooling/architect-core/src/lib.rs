//! Shared deterministic research toolkit for architecture skill outputs.
//!
//! # Overview
//! This crate provides deterministic extraction, metadata collection, cache management,
//! rendering, and validation primitives that are consumed by both `docker-architect-compose` and `docker-architect-image`.

use std::collections::BTreeMap;
use std::fs;
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::{Path, PathBuf};

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

const MAX_POLICY_PLAN_BYTES: u64 = 1_048_576;
const MAX_IMAGE_LIST_BYTES: u64 = 1_048_576;
const MAX_GENERAL_TEXT_INPUT_BYTES: u64 = 8 * 1024 * 1024;

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
            let content = read_utf8_file_with_size_limit(
                &args.input,
                MAX_GENERAL_TEXT_INPUT_BYTES,
                "extract input file",
            )?;
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
                let file_content =
                    read_utf8_file_with_size_limit(&path, MAX_IMAGE_LIST_BYTES, "image list file")?;
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
                schema_version: cache::CURRENT_CACHE_SCHEMA_VERSION,
                profiles,
                unresolved_references: extracted.unresolved,
            };
            cache::with_cache_lock(&cache_path, || cache::write_cache(&cache_path, &payload))?;
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
            let content = read_utf8_file_with_size_limit(
                &args.input,
                MAX_GENERAL_TEXT_INPUT_BYTES,
                "output-check input file",
            )?;
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
                let input_content = read_utf8_file_with_size_limit(
                    &args.input,
                    MAX_GENERAL_TEXT_INPUT_BYTES,
                    "policy-check input file",
                )?;
                let cache_dir = args
                    .cache_dir
                    .as_ref()
                    .ok_or_else(|| AppError::InvalidInput {
                        reason: "policy-check requires --cache-dir for compose workflow"
                            .to_string(),
                    })?;
                let cache_path = cache_dir.join("image-profiles.json");
                let cache = cache::read_cache(&cache_path)?;
                let policy_pack = policy::load_policy_pack_with_limit(
                    &args.policy,
                    policy::PolicyDomain::Compose,
                    policy::MAX_POLICY_PACK_BYTES,
                )?;
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
                    "violations": evaluation.violations,
                    "has_blocked_violations": evaluation.has_blocked_violations()
                });
                serde_json::to_string_pretty(&output)
                    .map_err(|error| AppError::serialization(&args.input, error.to_string()))
            }
            SkillVariant::Image => {
                let input_source_path =
                    canonicalize_existing_path(&args.input, "policy-check input file path")?;
                let input_content = read_utf8_file_with_size_limit(
                    input_source_path.as_path(),
                    MAX_GENERAL_TEXT_INPUT_BYTES,
                    "policy-check input file",
                )?;
                let cache_payload = if let Some(cache_dir) = args.cache_dir.as_ref() {
                    let cache_path = cache_dir.join("image-profiles.json");
                    Some(cache::read_cache(&cache_path)?)
                } else {
                    None
                };
                let policy_pack = policy::load_policy_pack_with_limit(
                    &args.policy,
                    policy::PolicyDomain::Dockerfile,
                    policy::MAX_POLICY_PACK_BYTES,
                )?;
                let evaluation = policy::evaluate_dockerfile_policy_with_cache_and_source(
                    &input_content,
                    &policy_pack,
                    cache_payload.as_ref(),
                    Some(input_source_path.as_path()),
                )?;
                let output = serde_json::json!({
                    "domain": evaluation.domain,
                    "strictness": evaluation.strictness,
                    "violations": evaluation.violations,
                    "has_blocked_violations": evaluation.has_blocked_violations()
                });
                serde_json::to_string_pretty(&output)
                    .map_err(|error| AppError::serialization(&args.input, error.to_string()))
            }
        },
        Command::PolicyPlan(args) => match variant {
            SkillVariant::Compose => {
                let input_content = read_utf8_file_with_size_limit(
                    &args.input,
                    MAX_GENERAL_TEXT_INPUT_BYTES,
                    "policy-plan input file",
                )?;
                let cache_dir = args
                    .cache_dir
                    .as_ref()
                    .ok_or_else(|| AppError::InvalidInput {
                        reason: "policy-plan requires --cache-dir for compose workflow".to_string(),
                    })?;
                let cache_path = cache_dir.join("image-profiles.json");
                let cache = cache::read_cache(&cache_path)?;
                let policy_pack = policy::load_policy_pack_with_limit(
                    &args.policy,
                    policy::PolicyDomain::Compose,
                    policy::MAX_POLICY_PACK_BYTES,
                )?;
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
                let input_source_path =
                    canonicalize_existing_path(&args.input, "policy-plan input file path")?;
                let input_content = read_utf8_file_with_size_limit(
                    input_source_path.as_path(),
                    MAX_GENERAL_TEXT_INPUT_BYTES,
                    "policy-plan input file",
                )?;
                let cache_payload = if let Some(cache_dir) = args.cache_dir.as_ref() {
                    let cache_path = cache_dir.join("image-profiles.json");
                    Some(cache::read_cache(&cache_path)?)
                } else {
                    None
                };
                let policy_pack = policy::load_policy_pack_with_limit(
                    &args.policy,
                    policy::PolicyDomain::Dockerfile,
                    policy::MAX_POLICY_PACK_BYTES,
                )?;
                let evaluation = policy::evaluate_dockerfile_policy_with_cache_and_source(
                    &input_content,
                    &policy_pack,
                    cache_payload.as_ref(),
                    Some(input_source_path.as_path()),
                )?;
                serde_json::to_string_pretty(&evaluation.patch_plan)
                    .map_err(|error| AppError::serialization(&args.input, error.to_string()))
            }
        },
        Command::PolicyApply(args) => match args.mode.as_str() {
            "compose" => {
                let input_content = read_utf8_file_with_size_limit(
                    &args.input,
                    MAX_GENERAL_TEXT_INPUT_BYTES,
                    "policy-apply input file",
                )?;
                let patch_plan = read_patch_plan_with_size_limit(&args.plan)?;
                let mode = heuristics::DeployMode::parse(&args.mode)?;
                let rendered = policy::apply_compose_patch_plan(&input_content, &patch_plan, mode)?;
                fs::write(&args.output, rendered)
                    .map_err(|error| AppError::io(&args.output, error.to_string()))?;
                Ok(format!(
                    "wrote patched compose output to {}",
                    args.output.display()
                ))
            }
            "dockerfile" => {
                if variant != SkillVariant::Image {
                    return Err(AppError::InvalidInput {
                        reason: "policy-apply mode dockerfile is only supported in image workflow"
                            .to_string(),
                    });
                }
                let input_content = read_utf8_file_with_size_limit(
                    &args.input,
                    MAX_GENERAL_TEXT_INPUT_BYTES,
                    "policy-apply input file",
                )?;
                let patch_plan = read_patch_plan_with_size_limit(&args.plan)?;
                let rendered = policy::apply_dockerfile_patch_plan(&input_content, &patch_plan)?;
                fs::write(&args.output, rendered)
                    .map_err(|error| AppError::io(&args.output, error.to_string()))?;
                Ok(format!(
                    "wrote patched dockerfile output to {}",
                    args.output.display()
                ))
            }
            _ => Err(AppError::InvalidInput {
                reason: format!("unsupported policy-apply mode: {}", args.mode),
            }),
        },
        Command::ComposeGenerate(args) => {
            if variant != SkillVariant::Compose {
                return Err(AppError::InvalidInput {
                    reason: "compose-generate is only supported in compose workflow".to_string(),
                });
            }
            let input_content = read_utf8_file_with_size_limit(
                &args.input,
                MAX_GENERAL_TEXT_INPUT_BYTES,
                "compose-generate input file",
            )?;
            let cache_path = args.cache_dir.join("image-profiles.json");
            let cache = cache::read_cache(&cache_path)?;
            let policy_pack = policy::load_policy_pack_with_limit(
                &args.policy,
                policy::PolicyDomain::Compose,
                policy::MAX_POLICY_PACK_BYTES,
            )?;
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
            let input_content = read_utf8_file_with_size_limit(
                &args.input,
                MAX_GENERAL_TEXT_INPUT_BYTES,
                "anchor-suggest input file",
            )?;
            let cache_path = args.cache_dir.join("image-profiles.json");
            let cache = cache::read_cache(&cache_path)?;
            let policy_pack = policy::load_policy_pack_with_limit(
                &args.policy,
                policy::PolicyDomain::Compose,
                policy::MAX_POLICY_PACK_BYTES,
            )?;
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
            let tools = if args.tools.is_empty() {
                vec!["sh".to_string(), "curl".to_string(), "wget".to_string()]
            } else {
                args.tools
            };
            let payload = cache::with_cache_lock(&cache_path, || cache::read_cache(&cache_path))?;
            let outcomes = collect_probe_outcomes(&payload.profiles, &tools);

            let profiles_updated = cache::with_cache_lock(&cache_path, || {
                let mut payload = cache::read_cache(&cache_path)?;
                let mut profiles_updated = 0usize;
                for profile in &mut payload.profiles {
                    let Some(outcome) = outcomes.get(&profile.image) else {
                        continue;
                    };
                    profiles_updated += 1;
                    match outcome {
                        ProbeOutcome::Success(result) => {
                            apply_runtime_probe_results(profile, result.clone());
                        }
                        ProbeOutcome::Failure { category } => {
                            note_runtime_probe_failure_category(profile, category);
                        }
                    }
                }
                cache::write_cache(&cache_path, &payload)?;
                Ok(profiles_updated)
            })?;
            Ok(format!(
                "updated runtime probe results for {} profiles in {}",
                profiles_updated,
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

/// Parse policy-check output and return whether blocked violations were reported.
///
/// # Arguments
/// * `output` - JSON output emitted by `Command::PolicyCheck`.
///
/// # Returns
/// * `Ok(true)` if `has_blocked_violations` is present and set to `true`.
/// * `Ok(false)` if `has_blocked_violations` is present and set to `false`.
/// * `Err(AppError)` if the output is not valid JSON or missing the required boolean field.
pub fn output_has_blocked_violations(output: &str) -> Result<bool, AppError> {
    let parsed: serde_json::Value =
        serde_json::from_str(output).map_err(|error| AppError::InvalidInput {
            reason: format!("policy-check output must be valid json: {error}"),
        })?;
    parsed
        .get("has_blocked_violations")
        .and_then(serde_json::Value::as_bool)
        .ok_or_else(|| AppError::InvalidInput {
            reason: "policy-check output missing boolean has_blocked_violations".to_string(),
        })
}

pub(crate) fn read_utf8_file_with_size_limit(
    path: &Path,
    max_bytes: u64,
    input_label: &str,
) -> Result<String, AppError> {
    let file = File::open(path).map_err(|error| AppError::io(path, error.to_string()))?;
    let metadata = file
        .metadata()
        .map_err(|error| AppError::io(path, error.to_string()))?;
    if metadata.len() > max_bytes {
        return Err(AppError::InvalidInput {
            reason: format!(
                "{input_label} exceeds max size of {max_bytes} bytes: {} bytes",
                metadata.len()
            ),
        });
    }

    let mut reader = BufReader::new(file).take(max_bytes.saturating_add(1));
    let mut content = String::new();
    reader
        .read_to_string(&mut content)
        .map_err(|error| AppError::io(path, error.to_string()))?;
    if content.len() as u64 > max_bytes {
        return Err(AppError::InvalidInput {
            reason: format!("{input_label} exceeds max size of {max_bytes} bytes"),
        });
    }

    Ok(content)
}

fn canonicalize_existing_path(path: &Path, input_label: &str) -> Result<PathBuf, AppError> {
    fs::canonicalize(path).map_err(|error| AppError::InvalidInput {
        reason: format!(
            "{input_label} must resolve to an existing canonical path: {} ({error})",
            path.display()
        ),
    })
}

fn read_patch_plan_with_size_limit(
    plan_path: &Path,
) -> Result<Vec<policy::PatchOperation>, AppError> {
    let patch_content =
        read_utf8_file_with_size_limit(plan_path, MAX_POLICY_PLAN_BYTES, "policy plan file")?;
    serde_json::from_str(&patch_content).map_err(|error| {
        AppError::serialization(plan_path, format!("invalid patch plan json: {error}"))
    })
}

#[derive(Debug, Clone)]
enum ProbeOutcome {
    Success(BTreeMap<String, RuntimeToolDetail>),
    Failure { category: String },
}

fn collect_probe_outcomes(
    profiles: &[ImageProfile],
    tools: &[String],
) -> BTreeMap<String, ProbeOutcome> {
    let mut outcomes = BTreeMap::new();
    for profile in profiles {
        let outcome = match probe::probe_runtime_tools(&profile.image, tools) {
            Ok(result) => ProbeOutcome::Success(result),
            Err(error) => ProbeOutcome::Failure {
                category: runtime_probe_failure_category(&error).to_string(),
            },
        };
        outcomes.insert(profile.image.clone(), outcome);
    }
    outcomes
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
    note_runtime_probe_failure_category(profile, runtime_probe_failure_category(error));
}

fn note_runtime_probe_failure_category(profile: &mut ImageProfile, category: &str) {
    push_note_once(&mut profile.notes, "runtime-probe-failed");
    push_note_once(
        &mut profile.notes,
        &format!("runtime-probe-failed-reason:{category}"),
    );
}

fn runtime_probe_failure_category(error: &AppError) -> &'static str {
    match error {
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
    }
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

#[cfg(test)]
mod tests {
    use std::fs::File;

    use tempfile::tempdir;

    use super::{
        output_has_blocked_violations, read_patch_plan_with_size_limit,
        read_utf8_file_with_size_limit,
    };
    use crate::error::AppError;

    #[test]
    fn read_utf8_file_with_size_limit_accepts_small_file() {
        let temp = tempdir().expect("tempdir should be created");
        let input_path = temp.path().join("input.txt");
        std::fs::write(&input_path, "services:\n  web:\n    image: nginx:1.27\n")
            .expect("input should be written");

        let content = read_utf8_file_with_size_limit(&input_path, 1024, "test input")
            .expect("small file should be accepted");
        assert!(content.contains("services:"));
    }

    #[test]
    fn read_utf8_file_with_size_limit_rejects_oversized_file() {
        let temp = tempdir().expect("tempdir should be created");
        let input_path = temp.path().join("input.txt");
        let file = File::create(&input_path).expect("file should be created");
        file.set_len(17).expect("file should be sized");

        let result = read_utf8_file_with_size_limit(&input_path, 16, "test input");
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn read_patch_plan_with_size_limit_accepts_small_valid_json() {
        let temp = tempdir().expect("tempdir should be created");
        let plan_path = temp.path().join("patch-plan.json");
        std::fs::write(
            &plan_path,
            r#"[{"op":"set","path":"services.web.read_only","value":true,"rule_id":"AC-CMP-READONLY"}]"#,
        )
        .expect("patch plan should be written");

        let patch_plan = read_patch_plan_with_size_limit(&plan_path).expect("plan should parse");
        assert_eq!(patch_plan.len(), 1);
    }

    #[test]
    fn read_patch_plan_with_size_limit_rejects_oversized_file() {
        let temp = tempdir().expect("tempdir should be created");
        let plan_path = temp.path().join("patch-plan.json");
        let file = File::create(&plan_path).expect("file should be created");
        file.set_len(1_048_577).expect("file should be sized");

        let result = read_patch_plan_with_size_limit(&plan_path);
        assert!(result.is_err());
    }

    #[test]
    fn output_has_blocked_violations_reads_true_flag() {
        let output = r#"{"has_blocked_violations":true}"#;
        let has_blocked = output_has_blocked_violations(output).expect("valid output should parse");
        assert!(has_blocked);
    }

    #[test]
    fn output_has_blocked_violations_reads_false_flag() {
        let output = r#"{"has_blocked_violations":false}"#;
        let has_blocked = output_has_blocked_violations(output).expect("valid output should parse");
        assert!(!has_blocked);
    }

    #[test]
    fn output_has_blocked_violations_errors_when_json_is_invalid() {
        let result = output_has_blocked_violations("not-json");
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn output_has_blocked_violations_errors_when_key_is_missing() {
        let result = output_has_blocked_violations(r#"{"violations":[]}"#);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }
}
