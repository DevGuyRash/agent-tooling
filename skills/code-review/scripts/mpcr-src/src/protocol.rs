//! Structured `mpcr protocol ...` retrieval and compatibility dispatch helpers.
#![allow(missing_docs)]

use crate::artifacts::{
    parse_artifact_file, ArtifactDocument, ExecutionArchitecture, Mode, ModuleId, PolicyCategory,
    PolicyRef, PolicyView, SurfaceId, POLICY_BUNDLE_VERSION,
};
use crate::paths;
use crate::policy_store::{
    generate_applicator_fallback, generate_fullcycle_fallback, generate_orchestrator_fallback,
    generate_reviewer_fallback, PolicyListEntry, PolicyStore,
};
use crate::session::{
    load_session, AgentRoleKind, LanguageResearchRef, ReviewProcess, SessionLocator,
};
use serde::Serialize;
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Text protocol response for one static policy lookup.
pub struct ProtocolOutput {
    pub category: PolicyCategory,
    pub id: String,
    pub view: PolicyView,
    pub content: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Structured compatibility dispatch response.
pub struct DispatchOutput {
    pub role: String,
    pub view: PolicyView,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reviewer_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_ref: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mode: Option<Mode>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub execution_architecture: Option<ExecutionArchitecture>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub agent_dir: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub report_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub role_kind: Option<String>,
    #[serde(default)]
    pub module_ids: Vec<String>,
    #[serde(default)]
    pub focus_surfaces: Vec<String>,
    #[serde(default)]
    pub claimed_scope: Vec<String>,
    #[serde(default)]
    pub delegated_scope: Vec<String>,
    #[serde(default)]
    pub lineage: Vec<String>,
    #[serde(default)]
    pub language_research_refs: Vec<LanguageResearchRef>,
    #[serde(default)]
    pub loaded_policy_refs: Vec<PolicyRef>,
    #[serde(default)]
    pub warnings: Vec<String>,
    pub content: String,
}

#[derive(Debug, Clone)]
struct ResolvedRole {
    role: String,
    mode: Mode,
    worker_policy_id: String,
    module_ids: Vec<String>,
}

#[derive(Debug, Clone)]
struct RouteContext {
    mode: Mode,
    execution_architecture: ExecutionArchitecture,
    selected_modules: Vec<String>,
    surfaces: Vec<String>,
}

#[derive(Debug, Clone)]
struct DispatchContext {
    role: ResolvedRole,
    reviewer_id: Option<String>,
    session_id: Option<String>,
    target_ref: Option<String>,
    route: Option<RouteContext>,
    agent_dir: Option<String>,
    report_path: Option<String>,
    role_kind: Option<String>,
    focus_surfaces: Vec<String>,
    claimed_scope: Vec<String>,
    delegated_scope: Vec<String>,
    lineage: Vec<String>,
    language_research_refs: Vec<LanguageResearchRef>,
    loaded_policy_refs: Vec<PolicyRef>,
    warnings: Vec<String>,
}

fn module_slug(module_id: ModuleId) -> String {
    toml::Value::try_from(module_id).map_or_else(
        |_| "unknown".to_string(),
        |value| value.to_string().trim_matches('"').to_string(),
    )
}

fn surface_slug(surface_id: SurfaceId) -> String {
    toml::Value::try_from(surface_id).map_or_else(
        |_| "unknown".to_string(),
        |value| value.to_string().trim_matches('"').to_string(),
    )
}

fn mode_slug(mode: Mode) -> String {
    toml::Value::try_from(mode).map_or_else(
        |_| "reviewer".to_string(),
        |value| value.to_string().trim_matches('"').to_string(),
    )
}

fn role_kind_slug(role_kind: &AgentRoleKind) -> String {
    match role_kind {
        AgentRoleKind::DomainReviewer => "domain-reviewer",
        AgentRoleKind::LanguageDetector => "language-detector",
        AgentRoleKind::LanguageResearch => "language-research",
        AgentRoleKind::FinalSynthesis => "final-synthesis",
        AgentRoleKind::ApplyComposite => "apply-composite",
        AgentRoleKind::ApplicatorWorker => "applicator-worker",
        AgentRoleKind::ApplicatorVerifier => "applicator-verifier",
        AgentRoleKind::Helper => "helper",
    }
    .to_string()
}

fn policy_ref(category: PolicyCategory, id: impl Into<String>, view: PolicyView) -> PolicyRef {
    PolicyRef {
        category,
        id: id.into(),
        version: POLICY_BUNDLE_VERSION.to_string(),
        view,
    }
}

fn push_section(lines: &mut Vec<String>, title: &str, items: &[String], empty: &str) {
    lines.push(format!("## {title}"));
    lines.push(String::new());
    if items.is_empty() {
        lines.push(format!("- {empty}"));
    } else {
        for item in items {
            lines.push(format!("- {item}"));
        }
    }
    lines.push(String::new());
}

fn normalize_dispatch_role(role: &str) -> anyhow::Result<ResolvedRole> {
    let trimmed = role.trim();
    anyhow::ensure!(
        !trimmed.is_empty(),
        "error: dispatch role must not be empty"
    );

    if let Some(module) = trimmed.strip_prefix("domain:") {
        anyhow::ensure!(
            ModuleId::all()
                .into_iter()
                .any(|candidate| module_slug(candidate) == module),
            "error: unknown dispatch role `{trimmed}`"
        );
        return Ok(ResolvedRole {
            role: trimmed.to_string(),
            mode: Mode::Reviewer,
            worker_policy_id: "domain-reviewer".to_string(),
            module_ids: vec![module.to_string()],
        });
    }

    if ModuleId::all()
        .into_iter()
        .any(|candidate| module_slug(candidate) == trimmed)
    {
        return Ok(ResolvedRole {
            role: format!("domain:{trimmed}"),
            mode: Mode::Reviewer,
            worker_policy_id: "domain-reviewer".to_string(),
            module_ids: vec![trimmed.to_string()],
        });
    }

    if trimmed == "domain-reviewer" {
        return Ok(ResolvedRole {
            role: trimmed.to_string(),
            mode: Mode::Reviewer,
            worker_policy_id: "domain-reviewer".to_string(),
            module_ids: Vec::new(),
        });
    }

    if trimmed == "language-detector" || trimmed.starts_with("language-detector:") {
        return Ok(ResolvedRole {
            role: "language-detector".to_string(),
            mode: Mode::Reviewer,
            worker_policy_id: "language-detector".to_string(),
            module_ids: Vec::new(),
        });
    }

    if trimmed.starts_with("language-research:") {
        return Ok(ResolvedRole {
            role: trimmed.to_string(),
            mode: Mode::Reviewer,
            worker_policy_id: "language-research".to_string(),
            module_ids: Vec::new(),
        });
    }

    if trimmed == "final-synthesis" || trimmed == "final-synthesizer" {
        return Ok(ResolvedRole {
            role: "final-synthesis".to_string(),
            mode: Mode::Reviewer,
            worker_policy_id: "final-synthesizer".to_string(),
            module_ids: vec![module_slug(ModuleId::ShipReadiness)],
        });
    }

    if trimmed == "apply-composite" {
        return Ok(ResolvedRole {
            role: trimmed.to_string(),
            mode: Mode::Applicator,
            worker_policy_id: trimmed.to_string(),
            module_ids: Vec::new(),
        });
    }

    if trimmed == "applicator-worker" {
        return Ok(ResolvedRole {
            role: trimmed.to_string(),
            mode: Mode::Applicator,
            worker_policy_id: trimmed.to_string(),
            module_ids: Vec::new(),
        });
    }

    if trimmed == "applicator-verifier" {
        return Ok(ResolvedRole {
            role: trimmed.to_string(),
            mode: Mode::Applicator,
            worker_policy_id: trimmed.to_string(),
            module_ids: Vec::new(),
        });
    }

    let store = PolicyStore::load()?;
    if store.get(PolicyCategory::Worker, trimmed).is_ok() {
        return Ok(ResolvedRole {
            role: trimmed.to_string(),
            mode: Mode::Reviewer,
            worker_policy_id: trimmed.to_string(),
            module_ids: Vec::new(),
        });
    }

    Err(anyhow::anyhow!("error: unknown dispatch role `{trimmed}`"))
}

fn role_matches_request(review: &ReviewProcess, resolved: &ResolvedRole) -> bool {
    review.role == resolved.role
        || (resolved.worker_policy_id == "domain-reviewer"
            && review
                .module_ids
                .iter()
                .any(|module_id| resolved.module_ids.contains(&module_slug(*module_id))))
        || (resolved.worker_policy_id == "language-detector"
            && review.role.starts_with("language-detector"))
        || (resolved.worker_policy_id == "language-research"
            && review.role.starts_with("language-research:"))
        || (resolved.worker_policy_id == "final-synthesizer" && review.role == "final-synthesis")
}

fn route_context_for(locator: &SessionLocator) -> anyhow::Result<Option<RouteContext>> {
    let session = load_session(locator)?;
    let Some(pointer) = &session.current.route_decision else {
        return Ok(None);
    };
    let route_path = if let Some(path) = pointer
        .json_path
        .as_deref()
        .or(pointer.toml_path.as_deref())
        .or(Some(pointer.path.as_str()))
    {
        paths::resolve_repo_relative(Path::new(&session.repo_root), path)?
    } else {
        return Ok(None);
    };
    let route = match parse_artifact_file(&route_path)? {
        ArtifactDocument::RouteDecision(route) => route,
        _ => return Ok(None),
    };
    Ok(Some(RouteContext {
        mode: route.mode,
        execution_architecture: route.execution_architecture,
        selected_modules: route
            .selected_modules
            .iter()
            .map(|module_id| module_slug(*module_id))
            .collect(),
        surfaces: route
            .risk_surfaces
            .iter()
            .map(|surface| surface_slug(surface.surface_id))
            .collect(),
    }))
}

fn dispatch_context(
    resolved: ResolvedRole,
    locator: Option<&SessionLocator>,
    reviewer_id: Option<&str>,
    view: PolicyView,
) -> anyhow::Result<DispatchContext> {
    let mut ctx = DispatchContext {
        role: resolved,
        reviewer_id: None,
        session_id: None,
        target_ref: None,
        route: None,
        agent_dir: None,
        report_path: None,
        role_kind: None,
        focus_surfaces: Vec::new(),
        claimed_scope: Vec::new(),
        delegated_scope: Vec::new(),
        lineage: Vec::new(),
        language_research_refs: Vec::new(),
        loaded_policy_refs: Vec::new(),
        warnings: Vec::new(),
    };

    let Some(locator) = locator else {
        anyhow::ensure!(
            reviewer_id.is_none(),
            "error: protocol dispatch with --reviewer-id also requires a session locator"
        );
        ctx.warnings.push(
            "dispatch loaded without session context; agent paths, lineage, and routed scope were not resolved"
                .to_string(),
        );
        ctx.loaded_policy_refs.push(policy_ref(
            PolicyCategory::Mode,
            mode_slug(ctx.role.mode),
            view,
        ));
        ctx.loaded_policy_refs.push(policy_ref(
            PolicyCategory::Worker,
            ctx.role.worker_policy_id.clone(),
            view,
        ));
        for module_id in &ctx.role.module_ids {
            ctx.loaded_policy_refs.push(policy_ref(
                PolicyCategory::Module,
                module_id.clone(),
                view,
            ));
        }
        return Ok(ctx);
    };

    let session = load_session(locator)?;
    ctx.session_id = Some(session.session_id.clone());
    ctx.target_ref = Some(session.target_ref.clone());
    ctx.route = route_context_for(locator)?;
    if let Some(route) = &ctx.route {
        if ctx.role.mode != Mode::Applicator {
            ctx.role.mode = route.mode;
        }
    }

    let review = if let Some(reviewer_id) = reviewer_id {
        Some(
            session
                .reviews
                .iter()
                .find(|review| review.reviewer_id == reviewer_id)
                .ok_or_else(|| anyhow::anyhow!("error: reviewer `{reviewer_id}` was not found"))?,
        )
    } else {
        let matches = session
            .reviews
            .iter()
            .filter(|review| role_matches_request(review, &ctx.role))
            .collect::<Vec<_>>();
        match matches.as_slice() {
            [] => None,
            [review] => Some(*review),
            _ => {
                ctx.warnings.push(format!(
                    "multiple reviewers matched role `{}`; rerun with --reviewer-id to bind the dispatch to one agent directory",
                    ctx.role.role
                ));
                None
            }
        }
    };

    if let Some(review) = review {
        if !role_matches_request(review, &ctx.role) {
            return Err(anyhow::anyhow!(
                "error: reviewer `{}` does not match dispatch role `{}`",
                review.reviewer_id,
                ctx.role.role
            ));
        }
        ctx.reviewer_id = Some(review.reviewer_id.clone());
        ctx.role.role = review.role.clone();
        ctx.role.module_ids = if review.module_ids.is_empty() {
            ctx.role.module_ids.clone()
        } else {
            review
                .module_ids
                .iter()
                .map(|module_id| module_slug(*module_id))
                .collect()
        };
        ctx.agent_dir = Some(review.agent_dir.clone());
        ctx.report_path = review.report_path.clone();
        ctx.role_kind = Some(role_kind_slug(&review.role_kind));
        ctx.focus_surfaces = review
            .focus_surfaces
            .iter()
            .map(|surface| surface_slug(*surface))
            .collect();
        ctx.claimed_scope = review.claimed_scope.clone();
        ctx.delegated_scope = review.delegated_scope.clone();
        ctx.lineage = review.lineage.clone();
        ctx.language_research_refs = review.research_refs.clone();
    } else {
        ctx.language_research_refs = session.language_research_refs.clone();
    }

    if ctx.role.module_ids.is_empty() {
        if let Some(route) = &ctx.route {
            ctx.role.module_ids = route.selected_modules.clone();
        }
    }

    ctx.loaded_policy_refs
        .retain(|policy| policy.category != PolicyCategory::Module);
    for module_id in &ctx.role.module_ids {
        ctx.loaded_policy_refs
            .push(policy_ref(PolicyCategory::Module, module_id.clone(), view));
    }

    if ctx.focus_surfaces.is_empty() {
        if let Some(route) = &ctx.route {
            ctx.focus_surfaces = route.surfaces.clone();
        }
    }

    ctx.loaded_policy_refs.push(policy_ref(
        PolicyCategory::Mode,
        mode_slug(ctx.role.mode),
        view,
    ));
    ctx.loaded_policy_refs.push(policy_ref(
        PolicyCategory::Worker,
        ctx.role.worker_policy_id.clone(),
        view,
    ));
    for module_id in &ctx.role.module_ids {
        ctx.loaded_policy_refs
            .push(policy_ref(PolicyCategory::Module, module_id.clone(), view));
    }

    Ok(ctx)
}

fn render_dispatch_content(ctx: &DispatchContext, store: &PolicyStore) -> anyhow::Result<String> {
    let mut lines = Vec::new();
    lines.push(format!("# Dispatch {}", ctx.role.role));
    lines.push(String::new());
    lines.push("You SHALL keep the orchestrator thin and execute only the slice assigned in this dispatch.".to_string());
    lines.push("You SHALL treat machine artifacts as canonical and authored markdown as the required explanatory companion.".to_string());
    lines.push("You SHALL write your full markdown report to the agent directory resolved below before you finalize machine artifacts.".to_string());
    lines.push("You SHALL NOT re-read the entire skill body after receiving this dispatch unless the dispatch itself is missing a required contract.".to_string());
    lines.push(String::new());

    let mut summary_items = vec![format!("role `{}`", ctx.role.role)];
    summary_items.push(format!("mode `{}`", mode_slug(ctx.role.mode)));
    if let Some(architecture) = ctx.route.as_ref().map(|route| route.execution_architecture) {
        summary_items.push(format!(
            "execution architecture `{}`",
            toml::Value::try_from(architecture).map_or_else(
                |_| "unknown".to_string(),
                |value| value.to_string().trim_matches('"').to_string(),
            )
        ));
    }
    if let Some(session_id) = &ctx.session_id {
        summary_items.push(format!("session `{session_id}`"));
    }
    if let Some(target_ref) = &ctx.target_ref {
        summary_items.push(format!("target ref `{target_ref}`"));
    }
    if let Some(reviewer_id) = &ctx.reviewer_id {
        summary_items.push(format!("reviewer `{reviewer_id}`"));
    }
    if let Some(role_kind) = &ctx.role_kind {
        summary_items.push(format!("role kind `{role_kind}`"));
    }
    if let Some(agent_dir) = &ctx.agent_dir {
        summary_items.push(format!("agent dir `{agent_dir}`"));
    }
    if let Some(report_path) = &ctx.report_path {
        summary_items.push(format!("report path `{report_path}`"));
    }
    push_section(
        &mut lines,
        "Assignment",
        &summary_items,
        "assignment context unavailable",
    );

    push_section(
        &mut lines,
        "Scope",
        &ctx.role
            .module_ids
            .iter()
            .map(|module_id| format!("own module `{module_id}`"))
            .chain(
                ctx.focus_surfaces
                    .iter()
                    .map(|surface| format!("focus surface `{surface}`")),
            )
            .chain(
                ctx.claimed_scope
                    .iter()
                    .map(|scope| format!("claimed scope `{scope}`")),
            )
            .chain(
                ctx.delegated_scope
                    .iter()
                    .map(|scope| format!("delegated scope `{scope}`")),
            )
            .collect::<Vec<_>>(),
        "scope was not session-bound",
    );

    push_section(
        &mut lines,
        "Research Refs",
        &ctx.language_research_refs
            .iter()
            .map(|reference| {
                format!(
                    "language `{}` via agent `{}` report `{}`",
                    reference.language, reference.agent_id, reference.report_path
                )
            })
            .collect::<Vec<_>>(),
        "no persisted language research refs were available",
    );

    push_section(
        &mut lines,
        "Lineage",
        &ctx.lineage,
        "lineage was not recorded for this dispatch",
    );

    push_section(
        &mut lines,
        "Loaded Packs",
        &ctx.loaded_policy_refs
            .iter()
            .map(|policy| format!("{} {} {}", policy.category, policy.id, policy.version))
            .collect::<Vec<_>>(),
        "no packs were resolved",
    );

    if !ctx.warnings.is_empty() {
        push_section(&mut lines, "Warnings", &ctx.warnings, "none");
    }

    lines.push("## Operating Rules".to_string());
    lines.push(String::new());
    lines.push("- Write a full `report.md` under the current agent directory even when the outcome is `OUT_OF_SCOPE`, `LOW_SIGNAL`, or `NO_FINDINGS`.".to_string());
    lines.push("- Keep `_agent.json`, `_agent.toml`, and child manifests in sync through `mpcr reviewer ...` session mutations rather than ad-hoc file writes.".to_string());
    lines.push("- When you delegate helper work, claim the parent scope first and pass the child only a new sub-scope so work is not duplicated.".to_string());
    lines.push("- Stop cleanly on low-signal, duplicate, non-actionable, or already-addressed findings after recording the reason.".to_string());
    lines.push(String::new());

    lines.push(
        store.render(
            PolicyCategory::Mode,
            &mode_slug(ctx.role.mode),
            ctx.loaded_policy_refs
                .iter()
                .find(|policy| policy.category == PolicyCategory::Mode)
                .map_or(PolicyView::Checklist, |policy| policy.view),
        )?,
    );
    lines.push(String::new());
    lines.push(
        store.render(
            PolicyCategory::Worker,
            &ctx.role.worker_policy_id,
            ctx.loaded_policy_refs
                .iter()
                .find(|policy| {
                    policy.category == PolicyCategory::Worker
                        && policy.id == ctx.role.worker_policy_id
                })
                .map_or(PolicyView::Checklist, |policy| policy.view),
        )?,
    );
    for module_id in &ctx.role.module_ids {
        lines.push(String::new());
        let module_view = ctx
            .loaded_policy_refs
            .iter()
            .find(|policy| policy.category == PolicyCategory::Module && policy.id == *module_id)
            .map_or(PolicyView::Checklist, |policy| policy.view);
        lines.push(store.render(PolicyCategory::Module, module_id, module_view)?);
    }

    Ok(lines.join("\n").trim_end().to_string())
}

/// Return the structured protocol list in stable order.
pub fn list() -> anyhow::Result<Vec<PolicyListEntry>> {
    Ok(PolicyStore::load()?.list())
}

/// Return one static mode policy view.
pub fn mode(mode: &str, view: PolicyView) -> anyhow::Result<ProtocolOutput> {
    let store = PolicyStore::load()?;
    Ok(ProtocolOutput {
        category: PolicyCategory::Mode,
        id: mode.to_string(),
        view,
        content: store.render(PolicyCategory::Mode, mode, view)?,
    })
}

/// Return one static worker policy view.
pub fn worker(kind: &str, view: PolicyView) -> anyhow::Result<ProtocolOutput> {
    let store = PolicyStore::load()?;
    Ok(ProtocolOutput {
        category: PolicyCategory::Worker,
        id: kind.to_string(),
        view,
        content: store.render(PolicyCategory::Worker, kind, view)?,
    })
}

/// Return one static module policy view.
pub fn module(id: &str, view: PolicyView) -> anyhow::Result<ProtocolOutput> {
    let store = PolicyStore::load()?;
    Ok(ProtocolOutput {
        category: PolicyCategory::Module,
        id: id.to_string(),
        view,
        content: store.render(PolicyCategory::Module, id, view)?,
    })
}

/// Return one static escalation policy view.
pub fn escalation(id: &str, view: PolicyView) -> anyhow::Result<ProtocolOutput> {
    let store = PolicyStore::load()?;
    Ok(ProtocolOutput {
        category: PolicyCategory::Escalation,
        id: id.to_string(),
        view,
        content: store.render(PolicyCategory::Escalation, id, view)?,
    })
}

pub fn dispatch(
    role: &str,
    locator: Option<&SessionLocator>,
    reviewer_id: Option<&str>,
    view: PolicyView,
) -> anyhow::Result<DispatchOutput> {
    let store = PolicyStore::load()?;
    let ctx = dispatch_context(normalize_dispatch_role(role)?, locator, reviewer_id, view)?;
    Ok(DispatchOutput {
        role: ctx.role.role.clone(),
        view,
        reviewer_id: ctx.reviewer_id.clone(),
        session_id: ctx.session_id.clone(),
        target_ref: ctx.target_ref.clone(),
        mode: Some(ctx.role.mode),
        execution_architecture: ctx.route.as_ref().map(|route| route.execution_architecture),
        agent_dir: ctx.agent_dir.clone(),
        report_path: ctx.report_path.clone(),
        role_kind: ctx.role_kind.clone(),
        module_ids: ctx.role.module_ids.clone(),
        focus_surfaces: ctx.focus_surfaces.clone(),
        claimed_scope: ctx.claimed_scope.clone(),
        delegated_scope: ctx.delegated_scope.clone(),
        lineage: ctx.lineage.clone(),
        language_research_refs: ctx.language_research_refs.clone(),
        loaded_policy_refs: ctx.loaded_policy_refs.clone(),
        warnings: ctx.warnings.clone(),
        content: render_dispatch_content(&ctx, &store)?,
    })
}

pub fn dispatch_list() -> Vec<String> {
    let mut roles = ModuleId::all()
        .into_iter()
        .map(|module_id| format!("domain:{}", module_slug(module_id)))
        .collect::<Vec<_>>();
    roles.extend([
        "language-detector".to_string(),
        "language-research:<language>".to_string(),
        "final-synthesis".to_string(),
        "apply-composite".to_string(),
        "applicator-worker".to_string(),
        "applicator-verifier".to_string(),
    ]);
    roles
}

/// Generated reviewer fallback doc.
pub fn reviewer_fallback_doc() -> anyhow::Result<String> {
    generate_reviewer_fallback(&PolicyStore::load()?)
}

/// Generated applicator fallback doc.
pub fn applicator_fallback_doc() -> anyhow::Result<String> {
    generate_applicator_fallback(&PolicyStore::load()?)
}

/// Generated full-cycle fallback doc.
pub fn fullcycle_fallback_doc() -> anyhow::Result<String> {
    generate_fullcycle_fallback(&PolicyStore::load()?)
}

/// Generated orchestrator fallback doc.
pub fn orchestrator_fallback_doc() -> anyhow::Result<String> {
    generate_orchestrator_fallback(&PolicyStore::load()?)
}

/// Materialize generated fallback docs under the skill `references/` directory.
pub fn materialize_fallback_docs(skill_root: &Path) -> anyhow::Result<()> {
    let references_dir = skill_root.join("references");
    fs::create_dir_all(&references_dir)?;
    fs::write(
        references_dir.join("reviewer-fallback.md"),
        reviewer_fallback_doc()?,
    )?;
    fs::write(
        references_dir.join("applicator-fallback.md"),
        applicator_fallback_doc()?,
    )?;
    fs::write(
        references_dir.join("fullcycle-fallback.md"),
        fullcycle_fallback_doc()?,
    )?;
    fs::write(
        references_dir.join("orchestrator-fallback.md"),
        orchestrator_fallback_doc()?,
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::ensure;
    use tempfile::tempdir;

    #[test]
    fn list_and_lookup_are_available() -> anyhow::Result<()> {
        let entries = list()?;
        ensure!(entries.iter().any(|entry| entry.id == "reviewer"));
        let output = mode("reviewer", PolicyView::Brief)?;
        ensure!(output.content.contains("reviewer"));
        let worker_output = worker("review-composite", PolicyView::Checklist)?;
        ensure!(worker_output.content.contains("## Must"));
        Ok(())
    }

    #[test]
    fn dispatch_supports_domain_roles_without_session_context() -> anyhow::Result<()> {
        let output = dispatch("domain:core-correctness", None, None, PolicyView::Checklist)?;
        ensure!(output
            .content
            .contains("# Dispatch domain:core-correctness"));
        ensure!(output.content.contains("## Operating Rules"));
        ensure!(output
            .loaded_policy_refs
            .iter()
            .any(|policy| policy.id == "domain-reviewer"));
        Ok(())
    }

    #[test]
    fn dispatch_supports_apply_composite_role() -> anyhow::Result<()> {
        let output = dispatch("apply-composite", None, None, PolicyView::Checklist)?;
        ensure!(output.content.contains("# Dispatch apply-composite"));
        ensure!(output
            .loaded_policy_refs
            .iter()
            .any(|policy| policy.id == "apply-composite"));
        Ok(())
    }

    #[test]
    fn dispatch_renders_modules_in_requested_view() -> anyhow::Result<()> {
        let output = dispatch("domain:core-correctness", None, None, PolicyView::Examples)?;
        let module_output = module("core-correctness", PolicyView::Examples)?;
        ensure!(output.content.contains(&module_output.content));
        Ok(())
    }

    #[test]
    fn materialize_fallback_docs_writes_generated_files() -> anyhow::Result<()> {
        let skill_root = tempdir()?;
        materialize_fallback_docs(skill_root.path())?;
        ensure!(skill_root
            .path()
            .join("references/reviewer-fallback.md")
            .exists());
        ensure!(skill_root
            .path()
            .join("references/applicator-fallback.md")
            .exists());
        ensure!(skill_root
            .path()
            .join("references/fullcycle-fallback.md")
            .exists());
        ensure!(skill_root
            .path()
            .join("references/orchestrator-fallback.md")
            .exists());
        Ok(())
    }
}
