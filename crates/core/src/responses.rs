//! Presentation of index health. No source discovery or provider execution here.
use crate::{
    config::Config,
    model::{Node, Snapshot, hash, language},
    providers,
};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

pub struct Health {
    pub counts: Value,
    pub coverage: Value,
    pub diagnostics: BTreeMap<String, usize>,
    pub errors: BTreeMap<String, Value>,
    fingerprint: String,
}
impl Health {
    pub fn new(
        snapshot: &Snapshot,
        nodes: impl Iterator<Item = NodeCounts>,
        edges: usize,
        dropped: usize,
    ) -> Self {
        let symbols = nodes.filter(|n| n.symbol).count();
        let mut languages = BTreeMap::<String, usize>::new();
        let mut diagnostics = BTreeMap::<String, usize>::from([
            ("error".into(), 0),
            ("warning".into(), 0),
            ("info".into(), 0),
        ]);
        let mut errors = BTreeMap::new();
        let mut identities = vec![];
        let mut unresolved = 0;
        for (file, record) in &snapshot.files {
            *languages.entry(language(file).into()).or_default() += 1;
            unresolved += record.unresolved_calls;
            for d in &record.diagnostics {
                let severity = d["severity"].as_str().unwrap_or("error");
                *diagnostics.entry(severity.into()).or_default() += 1;
                let identity = hash(json!([file, d]).to_string());
                identities.push(identity.clone());
                if severity == "error" {
                    // No machine paths or unbounded provider messages in automatic previews.
                    errors.insert(
                        identity,
                        json!({"file":file,"line":d["line"],"code":d["code"]}),
                    );
                }
            }
        }
        let coverage = json!({"languages":languages,"skipped":snapshot.skipped.len(),"unresolved_calls":unresolved,"dropped_edges":dropped,"precision":"static; dynamic/callback and cross-language coverage incomplete"});
        let fingerprint = hash(json!([identities, coverage]).to_string());
        Self {
            counts: json!({"files":snapshot.files.len(),"symbols":symbols,"edges":edges}),
            coverage,
            diagnostics,
            errors,
            fingerprint,
        }
    }
    pub fn provider_health(&self, c: &Config) -> Value {
        let doctor = providers::doctor(c);
        let mut health = serde_json::Map::new();
        for lang in self.coverage["languages"]
            .as_object()
            .into_iter()
            .flat_map(|m| m.keys())
        {
            let key = if ["typescript", "javascript"].contains(&lang.as_str()) {
                "typescript_javascript"
            } else {
                lang
            };
            health.insert(
                lang.clone(),
                json!({"available":doctor[key]["available"]==true}),
            );
        }
        Value::Object(health)
    }
    pub fn fingerprint(&self, provider_health: &Value) -> String {
        hash(json!([self.fingerprint, provider_health]).to_string())[..20].into()
    }
    pub fn issues(&self, provider_health: &Value) -> bool {
        !self.errors.is_empty()
            || provider_health
                .as_object()
                .into_iter()
                .flat_map(|m| m.values())
                .any(|v| v["available"] != true)
    }
    pub fn error_update(&self, previous: &BTreeSet<String>) -> Value {
        let changed: Vec<_> = self
            .errors
            .iter()
            .filter(|(key, _)| !previous.contains(*key))
            .map(|(_, value)| value)
            .collect();
        json!({"new_or_changed_total":changed.len(),"new_or_changed":changed.iter().take(3).collect::<Vec<_>>(),"omitted":changed.len().saturating_sub(3),"resolved":previous.iter().filter(|key|!self.errors.contains_key(*key)).count()})
    }
}
pub struct NodeCounts {
    symbol: bool,
}
impl From<&Node> for NodeCounts {
    fn from(node: &Node) -> Self {
        Self {
            symbol: node.kind != "file" && node.kind != "external",
        }
    }
}
pub fn page(
    items: impl IntoIterator<Item = Value>,
    args: &Value,
    c: &Config,
    generation: &str,
    health: &str,
) -> Value {
    let items: Vec<_> = items.into_iter().collect();
    let offset = args["offset"].as_u64().unwrap_or(0) as usize;
    let limit = (args["limit"]
        .as_u64()
        .unwrap_or(if c.compact(args) { 20 } else { 50 }) as usize)
        .min(c.max_results);
    let rows: Vec<_> = items.iter().skip(offset).take(limit).collect();
    let total = items.len();
    let next = offset.saturating_add(rows.len());
    json!({"generation":generation,"health_fingerprint":health,"items":rows,"total":total,"offset":offset,"next_offset":if next < total {Some(next)} else {None},"omitted":total.saturating_sub(rows.len()),"truncated":rows.len()<total})
}
pub fn update_summary(report: &Value) -> Value {
    let changed = report["changed_total"].as_u64().unwrap_or(0);
    let deleted = report["deleted_total"].as_u64().unwrap_or(0);
    let reindexed = report["reindexed_total"].as_u64().unwrap_or(0);
    json!({"state":if changed+deleted+reindexed==0 && report["full"]!=true {"unchanged"} else {"updated"},"changed":changed,"deleted":deleted,"reindexed":reindexed,"full":report["full"]==true})
}
