use super::{Baseline, Evidence, Options, Plan, Request, input::Review};
use crate::{
    config::Config,
    model::{Edge, Node, compare_text, language},
    query::Graph,
};
use anyhow::{Result, bail};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

pub fn path(c: &Config, file: &str) -> Result<()> {
    if file.is_empty()
        || file.starts_with('/')
        || file.contains('\\')
        || file.contains(':')
        || file.split('/').any(|p| p == ".." || p == ".")
    {
        bail!("Paths must be relative to graph root, without traversal")
    }
    c.safe(file)?;
    Ok(())
}
fn in_scope(file: &str, scope: &str) -> bool {
    let scope = scope.trim_end_matches('/');
    file == scope
        || file
            .strip_prefix(scope)
            .is_some_and(|tail| tail.starts_with('/'))
}
pub fn review_files(g: &Graph, c: &Config, r: &Request, v: &Review) -> Result<Vec<String>> {
    let mut files = if v.files.is_empty() {
        vec![r.target.split("::").next().unwrap_or("").to_owned()]
    } else {
        v.files.clone()
    };
    files.sort();
    files.dedup();
    for file in &v.new_files {
        path(c, file)?;
        if !files.contains(file) || c.safe(file)?.exists() {
            bail!("new_files must be exact absent files in the requested review scope: {file}")
        }
    }
    for file in &files {
        path(c, file)?;
        if v.strict_scope && !g.snapshot.files.contains_key(file) {
            if c.safe(file)?.exists() {
                bail!(
                    "review scope {file}: existing file is outside the indexed scope; not a future creation"
                )
            }
            if v.baseline.is_none() && !(v.capture_baseline && v.new_files.contains(file)) {
                let candidates: Vec<_> = g
                    .snapshot
                    .files
                    .keys()
                    .filter(|candidate| {
                        candidate.ends_with(&format!("/{file}"))
                            || candidate.rsplit('/').next() == file.rsplit('/').next()
                    })
                    .take(3)
                    .collect();
                bail!(
                    "review scope {file}: not indexed and not explicitly declared in new_files; root-relative candidates: {}",
                    serde_json::to_string(&candidates)?
                )
            }
        }
        if v.baseline.is_none()
            && !g.snapshot.files.contains_key(file)
            && !(v.capture_baseline && !c.safe(file)?.exists())
        {
            bail!("Baseline capture/current review requires indexed file: {file}")
        }
    }
    Ok(files)
}
fn declaration(n: &Node, section: &str) -> Evidence {
    Evidence {
        section: section.into(),
        edge: Edge {
            source: n.id.clone(),
            target: n.id.clone(),
            kind: "declaration".into(),
            file: n.file.clone(),
            line: n.line,
            offset: n.offset,
            confidence: "resolved".into(),
        },
        reason: "indexed_declaration; range is not an editable token span".into(),
        distance: 0,
        phase: "current".into(),
        also_sections: vec![],
    }
}
fn fact(e: &Edge, section: &str, reason: &str, distance: usize) -> Evidence {
    Evidence {
        section: section.into(),
        edge: e.clone(),
        reason: reason.into(),
        distance,
        phase: "current".into(),
        also_sections: vec![],
    }
}
struct Planner<'a> {
    g: &'a Graph,
    plan: Plan,
    work: usize,
    optional_tests: BTreeSet<String>,
}
impl Planner<'_> {
    fn spend(&mut self) -> bool {
        if self.work >= self.plan.request.budget.max_traversal {
            self.plan.exploration_limited = true;
            false
        } else {
            self.work += 1;
            true
        }
    }
    fn edges(&mut self, id: &str, incoming: bool, kinds: &[&str]) -> Vec<Edge> {
        let edges = self.g.context.edges(self.g, id, incoming, kinds);
        let remaining = self
            .plan
            .request
            .budget
            .max_traversal
            .saturating_sub(self.work);
        let mut selected: Vec<_> = edges.take(remaining + 1).cloned().collect();
        if selected.len() > remaining {
            selected.pop();
            self.plan.exploration_limited = true;
        }
        self.work += selected.len();
        selected
    }
    fn add(&mut self, e: Evidence) {
        self.plan.evidence.push(e);
    }
    fn declare(&mut self, id: &str, section: &str) {
        if let Some(n) = self.g.context.node(self.g, id) {
            self.add(declaration(n, section));
        }
    }
    fn incoming(&mut self, id: &str, kinds: &[&str], section: &str) {
        for e in self.edges(id, true, kinds) {
            if kinds.contains(&e.kind.as_str()) {
                self.add(fact(&e, section, "resolved_static_site", 1));
            }
        }
    }
    fn contracts(&mut self, start: &str) -> BTreeSet<String> {
        let mut found = BTreeSet::from([start.to_owned()]);
        let mut queue = VecDeque::from([(start.to_owned(), 0usize)]);
        while let Some((id, depth)) = queue.pop_front() {
            for incoming in [true, false] {
                for e in self.edges(
                    &id,
                    incoming,
                    &[
                        "overrides",
                        "binds_field",
                        "accessor_pair",
                        "super_parameter",
                    ],
                ) {
                    if ![
                        "overrides",
                        "binds_field",
                        "accessor_pair",
                        "super_parameter",
                    ]
                    .contains(&e.kind.as_str())
                    {
                        continue;
                    }
                    self.add(fact(
                        &e,
                        "contracts",
                        "compiler_resolved_symbol_link",
                        depth + 1,
                    ));
                    let next = if incoming {
                        e.source.clone()
                    } else {
                        e.target.clone()
                    };
                    if found.contains(&next) {
                        continue;
                    }
                    if depth >= self.plan.request.depth {
                        self.plan.depth_limited = true;
                        continue;
                    }
                    found.insert(next.clone());
                    self.declare(&next, "declarations");
                    queue.push_back((next, depth + 1));
                }
            }
        }
        found
    }
    fn walk(
        &mut self,
        start: &str,
        incoming: bool,
        section: &str,
        destination: Option<&str>,
    ) -> BTreeSet<String> {
        if let Some(destination) = destination {
            return self.path_to(start, destination, incoming, section);
        }
        let mut found = BTreeSet::from([start.to_owned()]);
        let mut queue = VecDeque::from([(start.to_owned(), 0usize)]);
        while let Some((id, depth)) = queue.pop_front() {
            if destination == Some(id.as_str()) {
                continue;
            }
            // Calls retain their direction. Override links are dispatch alternatives
            // in either direction, never evidence that an implementation ran.
            for direction in [incoming, !incoming] {
                for e in self.edges(
                    &id,
                    direction,
                    if direction == incoming {
                        &["calls", "overrides"]
                    } else {
                        &["overrides"]
                    },
                ) {
                    if e.kind != "overrides" && !(direction == incoming && e.kind == "calls") {
                        continue;
                    }
                    if depth >= self.plan.request.depth {
                        self.plan.depth_limited = true;
                        continue;
                    }
                    self.add(fact(
                        &e,
                        section,
                        if e.kind == "calls" {
                            "static_call; runtime order unknown"
                        } else {
                            "possible_dispatch; not proven runtime call"
                        },
                        depth + 1,
                    ));
                    let next = if direction {
                        e.source.clone()
                    } else {
                        e.target.clone()
                    };
                    if found.insert(next.clone()) {
                        queue.push_back((next, depth + 1));
                    }
                }
            }
        }
        found
    }
    fn path_to(
        &mut self,
        start: &str,
        destination: &str,
        incoming: bool,
        section: &str,
    ) -> BTreeSet<String> {
        let mut seen = BTreeSet::from([start.to_owned()]);
        let mut parents: BTreeMap<String, (String, Edge, usize)> = BTreeMap::new();
        let mut queue = VecDeque::from([(start.to_owned(), 0usize)]);
        'search: while let Some((id, depth)) = queue.pop_front() {
            if id == destination {
                break;
            }
            for direction in [incoming, !incoming] {
                for e in self.edges(
                    &id,
                    direction,
                    if direction == incoming {
                        &["calls", "overrides"]
                    } else {
                        &["overrides"]
                    },
                ) {
                    if depth >= self.plan.request.depth {
                        self.plan.depth_limited = true;
                        continue;
                    }
                    let next = if direction {
                        e.source.clone()
                    } else {
                        e.target.clone()
                    };
                    if seen.insert(next.clone()) {
                        parents.insert(next.clone(), (id.clone(), e, depth + 1));
                        if next == destination {
                            break 'search;
                        }
                        queue.push_back((next, depth + 1));
                    }
                }
            }
        }
        self.plan.facts["path_selection"] = json!(
            "one shortest static path within depth/work bounds; optional alternatives via trace without destination"
        );
        let mut path = BTreeSet::from([start.to_owned()]);
        if seen.contains(destination) {
            let mut cursor = destination.to_owned();
            path.insert(cursor.clone());
            while cursor != start {
                let Some((parent, e, distance)) = parents.get(&cursor) else {
                    break;
                };
                self.add(fact(
                    e,
                    section,
                    if e.kind == "calls" {
                        "directed static path; runtime order unknown"
                    } else {
                        "possible override dispatch; not proven runtime call"
                    },
                    *distance,
                ));
                path.insert(parent.clone());
                cursor = parent.clone();
            }
        }
        path
    }
    fn explain_dependencies(&mut self, id: &str) {
        for e in self.edges(
            id,
            false,
            &["calls", "references", "extends", "implements", "with", "on"],
        ) {
            if ["calls", "references", "extends", "implements", "with", "on"]
                .contains(&e.kind.as_str())
            {
                self.add(fact(
                    &e,
                    "dependencies",
                    "resolved direct dependency; role tags are hints",
                    1,
                ));
            }
        }
    }
    fn explain_implementations(&mut self, id: &str) {
        for e in self.edges(id, true, &["overrides", "implements", "extends", "with"]) {
            if ["overrides", "implements", "extends", "with"].contains(&e.kind.as_str()) {
                self.add(fact(
                    &e,
                    "implementations",
                    "resolved implementation/subtype; runtime selection unknown",
                    1,
                ));
            }
        }
    }
    fn directives(&mut self, file: &str, include_imports: bool) {
        let id = format!("{file}::file");
        for incoming in [true, false] {
            for e in self.edges(
                &id,
                incoming,
                if include_imports {
                    &["imports", "exports", "part", "part_of"]
                } else {
                    &["exports", "part", "part_of"]
                },
            ) {
                if (["exports", "part", "part_of"].contains(&e.kind.as_str()))
                    || (include_imports && e.kind == "imports")
                {
                    self.add(fact(
                        &e,
                        "module_context",
                        "file-level directive; not an obligatory symbol edit",
                        1,
                    ));
                }
            }
        }
    }
    fn tests(&mut self, start: &str, scope: Option<&str>, framework: Option<&str>) {
        if self.plan.request.lean() && self.plan.request.intent != super::Intent::FindTests {
            if matches!(&self.plan.request.options, Options::Signature(v) if v.include_tests) {
                self.optional_tests.insert(start.into());
            }
            return;
        }
        self.collect_tests(start, scope, framework);
    }
    fn collect_tests(&mut self, start: &str, scope: Option<&str>, framework: Option<&str>) {
        let mut found = BTreeSet::from([start.to_owned()]);
        let mut queue = VecDeque::from([(start.to_owned(), 0usize)]);
        while let Some((id, depth)) = queue.pop_front() {
            for e in self.edges(&id, true, &["references", "calls", "overrides"]) {
                if !["references", "calls", "overrides"].contains(&e.kind.as_str()) {
                    continue;
                }
                if depth >= self.plan.request.depth {
                    self.plan.depth_limited = true;
                    continue;
                }
                let is_case = self.g.snapshot.files.get(&e.file).and_then(|r| {
                    r.intent.tests.iter().find(|case| {
                        case["line"]
                            .as_u64()
                            .is_some_and(|line| line as usize <= e.line)
                            && case["end"]
                                .as_u64()
                                .is_some_and(|end| e.line <= end as usize)
                            && framework.is_none_or(|f| case["framework"].as_str() == Some(f))
                    })
                });
                let test_file = e
                    .file
                    .split('/')
                    .any(|p| ["test", "tests", "integration_test", "__tests__"].contains(&p))
                    || e.file.contains("_test.")
                    || e.file.contains(".test.")
                    || e.file.contains(".spec.")
                    || e.file.ends_with("Test.java")
                    || e.file.ends_with("Test.kt");
                if scope.is_none_or(|prefix| in_scope(&e.file, prefix)) {
                    if let Some(case) = is_case {
                        self.add(fact(&e,"tests",&format!("resolved test case {}: {}; static reference does not prove execution/assertion",case["framework"],case["name"]),depth+1));
                    } else if test_file && framework.is_none() {
                        self.add(fact(&e,"test_candidates","heuristic test-file classification with resolved graph link; runner/assertions unknown",depth+1));
                    }
                }
                if found.insert(e.source.clone()) {
                    queue.push_back((e.source, depth + 1));
                }
            }
        }
        self.plan.facts["test_runner"] = json!("unknown; consult project configuration");
        let warning = "Zero test results do not prove absence of coverage; imports alone are not test evidence";
        if !self.plan.limits.iter().any(|s| s == warning) {
            self.plan.limits.push(warning.into());
        }
    }
}
pub fn build(g: &Graph, c: &Config, r: Request, baseline: Option<&Baseline>) -> Result<Plan> {
    let mut plan=Plan {request:r,target:Value::Null,historical_symbols:BTreeMap::new(),details:BTreeMap::new(),evidence:vec![],facts:json!({}),limits:vec!["Static semantic evidence only; dynamic calls, callbacks, reflection, external consumers and cross-language flow may be incomplete".into()],outcome:"ok".into(),exploration_limited:false,depth_limited:false,optional_limited:false};
    if let Options::Review(v) = plan.request.options.clone() {
        return review(g, c, plan, v, baseline);
    }
    // Path-like targets are validated even when resolution would otherwise return not_found.
    if plan.request.target.contains('/')
        || plan.request.target.contains('\\')
        || plan.request.target.contains(':')
    {
        path(c, plan.request.target.split("::").next().unwrap_or(""))?;
    }
    let i = match g.resolve(&plan.request.target) {
        Ok(i) => i,
        Err(e) if e.to_string().starts_with("Symbol or file not found") => {
            plan.outcome = "not_found".into();
            plan.target = json!({"query":plan.request.target});
            plan.limits.push(
                "not_found_in_indexed_scope; use search_symbol with indexed root-relative prefixes"
                    .into(),
            );
            return Ok(plan);
        }
        Err(e) => return Err(e),
    };
    let n = &g.nodes[i];
    let id = n.id.clone();
    let file = n.file.clone();
    plan.target = n.compact();
    plan.facts = json!({"language":language(&file),"scope":"indexed_repository","capability_version":1,"exact_edit_spans":false,"hypothetical_type_check":"unknown"});
    let mut p = Planner {
        g,
        plan,
        work: 0,
        optional_tests: BTreeSet::new(),
    };
    p.declare(&id, "declarations");
    match p.plan.request.options.clone() {
        Options::Rename(v) => {
            if let Some(scope) = &v.scope {
                path(c, scope)?;
                if !g.snapshot.files.keys().any(|f| in_scope(f, scope)) || !in_scope(&file, scope) {
                    bail!("Rename scope must be an indexed root-relative prefix containing target")
                }
                p.plan.facts["edit_scope"] = json!(scope);
            }
            let linked = p.contracts(&id);
            for symbol in &linked {
                p.incoming(
                    symbol,
                    &["references", "calls", "parameter_reference"],
                    "usages",
                );
            }
            p.directives(&file, false);
            if let Some(scope) = &v.scope {
                for e in &mut p.plan.evidence {
                    if !in_scope(&e.edge.file, scope) && e.section == "usages" {
                        e.section = "out_of_edit_scope".into();
                        e.reason =
                            "resolved consumer outside proposed edit scope; must still be reviewed"
                                .into();
                    }
                }
            }
            let homonyms = g
                .named(&n.name)
                .filter(|other| other.id != id && !linked.contains(&other.id))
                .count();
            p.plan.facts["unlinked_homonyms_excluded"] = json!(homonyms);
            if let Some(new) = v.new_name {
                // Same-name members are candidates, never compiler-proven collisions.
                let total_candidates = g
                    .named(&new)
                    .filter(|other| other.parent == n.parent && other.id != id)
                    .count();
                let candidates: Vec<_> = g
                    .named(&new)
                    .filter(|other| other.parent == n.parent && other.id != id)
                    .take(20)
                    .map(Node::compact)
                    .collect();
                p.plan.facts["new_name"] = json!(new);
                p.plan.facts["conflict_candidates"] = json!(candidates);
                p.plan.facts["conflict_candidates_total"] = json!(total_candidates);
                p.plan.facts["conflict_candidates_omitted"] =
                    json!(total_candidates.saturating_sub(20));
                p.plan.facts["conflict_check"] =
                    json!("heuristic member candidates; compiler verification required");
            }
            if v.include_impact {
                p.walk(&id, true, "impact", None);
            }
            let binding = g.snapshot.files.get(&file).is_some_and(|r| {
                r.intent
                    .capabilities
                    .iter()
                    .any(|s| s == "parameter_bindings")
            });
            if !binding
                && [
                    "field",
                    "getter",
                    "setter",
                    "constructor",
                    "method",
                    "function",
                ]
                .contains(&n.kind.as_str())
            {
                p.plan.outcome = "partial".into();
                p.plan.limits.push("Provider does not expose intent parameter/field/accessor links; inspect declarations and constructor/argument labels manually".into());
            }
            p.plan.limits.push("Serialization keys, strings and generated code require review; no global text replacement or editable spans are proposed".into());
        }
        Options::Signature(v) => {
            let linked = p.contracts(&id);
            for symbol in &linked {
                p.incoming(symbol, &["calls", "references"], "callers");
            }
            if !p.plan.request.lean()
                && (v.return_type.is_some()
                    || v.asynchronous.is_some()
                    || !v.removed_parameters.is_empty()
                    || !v.renamed_parameters.is_empty()
                    || (v.added_parameters.is_empty() && v.required.is_none()))
            {
                p.walk(&id, true, "forwarding_context", None);
            } else {
                p.plan.facts["optional_expansions"] =
                    json!(["trace_flow direction=in for transitive forwarding"]);
            }
            p.tests(&id, None, None);
            for e in p.edges(&id, false, &["contains"]) {
                if e.kind == "contains" {
                    p.add(fact(&e, "contract", "indexed_member", 0));
                }
            }
            p.plan.facts["requested_change"] = json!(v);
            p.plan.facts["compatibility"] =
                json!("conditional; hypothetical compiler type-check unavailable");
            p.plan.outcome = "partial".into();
            p.plan.limits.push("Forwarding/callback behavior and required/default/overload compatibility are not verified by graph traversal".into());
        }
        Options::Tests(v) => {
            if let Some(scope) = &v.test_scope {
                path(c, scope)?;
                if !g.snapshot.files.keys().any(|f| in_scope(f, scope)) {
                    bail!("test_scope is not indexed")
                }
            }
            p.tests(&id, v.test_scope.as_deref(), v.framework.as_deref());
            p.plan.outcome = "partial".into();
        }
        Options::Explain(v) => {
            let focus = v.focus.as_deref().unwrap_or("contract");
            p.plan.facts["focus"] = json!(focus);
            p.plan.facts["ranking"] = json!(
                "declaration first, selected focus next, then distance and file/line/offset; bounded static evidence"
            );
            if let Some(parent) = &n.parent {
                p.declare(parent, "container");
            }
            if v.focus.is_some() {
                match focus {
                    "dependencies" => p.explain_dependencies(&id),
                    "implementation" => {
                        p.explain_implementations(&id);
                        p.contracts(&id);
                    }
                    _ => {
                        p.contracts(&id);
                        p.incoming(&id, &["calls", "references"], "consumers");
                    }
                }
                p.plan.facts["optional_expansions"] = json!([
                    "explain_symbol focus=contract",
                    "explain_symbol focus=implementation",
                    "explain_symbol focus=dependencies"
                ]);
            } else {
                p.contracts(&id);
                p.explain_implementations(&id);
                p.explain_dependencies(&id);
                p.incoming(&id, &["calls", "references"], "consumers");
            }
        }
        Options::Flow(v) => {
            let destination = v
                .destination
                .as_deref()
                .map(|s| g.resolve(s).map(|i| g.nodes[i].id.clone()))
                .transpose()?;
            let reached = p.walk(
                &id,
                v.direction.as_deref() == Some("in"),
                "flow",
                destination.as_deref(),
            );
            let frontier_files: BTreeSet<_> = reached
                .iter()
                .filter_map(|id| g.context.node(g, id))
                .map(|n| &n.file)
                .collect();
            let frontiers: Vec<_> = frontier_files
                .into_iter()
                .filter_map(|file| {
                    g.snapshot
                        .files
                        .get(file)
                        .filter(|r| r.unresolved_calls > 0)
                        .map(|r| json!({"file":file,"unresolved_calls_in_file":r.unresolved_calls}))
                })
                .collect();
            p.plan.facts["unresolved_frontiers"] = json!({"files":frontiers.iter().take(3).collect::<Vec<_>>(),"omitted":frontiers.len().saturating_sub(3),"precision":"file-level provider counts, not proven reachable call sites; unresolved callbacks/FFI are not invented as edges"});
            p.plan.facts["destination"] = json!(destination);
            p.plan.facts["destination_found"] =
                json!(destination.as_ref().map(|d| reached.contains(d)));
            p.plan.facts["flow_kind"] =
                json!("bounded static call graph, not value dataflow/runtime ordering");
            if destination.is_some_and(|d| !reached.contains(&d)) {
                p.plan.outcome = "partial".into();
                p.plan.limits.push(
                    "not_found_in_indexed_scope; no path is not proof of impossibility".into(),
                );
            }
        }
        Options::Move(v) => {
            path(c, &v.destination)?;
            p.incoming(&id, &["references", "calls"], "consumers");
            p.contracts(&id);
            p.directives(&file, true);
            p.plan.facts["destination"] = json!({"file":v.destination,"indexed":g.snapshot.files.contains_key(&v.destination),"visibility_and_build_compatibility":"unknown"});
            p.plan.outcome = "partial".into();
            p.plan.limits.push("Moving across modules, private visibility, assets and generated/build paths require compiler/manual checks; no files are written".into());
        }
        Options::Remove(v) => {
            let mut group = BTreeSet::from([id.clone()]);
            for target in v.group {
                group.insert(g.nodes[g.resolve(&target)?].id.clone());
            }
            for symbol in &group {
                p.incoming(
                    symbol,
                    &["calls", "references", "overrides", "registers"],
                    "consumers",
                );
                let linked = p.contracts(symbol);
                for link in linked {
                    p.incoming(
                        &link,
                        &["references", "parameter_reference", "calls"],
                        "consumers",
                    );
                }
            }
            for e in &mut p.plan.evidence {
                if group.contains(&e.edge.source) && e.section == "consumers" {
                    e.section = "internal_group".into();
                }
            }
            p.directives(&file, true);
            p.tests(&id, None, None);
            p.plan.facts["safe_to_delete"] =
                json!("unknown; zero static usages does not prove dead code");
        }
        Options::Replace(v) => {
            p.incoming(
                &id,
                &["calls", "references", "registers", "implements", "extends"],
                "composition",
            );
            p.contracts(&id);
            p.tests(&id, None, None);
            if let Some(replacement) = v.replacement {
                let other = &g.nodes[g.resolve(&replacement)?];
                p.declare(&other.id, "replacement");
                p.plan.facts["replacement"] = other.compact();
            }
            p.plan.outcome = "partial".into();
            p.plan.limits.push("DI patterns beyond resolved registers/construction, ownership, lifecycle and semantic contract equivalence are unverified".into());
        }
        Options::Extract(v) => {
            path(c, &v.file)?;
            let record = g
                .snapshot
                .files
                .get(&v.file)
                .ok_or_else(|| anyhow::anyhow!("Extraction file is not indexed"))?;
            if file != v.file {
                bail!("Extraction target must belong to region file")
            }
            if v.end_line
                > record
                    .nodes
                    .iter()
                    .filter(|n| n.kind == "file")
                    .map(|n| n.end)
                    .max()
                    .unwrap_or(0)
            {
                bail!("Extraction range outside indexed file")
            }
            p.plan.facts["region"] = json!(v);
            p.plan.facts["suggested_signature"] = Value::Null;
            super::extraction::prepare(g, &mut p.plan, &v)?;
        }
        Options::Review(_) => unreachable!("handled before resolution"),
    }
    finish(p)
}
fn finish(mut p: Planner<'_>) -> Result<Plan> {
    let primary_limits = (p.plan.exploration_limited, p.plan.depth_limited);
    if !p.optional_tests.is_empty() {
        p.plan.exploration_limited = false;
        p.plan.depth_limited = false;
        for id in std::mem::take(&mut p.optional_tests) {
            p.collect_tests(&id, None, None);
        }
        p.plan.optional_limited = p.plan.exploration_limited || p.plan.depth_limited;
        (p.plan.exploration_limited, p.plan.depth_limited) = primary_limits;
    }
    // Exact messages include their scope/parameters; preserve first occurrence order.
    let mut limits = BTreeSet::new();
    p.plan.limits.retain(|limit| limits.insert(limit.clone()));
    p.plan.facts["candidate_records"] = json!(p.plan.evidence.len());
    let mut unique: BTreeMap<(String, String), Evidence> = BTreeMap::new();
    for mut e in p.plan.evidence.drain(..) {
        if e.edge.confidence != "resolved" {
            e.also_sections.push(e.section.clone());
            e.section = "candidates".into();
            e.reason = format!("provider confidence {}: {}", e.edge.confidence, e.reason);
        }
        let key = (e.phase.clone(), serde_json::to_string(&e.edge)?);
        if let Some(previous) = unique.get_mut(&key) {
            if previous.section != e.section && !previous.also_sections.contains(&e.section) {
                previous.also_sections.push(e.section);
                if !previous.reason.contains(&e.reason) {
                    previous.reason.push_str("; ");
                    previous.reason.push_str(&e.reason);
                }
            }
        } else {
            unique.insert(key, e);
        }
    }
    p.plan.evidence = unique.into_values().collect();
    let focus = match &p.plan.request.options {
        Options::Explain(v) => v.focus.as_deref().unwrap_or("contract"),
        _ => "",
    };
    let priority = |section: &str| {
        if section == "declarations" {
            return 0;
        }
        if (focus == "dependencies" && section == "dependencies")
            || (focus == "implementation" && ["implementations", "contracts"].contains(&section))
            || (focus == "contract" && ["contracts", "container"].contains(&section))
        {
            1
        } else if !focus.is_empty() {
            rank(section) + 2
        } else {
            rank(section)
        }
    };
    p.plan.evidence.sort_by(|a, b| {
        (p.plan.request.lean() && !a.required(&p.plan.request))
            .cmp(&(p.plan.request.lean() && !b.required(&p.plan.request)))
            .then_with(|| {
                priority(&a.section)
                    .cmp(&priority(&b.section))
                    .then(a.distance.cmp(&b.distance))
                    .then_with(|| compare_text(&a.edge.file, &b.edge.file))
                    .then(a.edge.line.cmp(&b.edge.line))
                    .then(a.edge.offset.cmp(&b.edge.offset))
                    .then_with(|| compare_text(&a.edge.key(), &b.edge.key()))
            })
    });
    if (p.plan.exploration_limited || p.plan.depth_limited) && p.plan.outcome == "ok" {
        p.plan.outcome = "partial".into();
    }
    p.plan.facts["traversal_steps"] = json!(p.work);
    Ok(p.plan)
}
fn rank(s: &str) -> usize {
    match s {
        "declarations" => 0,
        "contracts" | "contract" => 1,
        "usages" | "callers" | "composition" => 2,
        "flow" => 3,
        "tests" => 4,
        "test_candidates" => 8,
        "module_context" => 9,
        _ => 5,
    }
}
fn review(
    g: &Graph,
    c: &Config,
    mut plan: Plan,
    v: Review,
    baseline: Option<&Baseline>,
) -> Result<Plan> {
    let files = review_files(g, c, &plan.request, &v)?;
    plan.target = json!({"files":files});
    plan.facts["files"] = json!(files);
    let mut p = Planner {
        g,
        plan,
        work: 0,
        optional_tests: BTreeSet::new(),
    };
    let Some(old) = baseline else {
        p.plan.outcome = "partial".into();
        p.plan.facts["comparison_verified"] = json!(false);
        p.plan.limits.push(if v.capture_baseline {"Baseline captured before edit; this is current-state context, not a verified diff"} else {"No explicit baseline: current-state context only; detect_changes does not constitute a Git/semantic diff"}.into());
        if v.capture_mode.as_deref() == Some("minimal") {
            return finish(p);
        }
        for file in &files {
            for node in g
                .snapshot
                .files
                .get(file)
                .into_iter()
                .flat_map(|r| &r.nodes)
            {
                if !p.spend() {
                    break;
                }
                if node.kind != "file" {
                    p.declare(&node.id, "declarations");
                }
            }
        }
        return finish(p);
    };
    p.plan.facts["baseline_generation"] = json!(old.snapshot.generation);
    p.plan.facts["baseline_health_fingerprint"] = json!(old.health);
    p.plan.facts["comparison_verified"] = json!(true);
    p.plan.facts["verification_status"] = json!("compiler/tests not executed");
    p.plan.facts["comparison_kind"] = json!(
        "captured working-tree source ranges and indexed semantic evidence; no Git history or correctness approval"
    );
    p.plan.facts["localization"] = json!([]);
    p.plan.facts["relation_changes"] = json!([]);
    if old.snapshot.environment != g.snapshot.environment
        || old.snapshot.fingerprint != g.snapshot.fingerprint
    {
        p.plan.outcome = "partial".into();
        p.plan.limits.push(
            "Provider environment/configuration changed between baseline and current snapshot"
                .into(),
        );
    }
    let mut diagnostic_changes = vec![];
    let historical: BTreeMap<_, _> = old
        .snapshot
        .files
        .values()
        .flat_map(|r| &r.nodes)
        .map(|n| (&n.id, n))
        .collect();
    for file in &files {
        let before = old.snapshot.files.get(file);
        let after = g.snapshot.files.get(file);
        let source_changed = before.map(|r| &r.hash) != after.map(|r| &r.hash);
        if source_changed && p.spend() {
            let id = format!("{file}::file");
            let kind = if before.is_none() {
                "source_added"
            } else if after.is_none() {
                "source_removed"
            } else {
                "source_changed"
            };
            let phase = if after.is_some() { "current" } else { "before" };
            if phase == "before"
                && let Some(n) = historical.get(&id)
            {
                p.plan.historical_symbols.insert(id.clone(), (*n).clone());
            }
            let event = Evidence {section:"source_changes".into(), edge:Edge {source:id.clone(),target:id,kind:kind.into(),file:file.clone(),line:1,offset:0,confidence:"resolved".into()},reason:"observed source hash change; file context does not identify changed statements or prove behavior".into(),distance:0,phase:phase.into(),also_sections:vec![]};
            p.plan.details.insert(
                event.id(),
                json!({"before_hash":before.map(|r| &r.hash),"after_hash":after.map(|r| &r.hash)}),
            );
            p.add(event);
            p.plan.outcome = "partial".into();
        }
        let a: BTreeMap<_, _> = before
            .into_iter()
            .flat_map(|r| &r.nodes)
            .map(|n| (n.id.clone(), n))
            .collect();
        let b: BTreeMap<_, _> = after
            .into_iter()
            .flat_map(|r| &r.nodes)
            .map(|n| (n.id.clone(), n))
            .collect();
        for (id, node) in &a {
            if !p.spend() {
                break;
            }
            if !b.contains_key(id) {
                let mut e = declaration(node, "removed_symbols");
                e.phase = "before".into();
                p.plan
                    .historical_symbols
                    .insert(id.clone(), (*node).clone());
                p.add(e);
                // Historical consumers outside comparison scope are context, not diffs.
                for edge in old.snapshot.files.values().flat_map(|r| &r.edges) {
                    if !p.spend() {
                        break;
                    }
                    if &edge.target != id
                        || !["calls", "references", "overrides"].contains(&edge.kind.as_str())
                    {
                        continue;
                    }
                    let mut e = fact(
                        edge,
                        "affected_consumers",
                        "resolved historical consumer of removed declaration; related file is not in comparison scope",
                        1,
                    );
                    e.phase = "before".into();
                    for target in [&e.edge.source, &e.edge.target] {
                        if let Some(n) = historical.get(target) {
                            p.plan
                                .historical_symbols
                                .insert(target.clone(), (*n).clone());
                        }
                    }
                    p.add(e);
                }
            }
        }
        let localization = if source_changed {
            super::review::localize(
                c,
                file,
                old.sources.get(file).map(String::as_str),
                after,
                p.plan.request.budget.max_traversal.saturating_sub(p.work),
            )?
        } else {
            super::review::Localization::default()
        };
        p.work += localization.work;
        if localization.fallback.is_some() {
            p.plan.limits.push(format!(
                "Review file fallback for {file}: {}",
                localization.fallback.as_deref().unwrap_or("unknown")
            ));
        }
        if source_changed {
            p.plan.facts["localization"].as_array_mut().expect("localizations").push(json!({"file":file,"hunks":localization.hunks,"kind":localization.kind,"fallback":localization.fallback,"seeds":localization.seeds}));
        }
        let current_source = after
            .map(|r| super::review::read(c, file, &r.hash))
            .transpose()?;
        let before_lines: Vec<_> = old
            .sources
            .get(file)
            .map_or("", String::as_str)
            .split('\n')
            .collect();
        let inert_prefix = old
            .sources
            .get(file)
            .zip(current_source.as_ref())
            .is_some_and(|(before, after)| super::review::inert_leading_edit(file, before, after));
        let current_lines: Vec<_> = current_source
            .as_deref()
            .unwrap_or("")
            .split('\n')
            .collect();
        for (id, node) in &b {
            if !p.spend() {
                break;
            }
            let declaration_changed = a
                .get(id)
                .is_none_or(|old| !super::review::same_declaration(old, node));
            let (unchanged_source, work) =
                if inert_prefix && localization.fallback.is_some() && node.kind != "file" {
                    super::review::unchanged_declaration_source(
                        &before_lines,
                        a.get(id),
                        &current_lines,
                        node,
                        p.plan.request.budget.max_traversal.saturating_sub(p.work),
                    )
                } else {
                    (false, 0)
                };
            p.work += work;
            let selected = localization.seeds.contains(id)
                || (localization.fallback.is_some() && !unchanged_source);
            if node.kind != "file" && (declaration_changed || selected) {
                p.declare(
                    id,
                    if !declaration_changed {
                        "file_context"
                    } else if a.contains_key(id) {
                        "changed_symbols"
                    } else {
                        "added_symbols"
                    },
                );
                if declaration_changed
                    || localization.kind != "body"
                    || localization.fallback.is_some()
                {
                    let linked = p.contracts(id);
                    for link in linked {
                        p.incoming(
                            &link,
                            &["calls", "references", "overrides"],
                            "affected_consumers",
                        );
                    }
                } else {
                    p.explain_dependencies(id);
                }
                p.tests(id, None, None);
            }
        }
        let comparison = super::review::relations(
            file,
            before,
            after,
            old.sources.get(file).map(String::as_str),
            current_source.as_deref(),
            p.plan.request.budget.max_traversal.saturating_sub(p.work),
        );
        p.work += comparison.work;
        if let Some(limit) = comparison.limit {
            p.plan
                .limits
                .push(format!("Relation mapping for {file}: {limit}"));
            if limit.contains("budget") {
                p.plan.exploration_limited = true;
            }
        }
        if comparison.uncertain > 0 {
            p.plan.limits.push(format!("Uncertain site correspondence in {file}: conservative before/after evidence retained; no arbitrary pairing"));
        }
        p.plan.facts["relation_changes"].as_array_mut().expect("relation summaries").push(json!({"file":file,"unchanged":comparison.unchanged,"relocated":comparison.relocated,"uncertain_mapping":comparison.uncertain,"removed_multiplicity":comparison.removed_multiplicity,"added_multiplicity":comparison.added_multiplicity,"mapping_limit":comparison.limit}));
        for delta in comparison.deltas {
            use super::review::RelationKind;
            if delta.kind == RelationKind::Unchanged {
                continue;
            }
            if delta.kind == RelationKind::Relocated {
                if p.plan.request.view == Some(super::View::FullEvidence) {
                    let e = fact(
                        delta.after.expect("relocated current site"),
                        "relocated_relations",
                        "unchanged semantic attributes; exact source interval moved",
                        0,
                    );
                    p.plan.details.insert(e.id(), json!({"classification":delta.kind,"before":delta.before,"after":delta.after}));
                    p.add(e);
                }
                continue;
            }
            if let Some(e) = delta.before {
                let mut e = fact(
                    e,
                    "removed_relations",
                    if delta.kind == RelationKind::UncertainMapping {
                        "uncertain_mapping: baseline site retained without a proven counterpart"
                    } else {
                        "observed baseline relation; no rename/move correspondence assumed"
                    },
                    0,
                );
                e.phase = "before".into();
                for id in [&e.edge.source, &e.edge.target] {
                    if let Some(n) = historical.get(id) {
                        p.plan.historical_symbols.insert(id.clone(), (*n).clone());
                    }
                }
                p.plan.details.insert(
                    e.id(),
                    json!({"classification":delta.kind,"before":delta.before,"after":delta.after}),
                );
                p.add(e);
            }
            if let Some(e) = delta.after {
                p.add(fact(e, "added_relations", "observed current relation", 0));
            }
        }
        let a: BTreeSet<_> = before
            .into_iter()
            .flat_map(|r| &r.diagnostics)
            .map(Value::to_string)
            .collect();
        let b: BTreeSet<_> = after
            .into_iter()
            .flat_map(|r| &r.diagnostics)
            .map(Value::to_string)
            .collect();
        for (kind, changes) in [
            ("new", b.difference(&a).collect::<Vec<_>>()),
            ("resolved", a.difference(&b).collect()),
        ] {
            for d in changes {
                if !p.spend() {
                    break;
                }
                let diagnostic: Value = serde_json::from_str(d)?;
                let id = format!(
                    "{file}::diagnostic_{}#diagnostic",
                    &crate::model::hash(d.as_bytes())[..16]
                );
                let line = diagnostic["line"].as_u64().unwrap_or(1).max(1) as usize;
                let node = Node {
                    id: id.clone(),
                    name: diagnostic["code"].as_str().unwrap_or("diagnostic").into(),
                    kind: "diagnostic".into(),
                    file: file.clone(),
                    line,
                    qualified: id.clone(),
                    end: line,
                    offset: 0,
                    length: 0,
                    parent: Some(format!("{file}::file")),
                    tags: vec![],
                    synthetic: true,
                };
                p.plan.historical_symbols.insert(id.clone(), node);
                if kind == "resolved"
                    && let Some(node) = historical.get(&format!("{file}::file"))
                {
                    p.plan
                        .historical_symbols
                        .insert(node.id.clone(), (*node).clone());
                }
                let event = Evidence {section:"diagnostic_changes".into(),edge:Edge {source:format!("{file}::file"),target:id,kind:format!("diagnostic_{kind}"),file:file.clone(),line,offset:0,confidence:"resolved".into()},reason:"observed provider diagnostic change; full payload in details; offset is unavailable".into(),distance:0,phase:if kind=="new" {"current"}else{"before"}.into(),also_sections:vec![]};
                p.plan.details.insert(event.id(), diagnostic);
                p.add(event);
                diagnostic_changes.push(json!({"file":file,"change":kind,"diagnostic":serde_json::from_str::<Value>(d)?}));
            }
        }
    }
    let count = diagnostic_changes.len();
    for diagnostic in &mut diagnostic_changes {
        if let Some(message) = diagnostic["diagnostic"]["message"].as_str()
            && message.chars().count() > 240
        {
            diagnostic["diagnostic"]["message"] =
                json!(message.chars().take(240).collect::<String>());
            diagnostic["message_truncated"] = json!(true);
        }
    }
    p.plan.facts["diagnostic_changes"] =
        json!(diagnostic_changes.into_iter().take(3).collect::<Vec<_>>());
    p.plan.facts["diagnostic_changes_total"] = json!(count);
    p.plan.facts["diagnostic_changes_omitted"] = json!(count.saturating_sub(3));
    p.plan.facts["diagnostic_expansion"] = json!(
        "diagnostic_changes evidence pages; full original records keyed by evidence ID in details (including baseline-resolved diagnostics)"
    );
    p.plan.limits.push("Renamed/moved IDs remain added/removed; no guessed identity correspondence or automatic correctness approval".into());
    finish(p)
}
