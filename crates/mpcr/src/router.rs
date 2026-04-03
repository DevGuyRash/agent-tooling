//! Adaptive semantic routing for the v2 code-review workflow.
#![allow(missing_docs)]

use crate::artifacts::{
    ArtifactHeader, CapabilityProfile, EscalationId, ExecutionArchitecture, Mode, ModuleId,
    PolicyCategory, PolicyRef, PolicyView, ResourceBudget, RigorLevel, RiskSurfaceRecord,
    RouteDecisionArtifact, RouteRevisionArtifact, SurfaceId, SurfaceMapArtifact, WorkerKind,
    WorkerPlanRecord, POLICY_BUNDLE_VERSION,
};
use crate::router_types::{HistorySignals, RouteInputs, RouteRevisionRequest, ScopeSignals};

fn router_policy_ref(id: &str) -> PolicyRef {
    PolicyRef {
        category: PolicyCategory::Worker,
        id: id.to_string(),
        version: POLICY_BUNDLE_VERSION.to_string(),
        view: PolicyView::Checklist,
    }
}

fn module_policy_ref(id: ModuleId) -> PolicyRef {
    PolicyRef {
        category: PolicyCategory::Module,
        id: toml::Value::try_from(id).map_or_else(
            |_| "unknown".to_string(),
            |value| value.to_string().trim_matches('"').to_string(),
        ),
        version: POLICY_BUNDLE_VERSION.to_string(),
        view: PolicyView::Checklist,
    }
}

fn risk_surface(
    surface_id: SurfaceId,
    reason: impl Into<String>,
    evidence: Vec<String>,
) -> RiskSurfaceRecord {
    RiskSurfaceRecord {
        surface_id,
        weight: surface_id.default_weight(),
        reason: reason.into(),
        evidence_refs: evidence,
        behavior_facing: matches!(
            surface_id,
            SurfaceId::PublicApi
                | SurfaceId::DocsStaleness
                | SurfaceId::OperatorGuidance
                | SurfaceId::ConfigSurface
        ),
    }
}

fn detect_surfaces_for_file(path: &str) -> Vec<SurfaceId> {
    let lower = path.to_ascii_lowercase();
    let mut surfaces = Vec::new();
    if lower.contains("api")
        || lower.contains("openapi")
        || lower.contains("proto")
        || lower.contains("graphql")
        || lower.contains("route")
        || lower.contains("cli")
    {
        surfaces.push(SurfaceId::PublicApi);
    }
    if lower.contains("auth") || lower.contains("login") || lower.contains("permission") {
        surfaces.push(SurfaceId::AuthAccess);
    }
    if lower.contains("input") || lower.contains("validate") || lower.contains("sanitize") {
        surfaces.push(SurfaceId::InputValidation);
    }
    if lower.contains("admin") || lower.contains("privilege") || lower.contains("rbac") {
        surfaces.push(SurfaceId::PrivilegeBoundary);
    }
    if lower.contains("db") || lower.contains("store") || lower.contains("persist") {
        surfaces.push(SurfaceId::Persistence);
    }
    if lower.contains("migration") || lower.contains("schema") {
        surfaces.push(SurfaceId::Migration);
        surfaces.push(SurfaceId::Persistence);
        surfaces.push(SurfaceId::DataIntegrity);
    }
    if lower.contains("integrity") || lower.contains("checksum") {
        surfaces.push(SurfaceId::DataIntegrity);
    }
    if lower.contains("async")
        || lower.contains("concurr")
        || lower.contains("thread")
        || lower.contains("atomic")
        || lower.contains("queue")
    {
        surfaces.push(SurfaceId::Concurrency);
    }
    if lower.contains("state") || lower.contains("workflow") || lower.contains("fsm") {
        surfaces.push(SurfaceId::StateMachine);
    }
    if lower.ends_with(".md")
        || lower.contains("readme")
        || lower.contains("example")
        || lower.contains("help")
    {
        surfaces.push(SurfaceId::DocsStaleness);
    }
    if lower.contains("runbook") || lower.contains("deploy") || lower.contains("operator") {
        surfaces.push(SurfaceId::OperatorGuidance);
    }
    if lower.contains("config")
        || lower.ends_with(".toml")
        || lower.ends_with(".yaml")
        || lower.ends_with(".yml")
        || lower.ends_with(".env")
    {
        surfaces.push(SurfaceId::ConfigSurface);
    }
    if lower.contains("perf") || lower.contains("cache") || lower.contains("benchmark") {
        surfaces.push(SurfaceId::PerformanceHotpath);
    }
    if lower.ends_with("cargo.toml")
        || lower.contains("package-lock")
        || lower.contains("pnpm-lock")
        || lower.contains("poetry.lock")
        || lower.contains("dockerfile")
    {
        surfaces.push(SurfaceId::DependencyBuild);
    }
    if has_test_or_spec_signal(&lower) {
        surfaces.push(SurfaceId::TestCoverage);
    }
    if lower.contains("metric") || lower.contains("trace") || lower.contains("log") {
        surfaces.push(SurfaceId::Observability);
    }
    if lower.contains("privacy") || lower.contains("pii") || lower.contains("gdpr") {
        surfaces.push(SurfaceId::Privacy);
    }
    surfaces.sort_unstable();
    surfaces.dedup();
    surfaces
}

fn has_test_or_spec_signal(path: &str) -> bool {
    let trimmed = path.trim_matches('/');
    if trimmed.is_empty() {
        return false;
    }

    let mut components = trimmed.split('/').peekable();
    while let Some(component) = components.next() {
        let is_last = components.peek().is_none();
        if component == "test"
            || component == "tests"
            || component == "spec"
            || component == "specs"
            || component == "__tests__"
            || component == "__specs__"
        {
            return true;
        }

        if is_last && file_name_has_test_or_spec_signal(component) {
            return true;
        }
    }

    false
}

fn file_name_has_test_or_spec_signal(file_name: &str) -> bool {
    let stem = file_name
        .rsplit_once('.')
        .map_or(file_name, |(stem, _ext)| stem);

    stem == "test"
        || stem == "spec"
        || stem.starts_with("test_")
        || stem.starts_with("spec_")
        || stem.ends_with("_test")
        || stem.ends_with("_spec")
        || stem.ends_with(".test")
        || stem.ends_with(".spec")
}

fn is_source_like_file(path: &str) -> bool {
    let lower = path.to_ascii_lowercase();
    let source_roots = ["src/", "lib/", "app/", "server/", "client/"];
    let source_exts = [
        ".rs", ".js", ".jsx", ".ts", ".tsx", ".py", ".go", ".java", ".kt", ".cs", ".rb", ".php",
    ];
    let excluded_exts = [".md", ".toml", ".yaml", ".yml", ".json", ".lock", ".env"];

    if excluded_exts.iter().any(|ext| lower.ends_with(ext)) {
        return false;
    }
    if lower.contains("docs/")
        || lower.contains("readme")
        || lower.contains("example")
        || lower.contains("help")
        || has_test_or_spec_signal(&lower)
    {
        return false;
    }

    source_roots.iter().any(|root| lower.contains(root))
        || source_exts.iter().any(|ext| lower.ends_with(ext))
}

fn has_docs_change(changed_files: &[String]) -> bool {
    changed_files.iter().any(|file| {
        let lower = file.to_ascii_lowercase();
        lower.ends_with(".md")
            || lower.contains("readme")
            || lower.contains("docs/")
            || lower.contains("example")
            || lower.contains("help")
    })
}

fn modules_for_surface(surface_id: SurfaceId) -> Vec<ModuleId> {
    match surface_id {
        SurfaceId::BehaviorChange => vec![ModuleId::CoreCorrectness],
        SurfaceId::PublicApi => vec![ModuleId::CoreCorrectness, ModuleId::ShipReadiness],
        SurfaceId::AuthAccess => vec![ModuleId::AuthAccess, ModuleId::InputValidation],
        SurfaceId::InputValidation => vec![ModuleId::InputValidation],
        SurfaceId::PrivilegeBoundary => vec![ModuleId::AuthAccess, ModuleId::Privacy],
        SurfaceId::Persistence => vec![ModuleId::Persistence, ModuleId::DataIntegrity],
        SurfaceId::Migration => vec![
            ModuleId::Persistence,
            ModuleId::DataIntegrity,
            ModuleId::ShipReadiness,
        ],
        SurfaceId::DataIntegrity => vec![ModuleId::DataIntegrity],
        SurfaceId::Concurrency => vec![ModuleId::Concurrency],
        SurfaceId::StateMachine => vec![ModuleId::CoreCorrectness, ModuleId::Concurrency],
        SurfaceId::DocsStaleness => vec![ModuleId::DocsStaleness],
        SurfaceId::OperatorGuidance => vec![ModuleId::OperatorGuidance, ModuleId::DocsStaleness],
        SurfaceId::ConfigSurface => vec![ModuleId::OperatorGuidance, ModuleId::ShipReadiness],
        SurfaceId::PerformanceHotpath => vec![ModuleId::Performance],
        SurfaceId::DependencyBuild => vec![ModuleId::Dependency, ModuleId::ShipReadiness],
        SurfaceId::TestCoverage => vec![ModuleId::Tests],
        SurfaceId::Observability => vec![ModuleId::Observability],
        SurfaceId::Privacy => vec![ModuleId::Privacy],
    }
}

fn canonical_selected_modules(extra_modules: &[ModuleId]) -> Vec<ModuleId> {
    let mut selected_modules = ModuleId::all().to_vec();
    selected_modules.extend(extra_modules.iter().copied());
    selected_modules.sort_unstable();
    selected_modules.dedup();
    selected_modules
}

fn detect_languages(changed_files: &[String]) -> Vec<String> {
    let mut languages = changed_files
        .iter()
        .filter_map(|file| {
            let language = if file.ends_with(".rs") {
                Some("rust")
            } else if file.ends_with(".py") {
                Some("python")
            } else if file.ends_with(".js") || file.ends_with(".jsx") {
                Some("javascript")
            } else if file.ends_with(".ts") || file.ends_with(".tsx") {
                Some("typescript")
            } else if file.ends_with(".go") {
                Some("go")
            } else if file.ends_with(".java") {
                Some("java")
            } else if file.ends_with(".rb") {
                Some("ruby")
            } else if file.ends_with(".php") {
                Some("php")
            } else if file.ends_with(".kt") {
                Some("kotlin")
            } else if file.ends_with(".cs") {
                Some("csharp")
            } else {
                None
            };
            language.map(ToString::to_string)
        })
        .collect::<Vec<_>>();
    languages.sort();
    languages.dedup();
    languages
}

fn scope_signals_for_modules(
    mut scope_signals: ScopeSignals,
    selected_modules: &[ModuleId],
) -> ScopeSignals {
    if selected_modules.contains(&ModuleId::ScopeCreep) {
        scope_signals.scope_creep_detected = true;
    }
    scope_signals
}

fn heldback_escalations_for_route(
    mode: Mode,
    surfaces: &[RiskSurfaceRecord],
    scope_signals: &ScopeSignals,
) -> Vec<EscalationId> {
    let mut heldback_escalations = vec![EscalationId::MalformedOutput];
    if surfaces.iter().any(|surface| {
        matches!(
            surface.surface_id,
            SurfaceId::AuthAccess
                | SurfaceId::PrivilegeBoundary
                | SurfaceId::InputValidation
                | SurfaceId::Privacy
        )
    }) {
        heldback_escalations.push(EscalationId::SecurityEscalation);
    }
    if mode == Mode::FullCycle {
        heldback_escalations.push(EscalationId::Reopen);
    }
    if scope_signals.scope_creep_detected || scope_signals.overengineering_detected {
        heldback_escalations.push(EscalationId::ScopeCreep);
    }
    heldback_escalations.sort_unstable();
    heldback_escalations.dedup();
    heldback_escalations
}

fn widen_architecture(architecture: ExecutionArchitecture) -> ExecutionArchitecture {
    match architecture {
        ExecutionArchitecture::Direct => ExecutionArchitecture::Hybrid,
        ExecutionArchitecture::Hybrid | ExecutionArchitecture::Delegated => {
            ExecutionArchitecture::Delegated
        }
    }
}

fn determine_rigor(
    surfaces: &[RiskSurfaceRecord],
    history: &crate::router_types::HistorySignals,
) -> RigorLevel {
    let surface_ids = surfaces
        .iter()
        .map(|record| record.surface_id)
        .collect::<Vec<_>>();
    let total_weight = surfaces
        .iter()
        .map(|record| u16::from(record.weight))
        .sum::<u16>();
    let has_behavior_facing = surfaces.iter().any(|record| record.behavior_facing);
    let has_high_risk = surface_ids.iter().any(|surface_id| {
        matches!(
            surface_id,
            SurfaceId::PublicApi
                | SurfaceId::AuthAccess
                | SurfaceId::PrivilegeBoundary
                | SurfaceId::Migration
                | SurfaceId::DataIntegrity
                | SurfaceId::Concurrency
        )
    });
    let lite = surfaces.iter().all(|surface| surface.weight < 4)
        && !has_behavior_facing
        && !surface_ids.iter().any(|surface_id| {
            matches!(
                surface_id,
                SurfaceId::PublicApi
                    | SurfaceId::AuthAccess
                    | SurfaceId::PrivilegeBoundary
                    | SurfaceId::Persistence
                    | SurfaceId::Migration
                    | SurfaceId::DataIntegrity
                    | SurfaceId::Concurrency
                    | SurfaceId::Privacy
                    | SurfaceId::PerformanceHotpath
            )
        });
    if lite {
        return RigorLevel::Lite;
    }
    if has_high_risk || total_weight >= 9 {
        return RigorLevel::Forensic;
    }
    if total_weight >= 8 && history.prior_reopens > 0 {
        return RigorLevel::Forensic;
    }
    RigorLevel::Standard
}

fn determine_architecture(
    capability: crate::artifacts::ExecutionCapability,
    rigor: RigorLevel,
    surface_count: usize,
) -> ExecutionArchitecture {
    match capability {
        crate::artifacts::ExecutionCapability::SingleProcess => ExecutionArchitecture::Direct,
        crate::artifacts::ExecutionCapability::BoundedHelpers => {
            if rigor == RigorLevel::Lite && surface_count <= 2 {
                ExecutionArchitecture::Direct
            } else {
                ExecutionArchitecture::Hybrid
            }
        }
        crate::artifacts::ExecutionCapability::ParallelSubagents => {
            if rigor == RigorLevel::Lite && surface_count <= 1 {
                ExecutionArchitecture::Direct
            } else {
                ExecutionArchitecture::Delegated
            }
        }
    }
}

fn worker_plan_record(
    worker_kind: WorkerKind,
    role_id: Option<String>,
    language: Option<String>,
    module_ids: Vec<ModuleId>,
    focus_surfaces: Vec<SurfaceId>,
    claimed_scope: Vec<String>,
    delegated_scope: Vec<String>,
    required: bool,
    parallelizable: bool,
) -> WorkerPlanRecord {
    WorkerPlanRecord {
        worker_kind,
        role_id,
        language,
        module_ids,
        focus_surfaces,
        claimed_scope,
        delegated_scope,
        required,
        parallelizable,
    }
}

fn build_worker_plan(
    mode: Mode,
    architecture: ExecutionArchitecture,
    surfaces: &[RiskSurfaceRecord],
    selected_modules: &[ModuleId],
    languages: &[String],
    scope_signals: ScopeSignals,
    staleness_required: bool,
) -> Vec<WorkerPlanRecord> {
    if mode == Mode::Applicator {
        let focus_surfaces = surfaces
            .iter()
            .map(|surface| surface.surface_id)
            .collect::<Vec<_>>();
        if architecture == ExecutionArchitecture::Direct {
            return vec![worker_plan_record(
                WorkerKind::ApplyComposite,
                Some("apply-composite".to_string()),
                None,
                selected_modules.to_vec(),
                focus_surfaces,
                Vec::new(),
                Vec::new(),
                true,
                false,
            )];
        }
        return vec![
            worker_plan_record(
                WorkerKind::ApplicatorWorker,
                Some("applicator-worker".to_string()),
                None,
                selected_modules.to_vec(),
                focus_surfaces.clone(),
                Vec::new(),
                Vec::new(),
                true,
                architecture == ExecutionArchitecture::Delegated,
            ),
            worker_plan_record(
                WorkerKind::ApplicatorVerifier,
                Some("applicator-verifier".to_string()),
                None,
                selected_modules.to_vec(),
                focus_surfaces,
                Vec::new(),
                Vec::new(),
                true,
                false,
            ),
        ];
    }
    let surface_ids = surfaces
        .iter()
        .map(|surface| surface.surface_id)
        .collect::<Vec<_>>();
    let mut plan = vec![worker_plan_record(
        WorkerKind::LanguageDetector,
        Some("language-detector".to_string()),
        None,
        Vec::new(),
        surface_ids.clone(),
        vec!["infer changed-file languages".to_string()],
        Vec::new(),
        true,
        false,
    )];
    for language in languages {
        plan.push(worker_plan_record(
            WorkerKind::LanguageResearch,
            Some(format!("language-research:{language}")),
            Some(language.clone()),
            Vec::new(),
            surface_ids.clone(),
            vec![format!("research language `{language}` primary sources")],
            vec!["do not re-run language research in domain agents".to_string()],
            true,
            architecture == ExecutionArchitecture::Delegated,
        ));
    }
    for module_id in selected_modules {
        let role_id = format!(
            "domain:{}",
            toml::Value::try_from(*module_id).map_or_else(
                |_| "unknown".to_string(),
                |value| value.to_string().trim_matches('"').to_string()
            )
        );
        let mut claimed_scope = vec![format!(
            "own domain `{}`",
            role_id.trim_start_matches("domain:")
        )];
        if *module_id == ModuleId::DocsStaleness && staleness_required {
            claimed_scope.push("treat behavior-facing staleness as required".to_string());
        }
        if *module_id == ModuleId::ScopeCreep
            && !(scope_signals.scope_creep_detected || scope_signals.overengineering_detected)
        {
            claimed_scope.push("likely low-signal or out-of-scope".to_string());
        }
        plan.push(worker_plan_record(
            WorkerKind::DomainReviewer,
            Some(role_id),
            None,
            vec![*module_id],
            surface_ids.clone(),
            claimed_scope,
            vec!["do not delegate the same domain investigation again".to_string()],
            true,
            architecture != ExecutionArchitecture::Direct,
        ));
    }
    plan.push(worker_plan_record(
        WorkerKind::FinalSynthesizer,
        Some("final-synthesis".to_string()),
        None,
        vec![ModuleId::ShipReadiness],
        surface_ids,
        vec!["synthesize descendant reports".to_string()],
        vec!["do not reopen low-signal duplicate findings".to_string()],
        true,
        false,
    ));
    plan
}

fn budgeted_worker_plan(
    mode: Mode,
    architecture: ExecutionArchitecture,
    surfaces: &[RiskSurfaceRecord],
    selected_modules: &[ModuleId],
    languages: &[String],
    scope_signals: ScopeSignals,
    staleness_required: bool,
    max_worker_count: u8,
) -> (ExecutionArchitecture, Vec<WorkerPlanRecord>) {
    let final_architecture = if mode == Mode::Applicator && max_worker_count < 2 {
        ExecutionArchitecture::Direct
    } else {
        architecture
    };
    let worker_plan = build_worker_plan(
        mode,
        final_architecture,
        surfaces,
        selected_modules,
        languages,
        scope_signals.clone(),
        staleness_required,
    );
    (final_architecture, worker_plan)
}

/// Build a deterministic surface map from changed files and declared interfaces.
pub fn build_surface_map(header: ArtifactHeader, inputs: &RouteInputs) -> SurfaceMapArtifact {
    let mut discovered = Vec::new();
    let mut behavior_facing_artifacts = inputs.behavior_facing_artifacts.clone();
    for file in &inputs.changed_files {
        let surfaces = detect_surfaces_for_file(file);
        let has_detected_surface = !surfaces.is_empty();
        for surface_id in surfaces {
            if !discovered
                .iter()
                .any(|existing: &RiskSurfaceRecord| existing.surface_id == surface_id)
            {
                discovered.push(risk_surface(
                    surface_id,
                    format!("derived from changed file `{file}`"),
                    vec![file.clone()],
                ));
            }
        }
        if is_source_like_file(file)
            && !has_detected_surface
            && !discovered
                .iter()
                .any(|existing| existing.surface_id == SurfaceId::BehaviorChange)
        {
            discovered.push(risk_surface(
                SurfaceId::BehaviorChange,
                format!("derived from generic source change `{file}`"),
                vec![file.clone()],
            ));
        }
        let lower = file.to_ascii_lowercase();
        if lower.ends_with(".md")
            || lower.contains("readme")
            || lower.contains("example")
            || lower.contains("help")
            || lower.contains("config")
            || lower.contains("runbook")
        {
            behavior_facing_artifacts.push(file.clone());
        }
    }
    for interface in &inputs.public_interfaces {
        if !discovered
            .iter()
            .any(|existing| existing.surface_id == SurfaceId::PublicApi)
        {
            discovered.push(risk_surface(
                SurfaceId::PublicApi,
                "derived from declared public interfaces".to_string(),
                inputs.public_interfaces.clone(),
            ));
        }
        behavior_facing_artifacts.push(interface.clone());
    }

    behavior_facing_artifacts.sort();
    behavior_facing_artifacts.dedup();
    let staleness_required = !behavior_facing_artifacts.is_empty()
        || (discovered.iter().any(|surface| {
            matches!(
                surface.surface_id,
                SurfaceId::PublicApi | SurfaceId::ConfigSurface | SurfaceId::OperatorGuidance
            )
        }) && !has_docs_change(&inputs.changed_files));

    if staleness_required
        && !discovered
            .iter()
            .any(|surface| surface.surface_id == SurfaceId::DocsStaleness)
    {
        discovered.push(risk_surface(
            SurfaceId::DocsStaleness,
            "behavior-facing change requires staleness checks".to_string(),
            behavior_facing_artifacts.clone(),
        ));
    }
    discovered.sort_by_key(|surface| surface.surface_id);

    let mut suggested_modules = vec![ModuleId::CoreCorrectness, ModuleId::ShipReadiness];
    for surface in &discovered {
        suggested_modules.extend(modules_for_surface(surface.surface_id));
    }
    if staleness_required {
        suggested_modules.push(ModuleId::DocsStaleness);
    }
    suggested_modules.sort_unstable();
    suggested_modules.dedup();

    SurfaceMapArtifact {
        header,
        changed_files: inputs.changed_files.clone(),
        public_interfaces: inputs.public_interfaces.clone(),
        behavior_facing_artifacts,
        risk_surfaces: discovered,
        suggested_modules,
        staleness_required,
    }
}

/// Build a deterministic route decision from a surface map and execution inputs.
pub fn build_route_decision(
    header: ArtifactHeader,
    mode: Mode,
    surface_map: &SurfaceMapArtifact,
    inputs: &RouteInputs,
) -> RouteDecisionArtifact {
    let rigor_level = determine_rigor(&surface_map.risk_surfaces, &inputs.history_signals);
    let requested_architecture = determine_architecture(
        inputs.execution_capability,
        rigor_level,
        surface_map.risk_surfaces.len(),
    );
    let selected_modules = canonical_selected_modules(&surface_map.suggested_modules);
    let languages = detect_languages(&surface_map.changed_files);
    let staleness_required = selected_modules.contains(&ModuleId::DocsStaleness);
    let scope_signals = scope_signals_for_modules(
        ScopeSignals::from_changed_files(&surface_map.changed_files),
        &selected_modules,
    );
    let (execution_architecture, worker_plan) = budgeted_worker_plan(
        mode,
        requested_architecture,
        &surface_map.risk_surfaces,
        &selected_modules,
        &languages,
        scope_signals.clone(),
        staleness_required,
        inputs.max_worker_count,
    );
    let capability_profile = CapabilityProfile {
        execution_capability: inputs.execution_capability,
        max_worker_count: inputs.max_worker_count,
        orchestrator_read_budget_lines: inputs.orchestrator_read_budget_lines,
        orchestrator_read_budget_snippets: inputs.orchestrator_read_budget_snippets,
    };
    let planned_worker_count = match u8::try_from(worker_plan.len()) {
        Ok(value) => value,
        Err(_err) => inputs.max_worker_count,
    };
    let resource_budget = ResourceBudget {
        planned_worker_count,
        max_worker_count: inputs.max_worker_count,
    };
    let heldback_escalations =
        heldback_escalations_for_route(mode, &surface_map.risk_surfaces, &scope_signals);
    let stop_conditions = match mode {
        Mode::Reviewer => vec![
            "parent_review finalized".to_string(),
            "hard validation failure".to_string(),
        ],
        Mode::Applicator => vec![
            "application_result finalized".to_string(),
            "verification_result finalized".to_string(),
            "hard validation failure".to_string(),
        ],
        Mode::FullCycle => vec![
            "convergence_state persisted".to_string(),
            "hard validation failure".to_string(),
        ],
    };

    RouteDecisionArtifact {
        header,
        mode,
        execution_architecture,
        rigor_level,
        capability_profile,
        resource_budget,
        risk_surfaces: surface_map.risk_surfaces.clone(),
        selected_modules,
        worker_plan,
        heldback_escalations,
        stop_conditions,
    }
}

/// Apply a bounded route revision to an existing route decision.
pub fn apply_route_revision(
    route: &RouteDecisionArtifact,
    revision: &RouteRevisionRequest,
) -> RouteDecisionArtifact {
    let mut revised = route.clone();
    for surface_id in &revision.discovered_surfaces {
        if !revised
            .risk_surfaces
            .iter()
            .any(|surface| surface.surface_id == *surface_id)
        {
            revised.risk_surfaces.push(risk_surface(
                *surface_id,
                "route revision discovered new semantic surface".to_string(),
                Vec::new(),
            ));
        }
    }
    revised
        .risk_surfaces
        .sort_by_key(|surface| surface.surface_id);
    let mut extra_modules = route.selected_modules.clone();
    extra_modules.extend(revision.added_modules.iter().copied());
    revised.selected_modules = canonical_selected_modules(&extra_modules);
    let languages = route
        .worker_plan
        .iter()
        .filter_map(|worker| worker.language.clone())
        .collect::<Vec<_>>();
    let scope_signals = scope_signals_for_modules(
        ScopeSignals::from_changed_files(&[]),
        &revised.selected_modules,
    );
    let recomputed_rigor = determine_rigor(&revised.risk_surfaces, &HistorySignals::default());
    revised.rigor_level = if revision.raise_rigor {
        RigorLevel::Forensic
    } else {
        route.rigor_level.max(recomputed_rigor)
    };
    let requested_architecture = if revision.widen_architecture {
        widen_architecture(route.execution_architecture)
    } else {
        route.execution_architecture
    };
    let staleness_required = revised.selected_modules.contains(&ModuleId::DocsStaleness);
    let (execution_architecture, worker_plan) = budgeted_worker_plan(
        route.mode,
        requested_architecture,
        &revised.risk_surfaces,
        &revised.selected_modules,
        &languages,
        scope_signals.clone(),
        staleness_required,
        route.capability_profile.max_worker_count,
    );
    revised.execution_architecture = execution_architecture;
    revised.worker_plan = worker_plan;
    revised.heldback_escalations =
        heldback_escalations_for_route(route.mode, &revised.risk_surfaces, &scope_signals);
    revised.resource_budget = ResourceBudget {
        planned_worker_count: match u8::try_from(revised.worker_plan.len()) {
            Ok(value) => value,
            Err(_err) => route.capability_profile.max_worker_count,
        },
        max_worker_count: route.capability_profile.max_worker_count,
    };
    revised
}

/// Build a route-revision artifact from a request.
pub fn build_route_revision(
    header: ArtifactHeader,
    route: &RouteDecisionArtifact,
    source_artifact_id: String,
    revision: &RouteRevisionRequest,
) -> RouteRevisionArtifact {
    RouteRevisionArtifact {
        header,
        discovered_surfaces: revision
            .discovered_surfaces
            .iter()
            .map(|surface_id| {
                risk_surface(*surface_id, "route revision input".to_string(), Vec::new())
            })
            .collect(),
        added_modules: revision.added_modules.clone(),
        rigor_change: (revision.raise_rigor && route.rigor_level != RigorLevel::Forensic)
            .then_some(RigorLevel::Forensic),
        architecture_change: revision
            .widen_architecture
            .then_some(widen_architecture(route.execution_architecture)),
        reason_code: "semantic-surface-discovery".to_string(),
        source_artifact_id,
    }
}

/// Default policy refs used for the router-produced artifacts.
pub fn default_router_policy_refs(selected_modules: &[ModuleId]) -> Vec<PolicyRef> {
    let mut refs = vec![router_policy_ref("surface-mapper")];
    refs.extend(selected_modules.iter().copied().map(module_policy_ref));
    refs
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::artifacts::{
        ArtifactKind, ConfidenceLabel, ExecutionCapability, PolicyCategory, PolicyView,
        ProducerKind,
    };
    use anyhow::ensure;

    fn header(kind: ArtifactKind) -> anyhow::Result<ArtifactHeader> {
        ArtifactHeader::new(
            kind,
            "abc123def456".to_string(),
            "sess0001".to_string(),
            "refs/heads/main".to_string(),
            ProducerKind::Router,
            "2026-03-08T00:00:00Z".to_string(),
            ConfidenceLabel::High,
            90,
            vec![PolicyRef {
                category: PolicyCategory::Worker,
                id: "surface-mapper".to_string(),
                version: POLICY_BUNDLE_VERSION.to_string(),
                view: PolicyView::Checklist,
            }],
        )
    }

    fn inputs() -> RouteInputs {
        RouteInputs {
            changed_files: vec![
                "src/auth.rs".to_string(),
                "src/api.rs".to_string(),
                "docs/api.md".to_string(),
            ],
            public_interfaces: vec!["src/api.rs".to_string()],
            behavior_facing_artifacts: Vec::new(),
            execution_capability: ExecutionCapability::ParallelSubagents,
            max_worker_count: 6,
            orchestrator_read_budget_lines: 120,
            orchestrator_read_budget_snippets: 12,
            history_signals: Default::default(),
        }
    }

    #[test]
    fn routing_is_semantic_and_deterministic() -> anyhow::Result<()> {
        let inputs = inputs();
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route_a = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );
        let route_b = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc124".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:02Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );
        ensure!(route_a.rigor_level == RigorLevel::Forensic);
        ensure!(route_a.execution_architecture == route_b.execution_architecture);
        ensure!(route_a.worker_plan == route_b.worker_plan);
        ensure!(surface_map.staleness_required);
        ensure!(route_a.selected_modules.contains(&ModuleId::DocsStaleness));
        Ok(())
    }

    #[test]
    fn route_revision_can_raise_rigor_and_expand_modules() -> anyhow::Result<()> {
        let inputs = inputs();
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );
        let revised = apply_route_revision(
            &route,
            &RouteRevisionRequest {
                discovered_surfaces: vec![SurfaceId::Privacy],
                added_modules: vec![ModuleId::Privacy],
                raise_rigor: true,
                widen_architecture: true,
            },
        );
        ensure!(revised.selected_modules.contains(&ModuleId::Privacy));
        ensure!(revised.rigor_level == RigorLevel::Forensic);
        ensure!(revised
            .heldback_escalations
            .contains(&EscalationId::SecurityEscalation));
        ensure!(revised.worker_plan.len() as u8 == revised.resource_budget.planned_worker_count);
        Ok(())
    }

    #[test]
    fn weak_history_priors_only_nudge_borderline_standard_cases() -> anyhow::Result<()> {
        let mut inputs = RouteInputs {
            changed_files: vec!["src/api.rs".to_string(), "src/config.rs".to_string()],
            public_interfaces: vec!["src/api.rs".to_string()],
            behavior_facing_artifacts: Vec::new(),
            execution_capability: ExecutionCapability::ParallelSubagents,
            max_worker_count: 6,
            orchestrator_read_budget_lines: 120,
            orchestrator_read_budget_snippets: 12,
            history_signals: Default::default(),
        };
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        inputs.history_signals.prior_reopens = 1;
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );
        ensure!(route.rigor_level == RigorLevel::Forensic);
        Ok(())
    }

    #[test]
    fn generic_source_changes_emit_behavior_change_surface() -> anyhow::Result<()> {
        let mut inputs = inputs();
        inputs.execution_capability = ExecutionCapability::SingleProcess;
        inputs.changed_files = vec!["src/orders.js".to_string(), "README.md".to_string()];
        inputs.public_interfaces = Vec::new();
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );

        ensure!(surface_map
            .risk_surfaces
            .iter()
            .any(|surface| surface.surface_id == SurfaceId::BehaviorChange));
        ensure!(surface_map
            .risk_surfaces
            .iter()
            .any(|surface| surface.surface_id == SurfaceId::DocsStaleness));
        ensure!(route.selected_modules.contains(&ModuleId::CoreCorrectness));
        ensure!(route.selected_modules.contains(&ModuleId::DocsStaleness));
        ensure!(route.selected_modules.contains(&ModuleId::ShipReadiness));
        Ok(())
    }

    #[test]
    fn direct_review_routes_keep_the_full_recursive_reviewer_roster() -> anyhow::Result<()> {
        let mut inputs = inputs();
        inputs.execution_capability = ExecutionCapability::SingleProcess;
        inputs.changed_files = vec!["src/api.rs".to_string(), "docs/api.md".to_string()];
        inputs.public_interfaces = vec!["src/api.rs".to_string()];
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );

        ensure!(route.execution_architecture == ExecutionArchitecture::Direct);
        ensure!(route
            .worker_plan
            .first()
            .is_some_and(|worker| worker.worker_kind == WorkerKind::LanguageDetector));
        ensure!(route
            .worker_plan
            .last()
            .is_some_and(|worker| worker.worker_kind == WorkerKind::FinalSynthesizer));
        let domain_workers = route
            .worker_plan
            .iter()
            .filter(|worker| worker.worker_kind == WorkerKind::DomainReviewer)
            .count();
        ensure!(domain_workers == ModuleId::all().len());
        ensure!(route.selected_modules == ModuleId::all().to_vec());
        ensure!(route.selected_modules.contains(&ModuleId::DocsStaleness));
        Ok(())
    }

    #[test]
    fn parallel_subagents_keep_tiny_lite_routes_direct() -> anyhow::Result<()> {
        let mut inputs = inputs();
        inputs.changed_files = vec!["tests/unit/foo_test.rs".to_string()];
        inputs.public_interfaces = Vec::new();
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );

        ensure!(route.rigor_level == RigorLevel::Lite);
        ensure!(route.execution_architecture == ExecutionArchitecture::Direct);
        Ok(())
    }

    #[test]
    fn parallel_subagents_delegate_non_tiny_routes() -> anyhow::Result<()> {
        let mut inputs = inputs();
        inputs.changed_files = vec!["docs/api.md".to_string()];
        inputs.public_interfaces = vec!["docs/api.md".to_string()];
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Applicator,
            &surface_map,
            &inputs,
        );

        let worker_kinds = route
            .worker_plan
            .iter()
            .map(|worker| worker.worker_kind)
            .collect::<Vec<_>>();
        ensure!(route.execution_architecture == ExecutionArchitecture::Delegated);
        ensure!(worker_kinds == vec![WorkerKind::ApplicatorWorker, WorkerKind::ApplicatorVerifier]);
        Ok(())
    }

    #[test]
    fn non_direct_applicator_uses_applicator_workers_only() -> anyhow::Result<()> {
        let mut inputs = inputs();
        inputs.execution_capability = ExecutionCapability::BoundedHelpers;
        inputs.changed_files = vec!["src/auth.rs".to_string(), "src/api.rs".to_string()];
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Applicator,
            &surface_map,
            &inputs,
        );

        let worker_kinds = route
            .worker_plan
            .iter()
            .map(|worker| worker.worker_kind)
            .collect::<Vec<_>>();
        ensure!(route.execution_architecture != ExecutionArchitecture::Direct);
        ensure!(worker_kinds == vec![WorkerKind::ApplicatorWorker, WorkerKind::ApplicatorVerifier]);
        Ok(())
    }

    #[test]
    fn direct_applicator_uses_apply_composite_worker() -> anyhow::Result<()> {
        let mut inputs = inputs();
        inputs.execution_capability = ExecutionCapability::SingleProcess;
        inputs.changed_files = vec!["src/auth.rs".to_string()];
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Applicator,
            &surface_map,
            &inputs,
        );

        ensure!(route.execution_architecture == ExecutionArchitecture::Direct);
        ensure!(route.worker_plan.len() == 1);
        ensure!(route.worker_plan[0].worker_kind == WorkerKind::ApplyComposite);
        ensure!(route.worker_plan[0].role_id.as_deref() == Some("apply-composite"));
        Ok(())
    }

    #[test]
    fn applicator_budget_one_degrades_to_direct_apply_composite() -> anyhow::Result<()> {
        let mut inputs = inputs();
        inputs.execution_capability = ExecutionCapability::BoundedHelpers;
        inputs.max_worker_count = 1;
        inputs.changed_files = vec!["src/auth.rs".to_string()];
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Applicator,
            &surface_map,
            &inputs,
        );

        ensure!(route.execution_architecture == ExecutionArchitecture::Direct);
        ensure!(route.resource_budget.max_worker_count == 1);
        ensure!(route.resource_budget.planned_worker_count == 1);
        ensure!(route.worker_plan.len() == 1);
        ensure!(route.worker_plan[0].worker_kind == WorkerKind::ApplyComposite);
        Ok(())
    }

    #[test]
    fn worker_budget_does_not_shrink_canonical_reviewer_roster() -> anyhow::Result<()> {
        let mut inputs = inputs();
        inputs.max_worker_count = 1;
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );

        ensure!(route.resource_budget.max_worker_count == 1);
        ensure!(
            route.resource_budget.planned_worker_count > route.resource_budget.max_worker_count
        );
        ensure!(
            route
                .worker_plan
                .iter()
                .filter(|worker| worker.worker_kind == WorkerKind::DomainReviewer)
                .count()
                == ModuleId::all().len()
        );
        Ok(())
    }

    #[test]
    fn route_revision_reports_actual_architecture_change() -> anyhow::Result<()> {
        let mut inputs = inputs();
        inputs.execution_capability = ExecutionCapability::BoundedHelpers;
        inputs.changed_files = vec!["tests/unit/foo_test.rs".to_string()];
        inputs.public_interfaces = Vec::new();
        let surface_map = build_surface_map(header(ArtifactKind::SurfaceMap)?, &inputs);
        let route = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                "def456abc123".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );
        ensure!(route.execution_architecture == ExecutionArchitecture::Direct);

        let revision = RouteRevisionRequest {
            discovered_surfaces: vec![SurfaceId::AuthAccess],
            added_modules: vec![ModuleId::AuthAccess],
            raise_rigor: false,
            widen_architecture: true,
        };
        let artifact = build_route_revision(
            ArtifactHeader::new(
                ArtifactKind::RouteRevision,
                "abc123def789".to_string(),
                "sess0001".to_string(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:02Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&route.selected_modules),
            )?,
            &route,
            route.header.artifact_id.clone(),
            &revision,
        );
        let revised = apply_route_revision(&route, &revision);

        ensure!(artifact.architecture_change == Some(ExecutionArchitecture::Hybrid));
        ensure!(revised.execution_architecture == ExecutionArchitecture::Hybrid);
        ensure!(revised
            .worker_plan
            .iter()
            .any(|worker| worker.worker_kind == WorkerKind::LanguageDetector));
        ensure!(revised
            .worker_plan
            .iter()
            .any(|worker| worker.worker_kind == WorkerKind::FinalSynthesizer));
        Ok(())
    }
}
