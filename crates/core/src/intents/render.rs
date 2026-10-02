use super::{Evidence, Plan};
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
fn windows(sites: &[usize]) -> Vec<(usize, usize)> {
    let mut sites = sites.to_vec();
    sites.sort();
    sites.dedup();
    let mut windows: Vec<(usize, usize)> = vec![];
    for line in sites {
        if line == 0 {
            continue;
        }
        let start = line.saturating_sub(2).max(1);
        let end = line + 2;
        if let Some(last) = windows.last_mut()
            && start <= last.1 + 1
        {
            last.1 = last.1.max(end);
            continue;
        }
        windows.push((start, end));
    }
    windows
}
struct SourceSlice {
    lines: BTreeMap<usize, String>,
    total: usize,
}
type Sources = BTreeMap<String, SourceSlice>;
fn read_sources(g: &Graph, c: &Config, evidence: &[Evidence]) -> Result<Sources> {
    let mut sites: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    for e in evidence {
        if e.phase == "current" && g.snapshot.files.contains_key(&e.edge.file) {
            sites
                .entry(e.edge.file.clone())
                .or_default()
                .push(e.edge.line);
        }
    }
    let mut sources = Sources::new();
    for (file, sites) in sites {
        let record = &g.snapshot.files[&file];
        let ranges = windows(&sites);
        let mut reader = BufReader::new(File::open(c.safe(&file)?)?);
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
                bail!("stale: source exceeded file budget")
            }
            digest.update(&raw);
            line += 1;
            if ranges
                .iter()
                .any(|(start, end)| line >= *start && line <= *end)
            {
                lines.insert(
                    line,
                    std::str::from_utf8(&raw)?.trim_end_matches('\n').to_owned(),
                );
            }
        }
        if format!("{:x}", digest.finalize()) != record.hash {
            bail!("stale: source hash differs from graph")
        }
        sources.insert(file, SourceSlice { lines, total: line });
    }
    Ok(sources)
}
fn snippets(c: &Config, file: &str, sites: &[usize], sources: &Sources) -> Value {
    let Some(source) = sources.get(file) else {
        return json!([]);
    };
    let mut used = 0;
    let results: Vec<_> = windows(sites).into_iter().map(|(start, desired)| {
        let end = desired.min(source.total).min(start + c.max_snippet_lines.saturating_sub(used).saturating_sub(1));
        let lines: Vec<_> = if used < c.max_snippet_lines { source.lines.range(start..=end.max(start)).map(|(_,s)|s.as_str()).collect() } else {vec![]};
        used += lines.len(); let text = lines.join("\n"); let truncated = end < desired || text.chars().count() > c.max_snippet_chars.min(2000) || lines.is_empty();
        let text: String = text.chars().take(c.max_snippet_chars.min(2000)).collect();
        json!({"start_line":start,"end_line":start+text.split('\n').count()-1,"text":text,"truncated":truncated,"requested_end_line":desired})
    }).collect();
    json!(results)
}
fn verify(g: &Graph, c: &Config, files: impl Iterator<Item = String>) -> Result<()> {
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
    for (file, records) in &groups {
        let sites: Vec<_> = records
            .iter()
            .filter(|e| e.phase == "current")
            .map(|e| e.edge.line)
            .collect();
        let snippet = if !sites.is_empty() && g.snapshot.files.contains_key(file) {
            snippets(c, file, &sites, sources)
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
                e.phase
            ])
        })
        .collect();
    let sections:BTreeMap<_,_>=counts.iter().map(|(name,count)| {
        let ids=sections.get(name).cloned().unwrap_or_default();let size=ids.len();
        (name,json!({"evidence":ids,"discovered_total":count,"total":if p.exploration_limited {Value::Null}else{json!(count)},"omitted":count-size,"truncated":size<*count,"depth_limited":p.depth_limited,"exploration_limited":p.exploration_limited,"expand_with":"next_cursor (same arguments)"}))
    }).collect();
    let diagnostic_total: usize = g.health.diagnostics.values().sum();
    let partial = g.health.issues(providers)
        || p.exploration_limited
        || p.depth_limited
        || offset + evidence.len() < p.evidence.len();
    let mut result = json!({"intent":p.request.intent,"target":p.target,"generation":g.snapshot.generation,"health_fingerprint":health,"freshness":freshness,"outcome":if p.outcome=="ok" && partial {"partial"} else {&p.outcome},"coverage":g.health.coverage,"provider_health":providers,"diagnostics":{"counts":g.health.diagnostics,"errors":g.health.errors.values().take(3).collect::<Vec<_>>(),"errors_omitted":g.health.errors.len().saturating_sub(3),"details_total":diagnostic_total,"details":"status(section: diagnostics)"},"budget":p.request.budget,"symbols":{"columns":["id","kind","name","file","line","phase","tags"],"rows":symbol_rows},"evidence":{"columns":["id","source","target","relation","site_file","site_line","offset","confidence","reason","distance","phase"],"rows":rows,"offset":offset,"discovered_total":p.evidence.len(),"total":if p.exploration_limited {Value::Null}else{json!(p.evidence.len())},"omitted":p.evidence.len()-evidence.len(),"truncated":evidence.len()<p.evidence.len(),"exploration_limited":p.exploration_limited,"depth_limited":p.depth_limited,"conservative":true},"rationales":rationales,"expansion_hints":{"snippets":"snippet(file, start_line, end_line)","cursor":"repeat identical intent arguments with next_cursor; restart if identities change"},"sections":sections,"files":file_groups,"facts":p.facts,"limits":p.limits,"next_cursor":if offset+evidence.len()<p.evidence.len(){json!("0".repeat(64))}else{Value::Null}});
    let details: BTreeMap<_, _> = evidence
        .iter()
        .filter_map(|e| p.details.get(&e.id()).map(|v| (e.id(), v)))
        .collect();
    if !details.is_empty() {
        result["details"] = json!(details);
    }
    Ok(result)
}
pub fn page(
    g: &Graph,
    c: &Config,
    p: &Plan,
    offset: usize,
    health: &str,
    providers: &Value,
    freshness: Value,
) -> Result<(Value, Option<usize>)> {
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
    let sources = read_sources(g, c, &p.evidence[offset..offset + count])?;
    loop {
        let slice = &p.evidence[offset..offset + count];
        let result = response(
            g,
            c,
            p,
            slice,
            offset,
            (health, providers, &freshness, &sources),
        )?;
        if chars(&result) <= p.request.budget.max_chars {
            verify(
                g,
                c,
                slice
                    .iter()
                    .filter(|e| e.phase == "current")
                    .map(|e| e.edge.file.clone())
                    .collect::<BTreeSet<_>>()
                    .into_iter(),
            )?;
            let next = offset + count;
            return Ok((result, (next < p.evidence.len()).then_some(next)));
        }
        if count <= 1 {
            bail!(
                "Intent record/metadata cannot fit max_chars; increase budget or use primitive details"
            )
        }
        count -= 1;
    }
}
