//! Conservative AST region constraints, not automatic refactoring/type inference.
use super::{Evidence, Plan, input::Extract};
use crate::{
    model::{Edge, Node},
    query::Graph,
};
use anyhow::{Result, bail};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
pub fn prepare(g: &Graph, plan: &mut Plan, region: &Extract) -> Result<()> {
    let record = &g.snapshot.files[&region.file];
    let ast = &record.intent.ast;
    if ast["version"] != 1 {
        plan.outcome = "unsupported".into();
        plan.facts["missing_capabilities"] = json!([
            "AST statement boundaries",
            "resolved local/parameter bindings",
            "read/write and control-exit facts"
        ]);
        return Ok(());
    }
    let inside = |site: &Value| {
        site["line"]
            .as_u64()
            .is_some_and(|line| line as usize >= region.start_line)
            && site["end"]
                .as_u64()
                .is_some_and(|end| end as usize <= region.end_line)
    };
    let statements: Vec<_> = ast["statements"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|site| inside(site))
        .collect();
    let outer: Vec<_> = statements
        .iter()
        .filter(|site| site["line"] == region.start_line && site["end"] == region.end_line)
        .copied()
        .collect();
    let sequence: Vec<_> = if outer.len() == 1 {
        outer
    } else {
        let first = statements
            .iter()
            .filter(|s| s["line"] == region.start_line)
            .min_by_key(|s| s["offset"].as_u64().unwrap_or(0));
        let last = statements
            .iter()
            .filter(|s| s["end"] == region.end_line)
            .max_by_key(|s| s["end_offset"].as_u64().unwrap_or(0));
        let (Some(first), Some(last)) = (first, last) else {
            bail!(
                "Extraction requires complete AST statements on the requested lines; select exact statement boundaries"
            )
        };
        if first["block"] != last["block"] || first["scope"] != last["scope"] {
            bail!("Extraction statements cross AST block/scope boundaries")
        }
        statements
            .iter()
            .filter(|s| s["block"] == first["block"] && s["scope"] == first["scope"])
            .copied()
            .collect()
    };
    let start = sequence
        .iter()
        .filter_map(|s| s["offset"].as_u64())
        .min()
        .ok_or_else(|| anyhow::anyhow!("No extractable AST statements"))?;
    let end = sequence
        .iter()
        .filter_map(|s| s["end_offset"].as_u64())
        .max()
        .unwrap_or(start);
    let scopes: BTreeSet<_> = sequence.iter().map(|s| s["scope"].to_string()).collect();
    if scopes.len() != 1 {
        bail!("Extraction region crosses lexical scopes")
    }
    let scope = sequence[0]["scope"].as_str().unwrap_or("");
    let bindings: BTreeMap<_, _> = ast["bindings"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|b| b["id"].as_str().map(|id| (id, b)))
        .collect();
    let uses: Vec<_> = ast["uses"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|site| {
            site["offset"]
                .as_u64()
                .is_some_and(|o| o >= start && o < end)
        })
        .collect();
    let after: BTreeSet<_> = ast["uses"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|s| s["scope"] == scope && s["offset"].as_u64().is_some_and(|o| o >= end))
        .filter_map(|s| s["binding"].as_str())
        .collect();
    let mut read = BTreeSet::new();
    let mut writes = BTreeSet::new();
    let mut outputs = BTreeSet::new();
    let mut unresolved = 0;
    let budget = plan.request.budget.max_traversal;
    if uses.len() > budget {
        plan.exploration_limited = true;
    }
    for site in uses.iter().take(budget) {
        let Some(id) = site["binding"].as_str() else {
            unresolved += 1;
            continue;
        };
        let Some(binding) = bindings.get(id) else {
            unresolved += 1;
            continue;
        };
        let declaration = binding["offset"].as_u64().unwrap_or(u64::MAX);
        let is_inside = declaration >= start && declaration < end;
        if !is_inside && site["read"] == true {
            read.insert(id);
        }
        if !is_inside && site["write"] == true {
            writes.insert(id);
        }
        if is_inside && after.contains(id) {
            outputs.insert(id);
        }
        plan.historical_symbols
            .insert(id.into(), binding_node(binding, id, &region.file, scope));
        let kind = match (site["read"] == true, site["write"] == true) {
            (true, true) => "local_read_write",
            (false, true) => "local_write",
            (true, false) => "local_read",
            _ => "local_access",
        };
        plan.evidence.push(Evidence {
            section: if is_inside {
                "region_locals"
            } else {
                "captures"
            }
            .into(),
            edge: Edge {
                source: scope.into(),
                target: id.into(),
                kind: kind.into(),
                file: region.file.clone(),
                line: site["line"].as_u64().unwrap_or(0) as usize,
                offset: site["offset"].as_u64().unwrap_or(0) as usize,
                confidence: "resolved".into(),
            },
            reason: "compiler-bound AST identifier; alias/lifetime/type compatibility unverified"
                .into(),
            distance: 0,
            phase: "current".into(),
            also_sections: vec![],
        });
    }
    // A declaration can escape the region even without a use inside it.
    for (id, binding) in &bindings {
        if binding["offset"]
            .as_u64()
            .is_some_and(|o| o >= start && o < end)
            && after.contains(id)
        {
            outputs.insert(*id);
        }
    }
    let output_budget = budget.saturating_sub(uses.len().min(budget));
    if outputs.len() > output_budget {
        plan.exploration_limited = true;
    }
    for id in outputs.iter().take(output_budget) {
        let binding = bindings[id];
        plan.historical_symbols
            .insert((*id).into(), binding_node(binding, id, &region.file, scope));
        plan.evidence.push(Evidence {
            section:"region_outputs".into(),
            edge:Edge {
                source:scope.into(), target:(*id).into(), kind:"local_output".into(),
                file:region.file.clone(), line:binding["line"].as_u64().unwrap_or(0) as usize,
                offset:binding["offset"].as_u64().unwrap_or(0) as usize,
                confidence:"resolved".into(),
            },
            reason:"region local has a resolved use after selection; path/definite-assignment compatibility remains unverified".into(),
            distance:0, phase:"current".into(), also_sections:vec![],
        });
    }
    let dependencies: Vec<_> = record
        .edges
        .iter()
        .filter(|e| {
            e.offset as u64 >= start
                && (e.offset as u64) < end
                && ["calls", "references", "registers"].contains(&e.kind.as_str())
        })
        .collect();
    let dependency_budget = output_budget.saturating_sub(outputs.len());
    if dependencies.len() > dependency_budget {
        plan.exploration_limited = true;
    }
    for edge in dependencies.iter().take(dependency_budget) {
        plan.evidence.push(Evidence {
            section: "region_dependencies".into(),
            edge: (*edge).clone(),
            reason: "resolved semantic dependency inside AST selection".into(),
            distance: 0,
            phase: "current".into(),
            also_sections: vec![],
        });
    }
    let controls: Vec<_> = ast["controls"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|s| s["offset"].as_u64().is_some_and(|o| o >= start && o < end))
        .collect();
    let remaining = dependency_budget.saturating_sub(dependencies.len());
    if controls.len() > remaining {
        plan.exploration_limited = true;
    }
    for control in controls.iter().take(remaining) {
        let kind = control["kind"].as_str().unwrap_or("unknown");
        plan.evidence.push(Evidence {
            section: "control_exits".into(),
            edge: Edge {
                source: scope.into(),
                target: scope.into(),
                kind: format!("control_{kind}"),
                file: region.file.clone(),
                line: control["line"].as_u64().unwrap_or(0) as usize,
                offset: control["offset"].as_u64().unwrap_or(0) as usize,
                confidence: "resolved".into(),
            },
            reason: "AST control event; exception/async behavior requires compiler/manual review"
                .into(),
            distance: 0,
            phase: "current".into(),
            also_sections: vec![],
        });
    }
    plan.facts["ast_region"] = json!({"start_offset":start,"end_offset":end,"offset_unit":ast["offset_unit"],"scope":scope,"statements":sequence.len(),"exact_statement_boundaries":true});
    for (name, ids) in [
        ("capture_reads", read),
        ("external_mutations", writes),
        ("locals_used_after", outputs),
    ] {
        let total = ids.len();
        plan.facts[name] = json!({"ids":ids.into_iter().take(20).collect::<Vec<_>>(),"total":total,"omitted":total.saturating_sub(20),"expansion":"evidence pages and primitive snippet for region"});
    }
    plan.facts["control_exits"] =
        json!({"total": controls.len(), "expansion":"control_exits evidence section"});
    plan.facts["unresolved_local_bindings"] = json!(unresolved);
    plan.facts["provider_limits"] = ast["limitations"].clone();
    plan.outcome = "partial".into();
    plan.limits.push("AST capture/read-write/control facts are available; aliases, runtime callbacks, lifetimes, exception behavior and a hypothetical extracted signature remain unverified".into());
    if plan.exploration_limited {
        plan.limits.push("Local/control exploration exceeded max_traversal; raise budget and restart this intent".into());
    }
    Ok(())
}

fn binding_node(binding: &Value, id: &str, file: &str, scope: &str) -> Node {
    Node {
        id: id.into(),
        name: binding["name"].as_str().unwrap_or("unknown").into(),
        kind: binding["kind"].as_str().unwrap_or("local").into(),
        file: file.into(),
        line: binding["line"].as_u64().unwrap_or(0) as usize,
        qualified: id.into(),
        end: binding["end"].as_u64().unwrap_or(0) as usize,
        offset: binding["offset"].as_u64().unwrap_or(0) as usize,
        length: 0,
        parent: Some(scope.into()),
        tags: vec![],
        synthetic: false,
    }
}
