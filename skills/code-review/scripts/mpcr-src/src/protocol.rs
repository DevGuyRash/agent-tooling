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

fn role_inherits_route_modules(role: &ResolvedRole) -> bool {
    matches!(
        role.worker_policy_id.as_str(),
        "domain-reviewer" | "apply-composite" | "applicator-worker" | "applicator-verifier"
    )
}

fn module_scope_label(worker_policy_id: &str) -> &'static str {
    match worker_policy_id {
        "domain-reviewer" => "own module",
        "final-synthesizer" => "synthesis module",
        _ => "module context",
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

fn policy_view_slug(view: PolicyView) -> &'static str {
    match view {
        PolicyView::Brief => "brief",
        PolicyView::Checklist => "checklist",
        PolicyView::Schema => "schema",
        PolicyView::Examples => "examples",
        PolicyView::Full => "full",
    }
}

fn policy_lookup_command(policy: &PolicyRef) -> String {
    let (subcommand, selector_flag) = match policy.category {
        PolicyCategory::Mode => ("mode", "--mode"),
        PolicyCategory::Worker => ("worker", "--kind"),
        PolicyCategory::Module => ("module", "--id"),
        PolicyCategory::Escalation => ("escalation", "--id"),
    };
    format!(
        "`mpcr protocol {subcommand} {selector_flag} {} --view {}`",
        policy.id,
        policy_view_slug(policy.view),
    )
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

    if trimmed == "orchestrator-root" {
        return Ok(ResolvedRole {
            role: trimmed.to_string(),
            mode: Mode::Reviewer,
            worker_policy_id: trimmed.to_string(),
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

    if ctx.role.module_ids.is_empty() && role_inherits_route_modules(&ctx.role) {
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

    Ok(ctx)
}

fn render_dispatch_content(ctx: &DispatchContext, store: &PolicyStore) -> anyhow::Result<String> {
    let mut lines = Vec::new();
    let has_report_destination = ctx.agent_dir.is_some() || ctx.report_path.is_some();
    lines.push(format!("# Dispatch {}", ctx.role.role));
    lines.push(String::new());
    lines.push("You SHALL keep the orchestrator thin and execute only the slice assigned in this dispatch.".to_string());
    lines.push("You SHALL treat machine artifacts as canonical and authored markdown as the required explanatory companion.".to_string());
    if has_report_destination {
        lines.push("You SHALL write your full markdown report to the agent directory resolved below before you finalize machine artifacts.".to_string());
    } else {
        lines.push("You SHALL finalize machine artifacts through the session workflow and only author companion markdown after a session-bound step gives you an explicit `agent dir` or `report path`.".to_string());
    }
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
            .map(|module_id| {
                format!(
                    "{} `{module_id}`",
                    module_scope_label(&ctx.role.worker_policy_id)
                )
            })
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
    if has_report_destination {
        lines.push("- Ensure a full `report.md` exists under the current agent directory even when the outcome is `OUT_OF_SCOPE`, `LOW_SIGNAL`, or `NO_FINDINGS`; `mpcr reviewer complete-child` and `mpcr reviewer finalize` will render it from the stored artifact when you do not author one separately.".to_string());
    } else {
        lines.push("- This dispatch does not bind an `agent dir` or `report path`. Finalize the required machine artifacts through the session workflow first, then author companion markdown only if a later session-bound step materializes a concrete report destination.".to_string());
    }
    lines.push("- Keep every surviving finding tied to at least one repo-relative `path:line` or `path:start-end` anchor. When PR threads, API docs, specs, or web sources matter, cite them in `report.md` and tie them back to anchored repo evidence instead of putting them in `findings[].anchors`.".to_string());
    lines.push("- Keep `_session.*`, `_agent.*`, and child manifests in sync through `mpcr ...` session mutations rather than ad-hoc file writes.".to_string());
    lines.push("- Use routed workers for code, PR, API-doc, and web exploration. The orchestrator routes, challenges, and synthesizes; it does not absorb sibling first-hand investigation.".to_string());
    lines.push("- When you delegate helper work, claim the parent scope first and pass the child only a new sub-scope so work is not duplicated.".to_string());
    lines.push("- Record the categorical reason, then stop only after the finding is explicitly closed as low-signal, duplicate, non-actionable, or already-addressed.".to_string());
    lines.push(String::new());

    lines.push("## Embedded Pack Contents".to_string());
    lines.push(String::new());
    lines.push(demote_markdown_headings(
        store
            .render(
                PolicyCategory::Mode,
                &mode_slug(ctx.role.mode),
                ctx.loaded_policy_refs
                    .iter()
                    .find(|policy| policy.category == PolicyCategory::Mode)
                    .map_or(PolicyView::Checklist, |policy| policy.view),
            )?
            .as_str(),
        1,
    ));
    lines.push(String::new());
    lines.push(demote_markdown_headings(
        store
            .render(
                PolicyCategory::Worker,
                &ctx.role.worker_policy_id,
                ctx.loaded_policy_refs
                    .iter()
                    .find(|policy| {
                        policy.category == PolicyCategory::Worker
                            && policy.id == ctx.role.worker_policy_id
                    })
                    .map_or(PolicyView::Checklist, |policy| policy.view),
            )?
            .as_str(),
        1,
    ));
    for module_id in &ctx.role.module_ids {
        lines.push(String::new());
        let module_view = ctx
            .loaded_policy_refs
            .iter()
            .find(|policy| policy.category == PolicyCategory::Module && policy.id == *module_id)
            .map_or(PolicyView::Checklist, |policy| policy.view);
        lines.push(demote_markdown_headings(
            store
                .render(PolicyCategory::Module, module_id, module_view)?
                .as_str(),
            1,
        ));
    }
    lines.push(String::new());

    lines.push("## Referenced Pack Lookups".to_string());
    lines.push(String::new());
    if ctx.loaded_policy_refs.is_empty() {
        lines.push("- no referenced packs were resolved".to_string());
    } else {
        lines.push("- Load only the pack you need next; do not re-read the entire skill body or unrelated policy packs.".to_string());
        for policy in &ctx.loaded_policy_refs {
            lines.push(format!(
                "- {} {} {} via {}",
                policy.category,
                policy.id,
                policy.version,
                policy_lookup_command(policy),
            ));
        }
    }
    lines.push(String::new());

    Ok(lines.join("\n").trim_end().to_string())
}

fn demote_markdown_headings(body: &str, levels: usize) -> String {
    let mut lines = Vec::new();
    for line in body.lines() {
        if let Some(demoted) = demote_atx_heading(line, levels) {
            lines.push(demoted);
        } else {
            lines.push(line.to_string());
        }
    }
    lines.join("\n")
}

fn demote_atx_heading(line: &str, levels: usize) -> Option<String> {
    let heading_width = line.bytes().take_while(|byte| *byte == b'#').count();
    if heading_width == 0 || heading_width > 6 {
        return None;
    }
    let remainder = &line[heading_width..];
    if !remainder.is_empty() && !remainder.starts_with([' ', '\t']) {
        return None;
    }
    Some(format!(
        "{}{}",
        "#".repeat(usize::min(heading_width + levels, 6)),
        remainder
    ))
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
    let mut roles = vec!["orchestrator-root".to_string()];
    roles.extend(
        ModuleId::all()
            .into_iter()
            .map(|module_id| format!("domain:{}", module_slug(module_id)))
            .collect::<Vec<_>>(),
    );
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
    use crate::artifacts::{
        ArtifactHeader, ArtifactKind, ExecutionCapability, PolicyCategory, PolicyRef, PolicyView,
        ProducerKind,
    };
    use crate::paths::session_paths;
    use crate::router::{build_route_decision, build_surface_map, default_router_policy_refs};
    use crate::router_types::RouteInputs;
    use crate::session::{ensure_session, persist_route_artifacts, PersistRouteArtifactsParams};
    use anyhow::ensure;
    use tempfile::tempdir;
    use time::{Date, Month};

    fn routed_session_locator() -> anyhow::Result<(tempfile::TempDir, SessionLocator)> {
        let repo_root = tempdir()?;
        let date = Date::from_calendar_date(2026, Month::March, 8)?;
        let session_dir = session_paths(repo_root.path(), date).session_dir;
        let locator = SessionLocator::from_session_dir(session_dir);
        let session_id = ensure_session(&locator, "refs/heads/main")?.session_id;
        let inputs = RouteInputs {
            changed_files: vec!["src/api.rs".to_string(), "docs/api.md".to_string()],
            public_interfaces: Vec::new(),
            behavior_facing_artifacts: vec!["docs/api.md".to_string()],
            execution_capability: ExecutionCapability::ParallelSubagents,
            max_worker_count: 4,
            orchestrator_read_budget_lines: 120,
            orchestrator_read_budget_snippets: 12,
            history_signals: Default::default(),
        };
        let surface_map = build_surface_map(
            ArtifactHeader::new(
                ArtifactKind::SurfaceMap,
                "abc123def456".to_string(),
                session_id.clone(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:00Z".to_string(),
                crate::artifacts::ConfidenceLabel::High,
                90,
                vec![PolicyRef {
                    category: PolicyCategory::Worker,
                    id: "surface-mapper".to_string(),
                    version: POLICY_BUNDLE_VERSION.to_string(),
                    view: PolicyView::Checklist,
                }],
            )?,
            &inputs,
        );
        let route_decision = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "fedcba654321".to_string(),
                session_id,
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:00Z".to_string(),
                crate::artifacts::ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );
        persist_route_artifacts(PersistRouteArtifactsParams {
            session: locator.clone(),
            target_ref: "refs/heads/main".to_string(),
            surface_map,
            route_decision,
        })?;
        Ok((repo_root, locator))
    }

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
        ensure!(output.content.contains("## Referenced Pack Lookups"));
        ensure!(output.content.contains("findings[].anchors"));
        ensure!(output
            .content
            .contains("The orchestrator routes, challenges, and synthesizes"));
        ensure!(output.content.contains("## Embedded Pack Contents"));
        ensure!(output
            .loaded_policy_refs
            .iter()
            .any(|policy| policy.id == "domain-reviewer"));
        ensure!(output
            .content
            .contains("`mpcr protocol worker --kind domain-reviewer --view checklist`"));
        Ok(())
    }

    #[test]
    fn dispatch_supports_orchestrator_root_without_session_context() -> anyhow::Result<()> {
        let output = dispatch("orchestrator-root", None, None, PolicyView::Checklist)?;
        ensure!(output.content.contains("# Dispatch orchestrator-root"));
        ensure!(output
            .loaded_policy_refs
            .iter()
            .any(|policy| policy.id == "orchestrator-root"));
        ensure!(output
            .content
            .contains("worker orchestrator-root 2026.03.08"));
        ensure!(output.content.contains("2-of-3 legitimacy vote"));
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
        ensure!(output.content.contains("3-voter legitimacy gate"));
        Ok(())
    }

    #[test]
    fn session_bound_dispatch_does_not_duplicate_route_module_refs() -> anyhow::Result<()> {
        let (_repo_root, locator) = routed_session_locator()?;
        let output = dispatch(
            "apply-composite",
            Some(&locator),
            None,
            PolicyView::Checklist,
        )?;
        let module_policy_count = output
            .loaded_policy_refs
            .iter()
            .filter(|policy| policy.category == PolicyCategory::Module)
            .count();
        ensure!(module_policy_count == output.module_ids.len());
        Ok(())
    }

    #[test]
    fn applicator_worker_dispatch_without_session_omits_agent_dir_requirements(
    ) -> anyhow::Result<()> {
        let output = dispatch("applicator-worker", None, None, PolicyView::Checklist)?;
        ensure!(!output.content.contains("agent directory resolved below"));
        ensure!(!output.content.contains("current agent directory"));
        ensure!(output
            .content
            .contains("does not bind an `agent dir` or `report path`"));
        Ok(())
    }

    #[test]
    fn dispatch_references_lookups_in_requested_view() -> anyhow::Result<()> {
        let output = dispatch("domain:core-correctness", None, None, PolicyView::Examples)?;
        ensure!(output
            .content
            .contains("`mpcr protocol mode --mode reviewer --view examples`"));
        ensure!(output
            .content
            .contains("`mpcr protocol worker --kind domain-reviewer --view examples`"));
        ensure!(output
            .content
            .contains("`mpcr protocol module --id core-correctness --view examples`"));
        ensure!(output.content.contains("## Embedded Pack Contents"));
        ensure!(output.content.contains("\n## reviewer\n"));
        ensure!(output.content.contains("\n## domain-reviewer\n"));
        ensure!(output.content.contains("\n## core-correctness\n"));
        Ok(())
    }

    #[test]
    fn language_detector_dispatch_does_not_inherit_route_modules_without_bound_review(
    ) -> anyhow::Result<()> {
        let (_repo_root, locator) = routed_session_locator()?;
        let output = dispatch(
            "language-detector",
            Some(&locator),
            None,
            PolicyView::Checklist,
        )?;
        ensure!(output.module_ids.is_empty());
        ensure!(!output.content.contains("own module `"));
        ensure!(
            output.content.contains("- scope was not session-bound")
                || output.content.contains("- focus surface `")
        );
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
