use super::{Evidence, Plan, View};
use crate::{config::Config, model::Node, query::Graph};
use anyhow::{Result, bail};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::{BufRead, BufReader, Read},
};

pub fn chars(v: &Value) -> usize {
    v.to_string().chars().count()
}
fn node<'a>(g: &'a Graph, p: &'a Plan, id: &str, phase: &str) -> Option<&'a Node> {
    if phase == "before" {
        p.historical_symbols
            .get(id)
            .or_else(|| g.context.node(g, id))
    } else {
        g.context
            .node(g, id)
            .or_else(|| p.historical_symbols.get(id))
    }
}
#[derive(Clone)]
struct Window {
    start: usize,
    end: usize,
    precision: &'static str,
}
fn selected_windows(g: &Graph, p: &Plan, evidence: &[Evidence], file: &str) -> Vec<Window> {
    let mut selected = vec![];
    for e in evidence
        .iter()
        .filter(|e| e.phase == "current" && e.edge.file == file)
    {
        let site = e.edge.line;
        let declaration = (e.edge.kind == "declaration")
            .then(|| node(g, p, &e.edge.target, "current"))
            .flatten();
        let window = match p.request.view {
            Some(View::Locations) => continue,
            None => Window {
                start: site.saturating_sub(2).max(1),
                end: site + 2,
                precision: "legacy_line_window",
            },
            Some(View::Contracts) if declaration.is_none() => continue,
            Some(View::Contracts) => {
                let n = declaration.expect("checked declaration");
                let first_body = g
                    .snapshot
                    .files
                    .get(file)
                    .and_then(|r| r.intent.ast["statements"].as_array())
                    .into_iter()
                    .flatten()
                    .filter(|s| s["scope"].as_str() == Some(&n.id))
                    .filter_map(|s| s["line"].as_u64())
                    .min();
                Window {
                    start: n.line,
                    end: first_body
                        .filter(|line| *line as usize > n.line)
                        .map_or(n.line, |line| line as usize - 1)
                        .min(n.line + 7),
                    precision: if first_body.is_some() {
                        "ast_header_lines"
                    } else {
                        "declaration_line_fallback"
                    },
                }
            }
            Some(View::EditContext | View::FullEvidence) => {
                if let Some(n) = declaration {
                    let primary = p.target["id"].as_str() == Some(&n.id)
                        || ["file_context", "changed_symbols", "added_symbols"]
                            .contains(&e.section.as_str());
                    if primary
                        && p.request.view == Some(View::EditContext)
                        && n.end.saturating_sub(n.line) > 80
                    {
                        let hunks: Vec<_> = p.facts["localization"]
                            .as_array()
                            .into_iter()
                            .flatten()
                            .filter(|v| v["file"] == file)
                            .flat_map(|v| v["hunks"].as_array().into_iter().flatten())
                            .filter_map(|h| {
                                Some((
                                    h["after_start"].as_u64()? as usize,
                                    h["after_end"].as_u64()? as usize,
                                ))
                            })
                            .filter(|(a, b)| *a >= n.line && *b <= n.end)
                            .collect();
                        if !hunks.is_empty() {
                            selected.push(Window {start:n.line,end:n.line,precision:"declaration_line_fallback; expand full_evidence for full scope"});
                            for (a, b) in hunks {
                                let statement = g.snapshot.files[file].intent.ast["statements"]
                                    .as_array()
                                    .into_iter()
                                    .flatten()
                                    .filter(|s| {
                                        s["scope"].as_str() == Some(&n.id)
                                            && s["line"].as_u64().is_some_and(|l| l as usize <= a)
                                            && s["end"].as_u64().is_some_and(|l| l as usize >= b)
                                    })
                                    .min_by_key(|s| {
                                        s["end"].as_u64().unwrap_or(0)
                                            - s["line"].as_u64().unwrap_or(0)
                                    });
                                selected.push(statement.map_or(Window{start:a,end:b,precision:"review_hunk_lines; statement boundary unavailable"},|s|Window{start:s["line"].as_u64().unwrap() as usize,end:s["end"].as_u64().unwrap() as usize,precision:"ast_statement_at_review_hunk"}));
                            }
                            continue;
                        }
                    }
                    Window {
                        start: n.line,
                        end: if primary || p.request.view == Some(View::FullEvidence) {
                            n.end
                        } else {
                            n.line
                        },
                        precision: "provider_declaration_range",
                    }
                } else if e.section == "source_changes" {
                    if p.request.lean() {
                        for h in p.facts["localization"]
                            .as_array()
                            .into_iter()
                            .flatten()
                            .filter(|v| v["file"] == file)
                            .flat_map(|v| v["hunks"].as_array().into_iter().flatten())
                        {
                            if let (Some(start), Some(end)) =
                                (h["after_start"].as_u64(), h["after_end"].as_u64())
                            {
                                selected.push(Window {start:start as usize,end:end as usize,precision:"review_hunk_lines; exact current source, not behavioral approval"});
                            }
                        }
                    }
                    // Actual hunks are represented separately; do not add a random file header.
                    continue;
                } else {
                    let stmt = g
                        .snapshot
                        .files
                        .get(file)
                        .and_then(|r| r.intent.ast["statements"].as_array())
                        .into_iter()
                        .flatten()
                        .filter(|s| {
                            s["scope"].as_str() == Some(&e.edge.source)
                                && s["line"].as_u64().is_some_and(|l| l as usize <= site)
                                && s["end"].as_u64().is_some_and(|l| l as usize >= site)
                        })
                        .min_by_key(|s| {
                            s["end"].as_u64().unwrap_or(0) - s["line"].as_u64().unwrap_or(0)
                        });
                    stmt.map_or(
                        Window {
                            start: site,
                            end: site,
                            precision: "site_line_fallback; expression boundary unavailable",
                        },
                        |s| Window {
                            start: s["line"].as_u64().unwrap_or(1) as usize,
                            end: s["end"].as_u64().unwrap_or(1) as usize,
                            precision: "ast_statement_lines",
                        },
                    )
                }
            }
        };
        if window.start > 0 {
            selected.push(window);
        }
    }
    selected.sort_by_key(|w| (w.start, w.end));
    let mut merged: Vec<Window> = vec![];
    for w in selected {
        if let Some(last) = merged.last_mut()
            && w.start <= last.end + 1
        {
            last.end = last.end.max(w.end);
            if last.precision != w.precision {
                last.precision = "merged_evidence_ranges";
            }
        } else {
            merged.push(w);
        }
    }
    merged
}
struct SourceSlice {
    lines: BTreeMap<usize, String>,
    total: usize,
}
type Sources = BTreeMap<String, SourceSlice>;
fn read_sources(
    g: &Graph,
    c: &Config,
    p: &Plan,
    evidence: &[Evidence],
    metrics: &mut super::Metrics,
) -> Result<Sources> {
    let files: BTreeSet<_> = evidence
        .iter()
        .filter(|e| e.phase == "current" && g.snapshot.files.contains_key(&e.edge.file))
        .map(|e| &e.edge.file)
        .collect();
    let mut sources = Sources::new();
    for file in files {
        let ranges = selected_windows(g, p, evidence, file);
        if ranges.is_empty() {
            continue;
        }
        let record = &g.snapshot.files[file];
        let mut reader = BufReader::new(File::open(c.safe(file)?)?);
        let mut digest = Sha256::new();
        let mut raw = vec![];
        let mut bytes = 0;
        let mut line = 0;
        let mut lines = BTreeMap::new();
        loop {
            raw.clear();
            let n = reader
                .by_ref()
                .take((c.max_file_bytes.saturating_sub(bytes) + 1) as u64)
                .read_until(b'\n', &mut raw)?;
            if n == 0 {
                break;
            }
            bytes += n;
            if bytes > c.max_file_bytes {
                bail!("stale: source exceeded file budget");
            }
            digest.update(&raw);
            line += 1;
            if ranges.iter().any(|w| {
                line >= w.start
                    && line <= w.end.min(w.start + c.max_snippet_lines.saturating_sub(1))
            }) {
                lines.insert(
                    line,
                    std::str::from_utf8(&raw)?.trim_end_matches('\n').to_owned(),
                );
            }
        }
        metrics.source_files_hashed += 1;
        metrics.source_bytes_hashed += bytes as u64;
        if format!("{:x}", digest.finalize()) != record.hash {
            bail!("stale: source hash differs from graph");
        }
        sources.insert(file.clone(), SourceSlice { lines, total: line });
    }
    Ok(sources)
}
fn snippets(
    g: &Graph,
    c: &Config,
    p: &Plan,
    file: &str,
    evidence: &[Evidence],
    sources: &Sources,
    source_remaining: &mut usize,
) -> Value {
    let Some(source) = sources.get(file) else {
        return json!([]);
    };
    let mut used = 0;
    let mut output = vec![];
    for w in selected_windows(g, p, evidence, file) {
        let desired = w.end.min(source.total);
        let end = desired.min(w.start + c.max_snippet_lines.saturating_sub(used).saturating_sub(1));
        let lines: Vec<_> = if used < c.max_snippet_lines {
            source
                .lines
                .range(w.start..=end.max(w.start))
                .map(|(_, s)| s.as_str())
                .collect()
        } else {
            vec![]
        };
        used += lines.len();
        let text = lines.join("\n");
        let limit = c
            .max_snippet_chars
            .min(if p.request.view.is_none() {
                2000
            } else {
                c.max_snippet_chars
            })
            .min(*source_remaining);
        let truncated = end < desired || text.chars().count() > limit || lines.is_empty();
        let text: String = text.chars().take(limit).collect();
        *source_remaining = source_remaining.saturating_sub(text.chars().count());
        let mut value = json!({"start_line":w.start,"end_line":w.start+text.split('\n').count()-1,"text":text,"truncated":truncated,"requested_end_line":w.end});
        if p.request.view.is_some() {
            value["precision"] = json!(w.precision);
        }
        output.push(value);
    }
    json!(output)
}
fn verify(
    g: &Graph,
    c: &Config,
    files: impl Iterator<Item = String>,
    metrics: &mut super::Metrics,
) -> Result<()> {
    for file in files {
        let Some(record) = g.snapshot.files.get(&file) else {
            continue;
        };
        let mut f = File::open(c.safe(&file)?)?;
        let mut h = Sha256::new();
        let mut buf = [0; 16384];
        let mut total = 0;
        loop {
            let n = f.read(&mut buf)?;
            if n == 0 {
                break;
            }
            total += n;
            if total > c.max_file_bytes {
                bail!("stale: changed source size")
            }
            h.update(&buf[..n]);
        }
        metrics.source_files_hashed += 1;
        metrics.source_bytes_hashed += total as u64;
        if format!("{:x}", h.finalize()) != record.hash {
            bail!("stale: source changed during context assembly")
        }
    }
    Ok(())
}
fn response(
    g: &Graph,
    c: &Config,
    p: &Plan,
    evidence: &[Evidence],
    offset: usize,
    identity: (&str, &Value, &Value, &Sources),
    source_limit: usize,
) -> Result<Value> {
    let (health, providers, freshness, sources) = identity;
    let mut symbols = BTreeMap::new();
    for e in evidence {
        for id in [&e.edge.source, &e.edge.target] {
            if let Some(n) = node(g, p, id, &e.phase) {
                symbols.insert((e.phase.clone(), id.clone()), n);
            }
        }
    }
    let lookup: BTreeMap<_, _> = symbols
        .keys()
        .enumerate()
        .map(|(i, id)| (id.clone(), i))
        .collect();
    let symbol_rows: Vec<_> = symbols
        .iter()
        .map(|((phase, _), n)| json!([n.id, n.kind, n.name, n.file, n.line, phase, n.tags]))
        .collect();
    let mut groups: BTreeMap<String, Vec<&Evidence>> = BTreeMap::new();
    let mut sections: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut counts = BTreeMap::<String, usize>::new();
    for e in &p.evidence {
        for section in std::iter::once(&e.section).chain(&e.also_sections) {
            *counts.entry(section.clone()).or_default() += 1;
        }
    }
    for e in evidence {
        groups.entry(e.edge.file.clone()).or_default().push(e);
        for section in std::iter::once(&e.section).chain(&e.also_sections) {
            sections.entry(section.clone()).or_default().push(e.id());
        }
    }
    let mut file_groups = vec![];
    let mut source_remaining = source_limit;
    for (file, records) in &groups {
        let sites: Vec<_> = records
            .iter()
            .filter(|e| e.phase == "current")
            .map(|e| e.edge.line)
            .collect();
        let snippet = if !sites.is_empty() && g.snapshot.files.contains_key(file) {
            snippets(g, c, p, file, evidence, sources, &mut source_remaining)
        } else {
            json!([])
        };
        file_groups.push(json!({"file":file,"evidence":records.iter().map(|e|e.id()).collect::<Vec<_>>(),"snippets":snippet}));
    }
    let file_lookup: BTreeMap<_, _> = groups
        .keys()
        .enumerate()
        .map(|(i, file)| (file.clone(), i))
        .collect();
    let rationales: Vec<_> = evidence
        .iter()
        .map(|e| e.reason.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let rows: Vec<_> = evidence
        .iter()
        .map(|e| {
            json!([
                e.id(),
                lookup.get(&(e.phase.clone(), e.edge.source.clone())),
                lookup.get(&(e.phase.clone(), e.edge.target.clone())),
                e.edge.kind,
                file_lookup[&e.edge.file],
                e.edge.line,
                e.edge.offset,
                e.edge.confidence,
                rationales.iter().position(|reason| reason == &e.reason),
                e.distance,
                e.phase,
                if e.required(&p.request) {
                    "required"
                } else {
                    "optional"
                }
            ])
        })
        .collect();
    let sections:BTreeMap<_,_>=counts.iter().map(|(name,count)| {
        let ids=sections.get(name).cloned().unwrap_or_default();let size=ids.len();
        (name,json!({"evidence":ids,"discovered_total":count,"total":if p.exploration_limited {Value::Null}else{json!(count)},"omitted":count-size,"truncated":size<*count,"page_count":size,"remaining_after_page":p.evidence.iter().skip(offset+evidence.len()).filter(|e| &e.section==name || e.also_sections.contains(name)).count(),"depth_limited":p.depth_limited,"exploration_limited":p.exploration_limited,"expand_with":"next_cursor (same arguments)"}))
    }).collect();
    let diagnostic_total: usize = g.health.diagnostics.values().sum();
    let partial = g.health.issues(providers)
        || p.exploration_limited
        || p.depth_limited
        || offset + evidence.len() < p.evidence.len();
    let mut result = json!({"intent":p.request.intent,"target":p.target,"generation":g.snapshot.generation,"health_fingerprint":health,"freshness":freshness,"outcome":if p.outcome=="ok" && partial {"partial"} else {&p.outcome},"coverage":g.health.coverage,"provider_health":providers,"diagnostics":{"counts":g.health.diagnostics,"errors":g.health.errors.values().take(3).collect::<Vec<_>>(),"errors_omitted":g.health.errors.len().saturating_sub(3),"details_total":diagnostic_total,"details":"status(section: diagnostics)"},"budget":p.request.budget,"symbols":{"columns":["id","kind","name","file","line","phase","tags"],"rows":symbol_rows},"evidence":{"columns":["id","source","target","relation","site_file","site_line","offset","confidence","reason","distance","phase","requirement"],"rows":rows,"offset":offset,"discovered_total":p.evidence.len(),"total":if p.exploration_limited {Value::Null}else{json!(p.evidence.len())},"page_count":evidence.len(),"remaining_after_page":p.evidence.len().saturating_sub(offset+evidence.len()),"collection_complete":offset+evidence.len()==p.evidence.len() && !p.exploration_limited && !p.depth_limited,"exploration_incomplete":p.exploration_limited || p.depth_limited,"omitted":p.evidence.len()-evidence.len(),"truncated":evidence.len()<p.evidence.len(),"exploration_limited":p.exploration_limited,"depth_limited":p.depth_limited,"conservative":true},"rationales":rationales,"expansion_hints":{"snippets":"snippet(file, start_line, end_line)","cursor":"repeat identical intent arguments with next_cursor; restart if identities change"},"sections":sections,"files":file_groups,"facts":p.facts,"limits":p.limits,"next_cursor":if offset+evidence.len()<p.evidence.len(){json!("0".repeat(64))}else{Value::Null}});
    let details: BTreeMap<_, _> = evidence
        .iter()
        .filter_map(|e| p.details.get(&e.id()).map(|v| (e.id(), v)))
        .collect();
    if !details.is_empty() {
        result["details"] = json!(details);
    }
    let source_incomplete = file_groups_incomplete(&result["files"]);
    result["source_windows_incomplete"] = json!(source_incomplete);
    if p.request.source_policy.is_some() || p.request.budget.max_source_chars.is_some() {
        result["source_selection"] = json!({"policy":p.request.source_policy,"view":p.request.view,"max_source_chars":p.request.budget.max_source_chars,"emitted_source_chars":source_limit-source_remaining,"scope":"source text only; required inventory and metadata remain subject to max_chars","explicit_view_overrides_policy":true});
    }
    let mut causes = vec![];
    if p.exploration_limited {
        causes.push("traversal_budget");
    }
    if p.depth_limited {
        causes.push("depth");
    }
    if offset + evidence.len() < p.evidence.len() {
        causes.push("response_page");
    }
    if source_incomplete {
        causes.push("source_window");
    }
    result["limit_causes"] = json!(causes);
    if p.request.view.is_some() {
        result["view"] = json!(p.request.view);
    }
    if p.request.budget.max_collection_items.is_some_and(|cap| {
        offset + evidence.len() >= cap && offset + evidence.len() < p.evidence.len()
    }) {
        result["next_cursor"] = Value::Null;
        result["limit_causes"]
            .as_array_mut()
            .expect("causes")
            .push(json!("collection_budget"));
        result["expansion_hints"]["collection"] = json!(
            "start a new request with a larger max_collection_items; cursors bind every budget"
        );
    }
    result["requirements"] = json!({"required_total":p.evidence.iter().filter(|e|e.required(&p.request)).count(),"optional_total":p.evidence.iter().filter(|e|!e.required(&p.request)).count(),"page_required":evidence.iter().filter(|e|e.required(&p.request)).count()});
    if p.request.lean() {
        return Ok(super::lean::project(g, c, p, evidence, offset, &result));
    }
    if p.request.context.is_some()
        || p.request
            .view
            .is_some_and(|v| v != super::input::View::Locations)
    {
        acknowledge(g, c, p, health, &mut result)?;
    }
    if p.request.budget.max_tokens.is_some() {
        result["token_budget"] = json!({"method":"unicode_chars_div4_v1","kind":"estimate","scope":"entire compact JSON result; excludes client/schema/model usage","estimated_tokens":0});
        for _ in 0..4 {
            result["token_budget"]["estimated_tokens"] = json!(chars(&result).div_ceil(4));
        }
    }
    Ok(result)
}
pub fn fits(p: &Plan, result: &Value) -> bool {
    chars(result) <= p.request.budget.max_chars
        && p.request
            .budget
            .max_tokens
            .is_none_or(|limit| chars(result).div_ceil(4) <= limit)
}
fn acknowledge(g: &Graph, c: &Config, p: &Plan, health: &str, result: &mut Value) -> Result<()> {
    let root_id = crate::model::hash(c.root.to_string_lossy().as_bytes());
    let ctx = p.request.context.as_ref();
    let valid = ctx.is_some_and(|v| {
        v.root_id == root_id
            && v.generation == g.snapshot.generation
            && v.health_fingerprint == health
            && v.environment_fingerprint == g.snapshot.environment
    });
    let rehydrate = ctx.is_some_and(|v| v.rehydrate);
    let mut repeated = 0;
    for file in result["files"].as_array_mut().expect("file groups") {
        let name = file["file"].as_str().unwrap_or("").to_owned();
        let Some(record) = g.snapshot.files.get(&name) else {
            continue;
        };
        file["source_hash"] = json!(record.hash);
        for window in file["snippets"].as_array_mut().expect("windows") {
            let id = crate::model::hash(serde_json::to_vec(&json!([
                root_id,
                g.snapshot.generation,
                health,
                g.snapshot.environment,
                g.snapshot.files[&name].hash,
                p.request.view,
                window
            ]))?);
            window["window_id"] = json!(id);
            if valid && !rehydrate && ctx.is_some_and(|v| v.known_windows.contains(&id)) {
                window.as_object_mut().expect("window").remove("text");
                window["acknowledged"] = json!(true);
                repeated += 1;
            }
        }
    }
    result["context"] = json!({"epoch":ctx.map(|v|&v.epoch),"root_id":root_id,"generation":g.snapshot.generation,"health_fingerprint":health,"environment_fingerprint":g.snapshot.environment,"acknowledgement_valid":valid,"reset_required":ctx.is_some() && !valid,"rehydrate":rehydrate,"suppressed_windows":repeated,"retention":"acknowledge only windows actually retained; reset epoch/known_windows after compaction"});
    Ok(())
}
fn file_groups_incomplete(files: &Value) -> bool {
    files.as_array().into_iter().flatten().any(|f| {
        f["snippets"]
            .as_array()
            .into_iter()
            .flatten()
            .any(|s| s["truncated"] == true)
    })
}
pub fn page(
    g: &Graph,
    c: &Config,
    p: &Plan,
    offset: usize,
    identity: (&str, &Value, Value),
    metrics: &mut super::Metrics,
) -> Result<(Value, Option<usize>)> {
    let (health, providers, freshness) = identity;
    if offset > p.evidence.len() {
        bail!("Invalid cursor offset")
    }
    let mut count = 0;
    let mut files = BTreeSet::new();
    for e in p
        .evidence
        .iter()
        .skip(offset)
        .take(p.request.budget.max_items.min(c.max_results))
    {
        files.insert(e.edge.file.clone());
        if files.len() > p.request.budget.max_files {
            break;
        }
        count += 1;
    }
    let cap = p.request.budget.max_collection_items.unwrap_or(usize::MAX);
    count = count.min(cap.saturating_sub(offset));
    let sources = read_sources(g, c, p, &p.evidence[offset..offset + count], metrics)?;
    let mut source_limit = p.request.budget.max_source_chars.unwrap_or(usize::MAX);
    loop {
        let slice = &p.evidence[offset..offset + count];
        let result = response(
            g,
            c,
            p,
            slice,
            offset,
            (health, providers, &freshness, &sources),
            source_limit,
        )?;
        if fits(p, &result) {
            verify(
                g,
                c,
                slice
                    .iter()
                    .filter(|e| e.phase == "current")
                    .map(|e| e.edge.file.clone())
                    .collect::<BTreeSet<_>>()
                    .into_iter(),
                metrics,
            )?;
            let next = offset + count;
            return Ok((
                result,
                (next < p.evidence.len() && next < cap).then_some(next),
            ));
        }
        // With an explicit source budget, shrink optional text before reducing
        // the inventory page. Every omitted slice remains visibly truncated.
        if p.request.budget.max_source_chars.is_some() && source_limit > 0 {
            source_limit /= 2;
            continue;
        }
        if count <= 1 {
            bail!(
                "Intent record/metadata cannot fit the response budget (max_chars/max_tokens) at this offset; start a new request with view=locations or a larger max_chars/max_tokens budget; retrieve source via snippet and diagnostics via status. No cursor was advanced"
            )
        }
        count -= 1;
    }
}
