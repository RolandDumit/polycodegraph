//! Intent-only planning; primitive graph APIs and resolver identities stay unchanged.
mod extraction;
mod input;
mod lean;
mod planner;
mod render;
mod review;
mod site_map;
use crate::{
    config::Config,
    model::{Edge, Node, Snapshot, hash},
    query::Graph,
};
use anyhow::{Result, bail};
pub use input::{Budget, Format, Intent, Options, Request, View};
pub(crate) use planner::path as validate_path;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashMap},
    sync::Arc,
    time::{Duration, Instant},
};

#[derive(Default)]
pub struct ContextIndex {
    pub nodes: BTreeMap<String, Node>,
    pub edges: Vec<Edge>,
    incoming: HashMap<String, BTreeMap<String, Vec<usize>>>,
    outgoing: HashMap<String, BTreeMap<String, Vec<usize>>>,
}
impl ContextIndex {
    pub fn new(snapshot: &Snapshot) -> Self {
        let mut this = Self::default();
        let mut edges = BTreeMap::new();
        for record in snapshot.files.values() {
            for node in &record.intent.symbols {
                this.nodes.insert(node.id.clone(), node.clone());
            }
            for edge in &record.intent.relations {
                edges.insert(
                    serde_json::to_string(edge).expect("edge serialization"),
                    edge.clone(),
                );
            }
        }
        this.edges = edges.into_values().collect();
        for (i, e) in this.edges.iter().enumerate() {
            this.incoming
                .entry(e.target.clone())
                .or_default()
                .entry(e.kind.clone())
                .or_default()
                .push(i);
            this.outgoing
                .entry(e.source.clone())
                .or_default()
                .entry(e.kind.clone())
                .or_default()
                .push(i);
        }
        this
    }
    pub fn node<'a>(&'a self, g: &'a Graph, id: &str) -> Option<&'a Node> {
        g.ids
            .get(id)
            .map(|i| &g.nodes[*i])
            .or_else(|| self.nodes.get(id))
    }
    pub fn edges<'a>(
        &'a self,
        g: &'a Graph,
        id: &str,
        incoming: bool,
        kinds: &'a [&'a str],
    ) -> impl Iterator<Item = &'a Edge> {
        let primary = g.ids.get(id).and_then(|i| {
            if incoming {
                g.incoming_kinds.get(i)
            } else {
                g.outgoing_kinds.get(i)
            }
        });
        let auxiliary = if incoming {
            self.incoming.get(id)
        } else {
            self.outgoing.get(id)
        };
        kinds
            .iter()
            .flat_map(move |kind| {
                primary
                    .into_iter()
                    .filter_map(move |m| m.get(*kind))
                    .flatten()
                    .map(|i| &g.edges[*i])
            })
            .chain(kinds.iter().flat_map(move |kind| {
                auxiliary
                    .into_iter()
                    .filter_map(move |m| m.get(*kind))
                    .flatten()
                    .map(|i| &self.edges[*i])
            }))
    }
}
#[derive(Clone, serde::Serialize)]
pub(super) struct Evidence {
    pub section: String,
    pub edge: Edge,
    pub reason: String,
    pub distance: usize,
    pub phase: String,
    pub also_sections: Vec<String>,
}
impl Evidence {
    fn required(&self, request: &Request) -> bool {
        if request.lean()
            && (self.section == "relocated_relations"
                || (request.intent != Intent::FindTests && self.section == "tests"))
        {
            return false;
        }
        if let Options::Explain(v) = &request.options
            && let Some(focus) = v.focus.as_deref()
            && ((focus == "dependencies" && self.section == "dependencies")
                || (focus == "implementation"
                    && ["implementations", "contracts"].contains(&self.section.as_str()))
                || (focus == "contract"
                    && ["container", "contracts"].contains(&self.section.as_str())))
        {
            return true;
        }
        ![
            "container",
            "dependencies",
            "consumers",
            "forwarding_context",
            "impact",
            "test_candidates",
            "module_context",
            "candidates",
        ]
        .contains(&self.section.as_str())
            || self.also_sections.iter().any(|s| {
                [
                    "usages",
                    "contracts",
                    "callers",
                    "flow",
                    "diagnostic_changes",
                ]
                .contains(&s.as_str())
            })
    }
    fn id(&self) -> String {
        hash(serde_json::to_vec(&(&self.phase, &self.edge)).expect("edge serialization"))[..16]
            .into()
    }
}
#[derive(serde::Serialize)]
pub(super) struct Plan {
    pub request: Request,
    pub target: Value,
    pub historical_symbols: BTreeMap<String, Node>,
    pub details: BTreeMap<String, Value>,
    pub evidence: Vec<Evidence>,
    pub facts: Value,
    pub limits: Vec<String>,
    pub outcome: String,
    pub exploration_limited: bool,
    pub depth_limited: bool,
    pub optional_limited: bool,
}
struct Cursor {
    request: String,
    root: String,
    generation: String,
    health: String,
    plan: Arc<Plan>,
    offset: usize,
    created: Instant,
    bytes: usize,
}
pub struct Baseline {
    pub root: String,
    pub snapshot: Arc<Snapshot>,
    pub files: Vec<String>,
    pub health: String,
    pub strict_scope: bool,
    pub sources: BTreeMap<String, String>,
    pub created: Instant,
    bytes: usize,
}
#[derive(Default, serde::Serialize)]
pub struct Metrics {
    pub plan_calls: u64,
    pub render_calls: u64,
    pub intent_plan_ms: f64,
    pub intent_render_ms: f64,
    pub candidate_records: u64,
    pub selected_records: u64,
    pub required_records: u64,
    pub optional_records: u64,
    pub source_files_hashed: u64,
    pub source_bytes_hashed: u64,
}
#[derive(Default)]
pub struct State {
    pub metrics: Metrics,
    cursors: BTreeMap<String, Cursor>,
    baselines: BTreeMap<String, Baseline>,
}
fn token() -> Result<String> {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes)
        .map_err(|e| anyhow::anyhow!("Cannot create context handle: {e}"))?;
    Ok(hash(bytes))
}
impl State {
    fn prune(&mut self) {
        self.cursors
            .retain(|_, v| v.created.elapsed() < Duration::from_secs(300));
        self.baselines
            .retain(|_, v| v.created.elapsed() < Duration::from_secs(600));
    }
    pub fn prepare(
        &mut self,
        g: &Graph,
        c: &Config,
        args: &Value,
        freshness: Value,
    ) -> Result<Value> {
        let request = Request::parse(args)?;
        self.prune();
        let providers = g.health.provider_health(c);
        let health = g.health.fingerprint(&providers);
        let signature = hash(serde_json::to_vec(&request)?);
        let root = c.root.to_string_lossy();
        let (plan, offset) = if let Some(cursor) = args.get("cursor") {
            let key = cursor
                .as_str()
                .ok_or_else(|| anyhow::anyhow!("cursor must be a string"))?;
            let Some(ticket) = self.cursors.get(key) else {
                return restart(
                    &request,
                    g,
                    &health,
                    &providers,
                    freshness,
                    "cursor missing, expired, evicted or belongs to another session/root",
                );
            };
            if ticket.request != signature || ticket.root != root {
                bail!("Cursor does not match intent, arguments, budget or root")
            }
            if ticket.generation != g.snapshot.generation || ticket.health != health {
                return restart(
                    &request,
                    g,
                    &health,
                    &providers,
                    freshness,
                    "generation or health changed",
                );
            }
            if let Options::Review(v) = &request.options
                && let Some(key) = &v.baseline
                && !self.baselines.contains_key(key)
            {
                return restart(
                    &request,
                    g,
                    &health,
                    &providers,
                    freshness,
                    "baseline expired or evicted",
                );
            }
            (ticket.plan.clone(), ticket.offset)
        } else {
            let mut baseline = None;
            let mut baseline_info = Value::Null;
            if let Options::Review(v) = &request.options {
                let files = planner::review_files(g, c, &request, v)?;
                if v.capture_baseline {
                    // Retain only explicitly selected sources and records, never implicit HEAD.
                    let (snapshot, sources, bytes) = review::capture(g, c, &files)?;
                    self.metrics.source_files_hashed += sources.len() as u64 * 2;
                    self.metrics.source_bytes_hashed +=
                        sources.values().map(|s| s.len() as u64).sum::<u64>() * 2;
                    if bytes > 128 * 1024 * 1024 {
                        bail!("Snapshot exceeds 128 MiB baseline capacity")
                    }
                    while self.baselines.len() >= 2
                        || self.baselines.values().map(|v| v.bytes).sum::<usize>() + bytes
                            > 128 * 1024 * 1024
                    {
                        self.evict_baseline();
                    }
                    let key = token()?;
                    self.baselines.insert(
                        key.clone(),
                        Baseline {
                            root: root.to_string(),
                            snapshot,
                            sources,
                            files: files.clone(),
                            health: health.clone(),
                            strict_scope: v.strict_scope,
                            created: Instant::now(),
                            bytes,
                        },
                    );
                    baseline_info = json!({"handle":key,"generation":g.snapshot.generation,"health_fingerprint":health,"expires_after_seconds":600,"retained_bytes":bytes,"capacity":2,"session_only":true,"files":files,"capture_mode":v.capture_mode.as_deref().unwrap_or("context"),"existing_files_captured":files.iter().filter(|f|g.snapshot.files.contains_key(*f)).count(),"new_files_admitted":v.new_files.len(),"strict_scope":v.strict_scope});
                } else if let Some(key) = &v.baseline {
                    let Some(old) = self.baselines.get(key) else {
                        return restart(
                            &request,
                            g,
                            &health,
                            &providers,
                            freshness,
                            "baseline missing, expired, evicted or belongs to another session/root",
                        );
                    };
                    if old.root != root {
                        bail!("Baseline belongs to another root");
                    }
                    if old.files != files {
                        bail!(
                            "Baseline file scope does not match; capture a baseline with exactly these files"
                        )
                    }
                    if old.strict_scope != v.strict_scope {
                        bail!("Baseline strict_scope does not match the captured contract")
                    }
                    baseline = Some(old);
                }
            }
            let started = Instant::now();
            let planned = planner::build(g, c, request, baseline);
            self.metrics.intent_plan_ms += started.elapsed().as_secs_f64() * 1000.;
            self.metrics.plan_calls += 1;
            let mut plan = planned?;
            self.metrics.candidate_records += plan.facts["candidate_records"].as_u64().unwrap_or(0);
            if !baseline_info.is_null() {
                plan.facts["baseline"] = baseline_info;
            }
            (Arc::new(plan), 0)
        };
        let started = Instant::now();
        let page = render::page(
            g,
            c,
            &plan,
            offset,
            (&health, &providers, freshness.clone()),
            &mut self.metrics,
        );
        self.metrics.intent_render_ms += started.elapsed().as_secs_f64() * 1000.;
        self.metrics.render_calls += 1;
        match page {
            Ok((mut result, next)) => {
                self.metrics.selected_records += result["evidence"]["page_count"]
                    .as_u64()
                    .unwrap_or_else(|| result["page"]["records"].as_u64().unwrap_or(0));
                let required = result["requirements"]["page_required"]
                    .as_u64()
                    .unwrap_or_else(|| result["page"]["required"].as_u64().unwrap_or(0));
                self.metrics.required_records += required;
                self.metrics.optional_records += result["evidence"]["page_count"]
                    .as_u64()
                    .unwrap_or_else(|| result["page"]["records"].as_u64().unwrap_or(0))
                    .saturating_sub(required);
                if let Some(offset) = next {
                    let bytes = serde_json::to_vec(plan.as_ref())?.len();
                    if bytes > 64 * 1024 * 1024 {
                        bail!("Intent plan exceeds cursor memory capacity")
                    }
                    while self.cursors.len() >= 16
                        || self.cursors.values().map(|v| v.bytes).sum::<usize>() + bytes
                            > 64 * 1024 * 1024
                    {
                        self.evict_cursor();
                    }
                    let key = token()?;
                    self.cursors.insert(
                        key.clone(),
                        Cursor {
                            request: signature,
                            root: root.into_owned(),
                            generation: g.snapshot.generation.clone(),
                            health: health.clone(),
                            plan: plan.clone(),
                            offset,
                            created: Instant::now(),
                            bytes,
                        },
                    );
                    result["next_cursor"] = json!(key);
                }
                if !render::fits(&plan, &result) {
                    bail!("Mandatory intent metadata exceeds budget; increase max_chars")
                }
                Ok(result)
            }
            Err(e) if e.to_string().starts_with("stale:") => restart(
                &plan.request,
                g,
                &health,
                &providers,
                freshness,
                "source changed during snippet read; retry after reconciliation",
            ),
            Err(e) => Err(e),
        }
    }
    fn evict_cursor(&mut self) {
        if let Some(k) = self
            .cursors
            .iter()
            .min_by_key(|(_, v)| v.created)
            .map(|(k, _)| k.clone())
        {
            self.cursors.remove(&k);
        }
    }
    fn evict_baseline(&mut self) {
        if let Some(k) = self
            .baselines
            .iter()
            .min_by_key(|(_, v)| v.created)
            .map(|(k, _)| k.clone())
        {
            self.baselines.remove(&k);
        }
    }
}
fn restart(
    r: &Request,
    g: &Graph,
    health: &str,
    providers: &Value,
    freshness: Value,
    reason: &str,
) -> Result<Value> {
    let value = json!({"intent":r.intent,"target":r.target,"generation":g.snapshot.generation,"health_fingerprint":health,"freshness":freshness,"outcome":"partial","restart_required":true,"reason":reason,"coverage":g.health.coverage,"provider_health":providers,"budget":r.budget,"limits":["Context discarded; reconcile and restart with original arguments"],"diagnostics":{"counts":g.health.diagnostics,"errors":g.health.errors.values().take(3).collect::<Vec<_>>(),"errors_omitted":g.health.errors.len().saturating_sub(3),"details":"status(section: diagnostics)"},"next_cursor":null});
    if render::chars(&value) > r.budget.max_chars {
        bail!("Mandatory restart metadata exceeds budget; increase max_chars");
    }
    Ok(value)
}

#[cfg(test)]
mod lifecycle_tests {
    use super::*;
    #[test]
    fn expired_session_handles_are_pruned_without_waiting() {
        let request = Request::parse(&json!({"intent":"rename","target":"x"})).unwrap();
        let plan = Arc::new(Plan {
            request,
            target: json!("x"),
            historical_symbols: BTreeMap::new(),
            details: BTreeMap::new(),
            evidence: vec![],
            facts: json!({}),
            limits: vec![],
            outcome: "partial".into(),
            exploration_limited: false,
            depth_limited: false,
            optional_limited: false,
        });
        let mut state = State::default();
        state.cursors.insert(
            "old".into(),
            Cursor {
                request: String::new(),
                root: String::new(),
                generation: String::new(),
                health: String::new(),
                plan,
                offset: 0,
                created: Instant::now() - Duration::from_secs(301),
                bytes: 1,
            },
        );
        state.baselines.insert(
            "old".into(),
            Baseline {
                root: String::new(),
                snapshot: Arc::new(Snapshot::default()),
                sources: BTreeMap::new(),
                files: vec![],
                health: String::new(),
                strict_scope: false,
                created: Instant::now() - Duration::from_secs(601),
                bytes: 1,
            },
        );
        state.prune();
        assert!(state.cursors.is_empty() && state.baselines.is_empty());
    }
}
