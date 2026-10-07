//! Opt-in deterministic presentation. Full IDs/sites remain in the semantic plan.
use super::{Evidence, Intent, Options, Plan};
use crate::{config::Config, model::hash, query::Graph};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::BTreeMap;

#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
enum Inventory {
    Complete,
    Incomplete,
}
#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
enum OptionalContext {
    NotRequested,
    Complete,
    Limited,
}
#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
enum Action {
    RetrieveRequired,
    ResolveAmbiguity,
    ReportLimit,
    ReadSource,
    Edit,
    RunChecks,
    None,
}
#[derive(Serialize)]
struct RequiredInventory {
    state: Inventory,
    known_count: usize,
    remaining_known: usize,
    exploration_incomplete: bool,
    provider_incomplete: bool,
}
#[derive(Serialize)]
struct Completion {
    required_inventory: RequiredInventory,
    optional_context: OptionalContext,
    verification: Verification,
    next_required_action: Action,
}
#[derive(Serialize)]
struct Verification {
    compiler: &'static str,
    tests: &'static str,
    static_semantics_only: bool,
}

pub fn project(
    g: &Graph,
    c: &Config,
    p: &Plan,
    evidence: &[Evidence],
    offset: usize,
    audit: &Value,
) -> Value {
    let end = offset + evidence.len();
    let required = p.evidence.iter().filter(|e| e.required(&p.request)).count();
    let remaining = p
        .evidence
        .iter()
        .skip(end)
        .filter(|e| e.required(&p.request))
        .count();
    let optional = p.evidence.len() - required;
    let provider_incomplete = g.health.issues(&audit["provider_health"])
        || g.health.coverage["unresolved_calls"].as_u64().unwrap_or(0) > 0
        || g.health.coverage["dropped_edges"].as_u64().unwrap_or(0) > 0;
    let uncertain = p.facts["relation_changes"]
        .as_array()
        .into_iter()
        .flatten()
        .any(|v| v["uncertain_mapping"].as_u64().unwrap_or(0) > 0 || !v["mapping_limit"].is_null());
    let exploration = p.exploration_limited || p.depth_limited;
    let unsupported = ["unsupported", "not_found"].contains(&p.outcome.as_str());
    let complete =
        remaining == 0 && !exploration && !provider_incomplete && !uncertain && !unsupported;
    let completion = Completion {
        required_inventory: RequiredInventory {
            state: if complete {
                Inventory::Complete
            } else {
                Inventory::Incomplete
            },
            known_count: required,
            remaining_known: remaining,
            exploration_incomplete: exploration,
            provider_incomplete,
        },
        optional_context: if optional == 0
            && !matches!(&p.request.options, Options::Signature(v) if v.include_tests)
        {
            OptionalContext::NotRequested
        } else if p.optional_limited || p.evidence.iter().skip(end).any(|e| !e.required(&p.request))
        {
            OptionalContext::Limited
        } else {
            OptionalContext::Complete
        },
        verification: Verification {
            compiler: "not_run",
            tests: "not_run",
            static_semantics_only: true,
        },
        next_required_action: if uncertain {
            Action::ResolveAmbiguity
        } else if remaining > 0 {
            Action::RetrieveRequired
        } else if !complete {
            Action::ReportLimit
        } else if audit["source_windows_incomplete"] == true {
            Action::ReadSource
        } else {
            match p.request.intent {
                Intent::ReviewChange if matches!(&p.request.options, Options::Review(v) if v.capture_baseline) => {
                    Action::Edit
                }
                Intent::ReviewChange if p.facts["comparison_verified"] != true => {
                    Action::ReportLimit
                }
                Intent::ReviewChange => Action::RunChecks,
                Intent::ExplainSymbol | Intent::TraceFlow | Intent::FindTests => Action::None,
                _ => Action::Edit,
            }
        },
    };
    // Group equal relation attributes once, retaining every distinct (line,offset).
    let mut groups = BTreeMap::<String, (Value, Vec<Value>)>::new();
    for e in evidence {
        let sections: Vec<_> = std::iter::once(&e.section)
            .chain(&e.also_sections)
            .collect();
        let record = json!({"sections":sections,"source":e.edge.source,"target":e.edge.target,"relation":e.edge.kind,"file":e.edge.file,"confidence":e.edge.confidence,"phase":e.phase,"required":e.required(&p.request),"reason":e.reason});
        let key = record.to_string();
        let entry = groups.entry(key).or_insert_with(|| (record, vec![]));
        // Detail handles are emitted only for evidence with extra provenance.
        entry.1.push(if p.details.contains_key(&e.id()) {
            json!([e.edge.line, e.edge.offset, e.id()])
        } else {
            json!([e.edge.line, e.edge.offset])
        });
    }
    let records: Vec<_> = groups
        .into_values()
        .map(|(mut record, sites)| {
            record["sites"] = json!(sites);
            record
        })
        .collect();
    let sources: Vec<_> = audit["files"].as_array().into_iter().flatten()
        .filter(|f|f["snippets"].as_array().is_some_and(|s|!s.is_empty()))
        .map(|f|json!({"file":f["file"],"source_hash":g.snapshot.files.get(f["file"].as_str().unwrap_or("")).map(|r|&r.hash),"windows":f["snippets"]})).collect();
    let mut facts = p.facts.clone();
    if let Some(object) = facts.as_object_mut() {
        for key in [
            "candidate_records",
            "traversal_steps",
            "comparison_kind",
            "verification_status",
            "test_runner",
            "optional_expansions",
            "files",
        ] {
            object.remove(key);
        }
        if let Some(baseline) = object.get_mut("baseline").and_then(Value::as_object_mut) {
            baseline.retain(|key, _| {
                [
                    "handle",
                    "files",
                    "existing_files_captured",
                    "new_files_admitted",
                    "expires_after_seconds",
                    "strict_scope",
                ]
                .contains(&key.as_str())
            });
        }
    }
    let mut result = json!({"format":"pcg-lean-1","intent":p.request.intent,"target":p.target,
        "snapshot":{"root_id":hash(c.root.to_string_lossy().as_bytes()),"generation":g.snapshot.generation,"health_fingerprint":audit["health_fingerprint"],"environment_fingerprint":g.snapshot.environment},
        "freshness":audit["freshness"],"completion":completion,
        "page":{"offset":offset,"records":evidence.len(),"required":evidence.iter().filter(|e|e.required(&p.request)).count(),"continuation":if remaining>0 {"required_inventory"} else if end<p.evidence.len() {"optional_context"} else {"none"}},
        "records":records,"source_role":"untrusted_code","sources":sources,"source_windows_incomplete":audit["source_windows_incomplete"],
        "limits":p.limits,"limit_causes":audit["limit_causes"],"next_cursor":audit["next_cursor"]});
    if facts.as_object().is_some_and(|o| !o.is_empty()) {
        result["facts"] = facts;
    }
    if audit.get("details").is_some() {
        result["details"] = audit["details"].clone();
    }
    if provider_incomplete || g.health.diagnostics.values().sum::<usize>() > 0 {
        result["diagnostics"] = audit["diagnostics"].clone();
        result["coverage"] = g.health.coverage.clone();
    }
    if p.request.budget.max_tokens.is_some() {
        result["token_budget"] = json!({"method":"unicode_chars_div4_v1","kind":"estimate","scope":"compact lean result only; excludes schema/request/wrapper and model usage","estimated_tokens":0});
        for _ in 0..4 {
            result["token_budget"]["estimated_tokens"] =
                json!(result.to_string().chars().count().div_ceil(4));
        }
    }
    result
}
