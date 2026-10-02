use crate::{
    config::Config,
    model::{Edge, Node, Snapshot, TextOrder, compare_text, hash, language},
};
use anyhow::{Result, bail};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet, HashMap, HashSet},
    fs,
    ops::Index,
    sync::Arc,
};
pub const COLUMNS: [&str; 6] = ["id", "kind", "name", "file", "line", "tags"];
pub struct Nodes {
    snapshot: Arc<Snapshot>,
    files: Arc<Vec<String>>,
    positions: Vec<(usize, usize)>,
}
impl Nodes {
    pub fn len(&self) -> usize {
        self.positions.len()
    }
    pub fn is_empty(&self) -> bool {
        self.positions.is_empty()
    }
    pub fn iter(&self) -> impl Iterator<Item = &Node> {
        self.positions
            .iter()
            .map(|(f, i)| &self.snapshot.files[&self.files[*f]].nodes[*i])
    }
}
impl Index<usize> for Nodes {
    type Output = Node;
    fn index(&self, i: usize) -> &Node {
        let (f, n) = self.positions[i];
        &self.snapshot.files[&self.files[f]].nodes[n]
    }
}
pub struct Edges {
    snapshot: Arc<Snapshot>,
    files: Arc<Vec<String>>,
    positions: Vec<(usize, usize)>,
}
impl Edges {
    pub fn len(&self) -> usize {
        self.positions.len()
    }
    pub fn is_empty(&self) -> bool {
        self.positions.is_empty()
    }
    pub fn iter(&self) -> impl Iterator<Item = &Edge> {
        self.positions
            .iter()
            .map(|(f, i)| &self.snapshot.files[&self.files[*f]].edges[*i])
    }
}
impl Index<usize> for Edges {
    type Output = Edge;
    fn index(&self, i: usize) -> &Edge {
        let (f, n) = self.positions[i];
        &self.snapshot.files[&self.files[f]].edges[n]
    }
}
pub struct Graph {
    pub context: crate::intents::ContextIndex,
    pub health: crate::responses::Health,
    pub snapshot: Arc<Snapshot>,
    pub nodes: Nodes,
    pub ids: HashMap<String, usize>,
    pub edges: Edges,
    pub incoming: Vec<Vec<usize>>,
    pub outgoing: Vec<Vec<usize>>,
    pub dropped: usize,
    names: HashMap<String, Vec<usize>>,
    qualified: HashMap<String, Vec<usize>>,
    file_edges: HashMap<String, Vec<usize>>,
}
impl Graph {
    pub(crate) fn named(&self, name: &str) -> impl Iterator<Item = &Node> {
        self.names
            .get(name)
            .into_iter()
            .flatten()
            .map(|i| &self.nodes[*i])
    }
    pub fn new(snapshot: Snapshot) -> Self {
        let snapshot = Arc::new(snapshot);
        let files = Arc::new(snapshot.files.keys().cloned().collect::<Vec<_>>());
        let mut node_map = BTreeMap::new();
        for (f, r) in snapshot.files.values().enumerate() {
            for (i, n) in r.nodes.iter().enumerate() {
                node_map.insert(n.id.as_str(), (f, i));
            }
        }
        let mut positions: Vec<_> = node_map.into_values().collect();
        positions.sort_by(|(a, i), (b, j)| {
            compare_text(
                &snapshot.files[&files[*a]].nodes[*i].id,
                &snapshot.files[&files[*b]].nodes[*j].id,
            )
        });
        let nodes = Nodes {
            snapshot: snapshot.clone(),
            files: files.clone(),
            positions,
        };
        let ids: HashMap<_, _> = nodes
            .iter()
            .enumerate()
            .map(|(i, n)| (n.id.clone(), i))
            .collect();
        let mut names: HashMap<String, Vec<usize>> = HashMap::new();
        let mut qualified: HashMap<String, Vec<usize>> = HashMap::new();
        for (i, n) in nodes.iter().enumerate() {
            names.entry(n.name.clone()).or_default().push(i);
            qualified.entry(n.qualified.clone()).or_default().push(i);
        }
        let mut dropped = 0;
        let mut seen = HashSet::new();
        let mut positions = vec![];
        for (f, r) in snapshot.files.values().enumerate() {
            for (i, e) in r.edges.iter().enumerate() {
                if !ids.contains_key(&e.source) || !ids.contains_key(&e.target) {
                    dropped += 1;
                    continue;
                }
                if seen.insert((
                    e.source.as_str(),
                    e.target.as_str(),
                    e.kind.as_str(),
                    e.file.as_str(),
                    e.offset,
                )) {
                    positions.push((f, i));
                }
            }
        }
        drop(seen);
        positions
            .sort_by_cached_key(|(f, i)| TextOrder(snapshot.files[&files[*f]].edges[*i].key()));
        let edges = Edges {
            snapshot: snapshot.clone(),
            files,
            positions,
        };
        let mut incoming = vec![vec![]; nodes.len()];
        let mut outgoing = incoming.clone();
        let mut file_edges: HashMap<String, Vec<usize>> = HashMap::new();
        for (i, e) in edges.iter().enumerate() {
            incoming[ids[&e.target]].push(i);
            outgoing[ids[&e.source]].push(i);
            file_edges
                .entry(nodes[ids[&e.source]].file.clone())
                .or_default()
                .push(i);
            if nodes[ids[&e.source]].file != nodes[ids[&e.target]].file {
                file_edges
                    .entry(nodes[ids[&e.target]].file.clone())
                    .or_default()
                    .push(i);
            }
        }
        Self {
            context: crate::intents::ContextIndex::new(&snapshot),
            health: crate::responses::Health::new(
                &snapshot,
                nodes.iter().map(Into::into),
                edges.len(),
                dropped,
            ),
            snapshot,
            nodes,
            ids,
            edges,
            incoming,
            outgoing,
            dropped,
            names,
            qualified,
            file_edges,
        }
    }
    pub fn resolve(&self, target: &str) -> Result<usize> {
        if let Some(i) = self
            .ids
            .get(target)
            .or_else(|| self.ids.get(&format!("{target}::file")))
        {
            return Ok(*i);
        }
        let matches = self
            .qualified
            .get(target)
            .or_else(|| self.names.get(target));
        match matches {
            None => bail!("Symbol or file not found: {target}"),
            Some(v) if v.len() == 1 => Ok(v[0]),
            Some(v) => bail!(
                "Ambiguous symbol; use an id from search_symbol: {}",
                json!({"matches":v.iter().take(10).map(|i|self.nodes[*i].compact()).collect::<Vec<_>>()})
            ),
        }
    }
    fn table(
        &self,
        c: &Config,
        columns: Value,
        rows: Vec<Vec<Value>>,
        a: &Value,
        mut extra: Value,
    ) -> Value {
        let offset = a["offset"].as_u64().unwrap_or(0) as usize;
        let limit = (a["limit"]
            .as_u64()
            .unwrap_or(if c.compact(a) { 20 } else { 50 }) as usize)
            .min(c.max_results);
        let total = rows.len();
        let page: Vec<_> = rows.into_iter().skip(offset).take(limit).collect();
        let next = if offset + page.len() < total {
            json!(offset + page.len())
        } else {
            Value::Null
        };
        extra["generation"] = json!(self.snapshot.generation);
        extra["columns"] = columns;
        extra["rows"] = json!(page);
        extra["total"] = json!(total);
        extra["offset"] = json!(offset);
        extra["next_offset"] = next;
        if c.compact(a) {
            extra["omitted"] =
                json!(total.saturating_sub(extra["rows"].as_array().map_or(0, Vec::len)));
            extra["truncated"] = json!(total > extra["rows"].as_array().map_or(0, Vec::len));
        }
        extra
    }
    pub fn search(&self, c: &Config, a: &Value) -> Value {
        let q = a["query"].as_str().unwrap_or("").to_lowercase();
        let mut matches: Vec<_> = self
            .nodes
            .iter()
            .filter(|n| {
                n.kind != "external"
                    && a["kind"].as_str().map_or(n.kind != "file", |k| n.kind == k)
                    && a["tag"]
                        .as_str()
                        .is_none_or(|t| n.tags.iter().any(|x| x == t))
                    && a["language"]
                        .as_str()
                        .is_none_or(|l| language(&n.file) == l)
                    && a["file"].as_str().is_none_or(|f| n.file.starts_with(f))
                    && (n.name.to_lowercase().contains(&q)
                        || n.qualified.to_lowercase().contains(&q))
            })
            .collect();
        let rank = |n: &Node| {
            let s = n.name.to_lowercase();
            if s == q {
                0
            } else if s.starts_with(&q) {
                1
            } else {
                2
            }
        };
        matches.sort_by(|x, y| {
            rank(x)
                .cmp(&rank(y))
                .then_with(|| compare_text(&x.id, &y.id))
        });
        let mut args = a.clone();
        if c.compact(a) && a["limit"].is_null() {
            args["limit"] = json!(10);
        }
        self.table(
            c,
            json!(COLUMNS),
            matches.into_iter().map(Node::row).collect(),
            &args,
            json!({}),
        )
    }
    fn file_filter(&self, c: &Config, a: &Value) -> Result<Value> {
        let Some(prefix) = a["file"].as_str().filter(|p| !p.is_empty()) else {
            return Ok(json!({}));
        };
        if prefix.starts_with('/')
            || prefix.contains('\\')
            || prefix.contains(':')
            || prefix.split('/').any(|p| p == "..")
        {
            bail!("file must be a slash-separated prefix relative to graph root");
        }
        c.safe(prefix)?;
        let valid = self.snapshot.files.keys().any(|f| f.starts_with(prefix));
        let mut result = json!({"file_filter":{"valid":valid}});
        if !valid {
            result["warning"] =
                json!("File prefix is not indexed; use paths relative to graph root");
            let mut candidates = BTreeSet::new();
            for file in self.snapshot.files.keys() {
                for (start, _) in file.match_indices(prefix) {
                    if start > 0 && file.as_bytes()[start - 1] == b'/' {
                        candidates.insert(file[..start + prefix.len()].to_owned());
                    }
                }
            }
            if candidates.len() == 1 {
                result["file_filter"]["suggested_prefix"] = json!(candidates.first());
            }
        }
        Ok(result)
    }
    pub fn relations(
        &self,
        c: &Config,
        a: &Value,
        direction: &str,
        kinds: Option<&[&str]>,
    ) -> Result<Value> {
        let i = self.resolve(a["target"].as_str().unwrap_or(""))?;
        let mut rows = vec![];
        for (dir, list) in [("out", &self.outgoing[i]), ("in", &self.incoming[i])] {
            if direction != "both" && direction != dir {
                continue;
            }
            for k in list {
                let e = &self.edges[*k];
                if kinds.is_some_and(|ks| !ks.contains(&e.kind.as_str())) {
                    continue;
                }
                let other = if dir == "out" { &e.target } else { &e.source };
                let mut row = self.nodes[self.ids[other]].row();
                row.extend([
                    json!(e.kind),
                    json!(dir),
                    json!(e.file),
                    json!(e.line),
                    json!(e.confidence),
                ]);
                rows.push(row);
            }
        }
        rows.sort_by_key(|r| TextOrder(dart_join(r, "\t")));
        let mut cols = COLUMNS.to_vec();
        cols.extend([
            "relation",
            "direction",
            "site_file",
            "site_line",
            "confidence",
        ]);
        Ok(self.table(c, json!(cols), rows, a, json!({"target":self.nodes[i].id})))
    }
    pub fn implementations(&self, c: &Config, a: &Value) -> Result<Value> {
        let start = self.resolve(a["target"].as_str().unwrap_or(""))?;
        let mut seen = HashSet::from([start]);
        let mut queue = vec![start];
        let mut cursor = 0;
        while cursor < queue.len() {
            for e in &self.incoming[queue[cursor]] {
                let e = &self.edges[*e];
                let i = self.ids[&e.source];
                if ["extends", "implements", "with", "overrides"].contains(&e.kind.as_str())
                    && seen.insert(i)
                {
                    queue.push(i);
                }
            }
            cursor += 1;
        }
        let mut found: Vec<_> = queue.into_iter().skip(1).map(|i| &self.nodes[i]).collect();
        found.sort_by(|a, b| compare_text(&a.id, &b.id));
        Ok(self.table(
            c,
            json!(COLUMNS),
            found.into_iter().map(Node::row).collect(),
            a,
            json!({"target":self.nodes[start].id}),
        ))
    }
    pub fn dependencies(&self, c: &Config, a: &Value) -> Result<Value> {
        let i = self.resolve(a["target"].as_str().unwrap_or(""))?;
        let n = &self.nodes[i];
        let file = self.resolve(&n.file)?;
        let dir = a["direction"].as_str().unwrap_or("out");
        let mut found = BTreeMap::new();
        for idx in self.file_edges.get(&n.file).into_iter().flatten() {
            let e = &self.edges[*idx];
            if e.kind == "contains" {
                continue;
            }
            let from = &self.nodes[self.ids[&e.source]];
            let to = &self.nodes[self.ids[&e.target]];
            if from.file == to.file {
                continue;
            }
            let out = from.file == n.file;
            let into = to.file == n.file;
            if (dir == "out" && !out) || (dir == "in" && !into) {
                continue;
            }
            let other = if out { to } else { from };
            let direction = if out { "out" } else { "in" };
            found.insert(
                format!("{}|{}|{direction}", other.file, e.kind),
                vec![json!(other.file), json!(e.kind), json!(direction)],
            );
        }
        let mut rows: Vec<_> = found.into_values().collect();
        rows.sort_by_key(|r| TextOrder(dart_join(r, "")));
        Ok(self.table(
            c,
            json!(["file", "relation", "direction"]),
            rows,
            a,
            json!({"target":self.nodes[file].id}),
        ))
    }
    pub fn affected(&self, c: &Config, a: &Value) -> Result<Value> {
        let start = self.resolve(a["target"].as_str().unwrap_or(""))?;
        let depth = a["depth"].as_u64().unwrap_or(6) as usize;
        if !(1..=32).contains(&depth) {
            bail!("depth must be 1..32")
        }
        let mut dist = HashMap::from([(start, 0usize)]);
        let mut reasons: HashMap<usize, (usize, String)> = HashMap::new();
        let mut queue = vec![start];
        let mut cursor = 0;
        let mut limited = false;
        while cursor < queue.len() {
            let id = queue[cursor];
            let n = &self.nodes[id];
            let distance = dist[&id];
            let mut candidates = vec![];
            for e in &self.incoming[id] {
                let e = &self.edges[*e];
                if [
                    "references",
                    "calls",
                    "extends",
                    "implements",
                    "with",
                    "on",
                    "overrides",
                    "registers",
                    "imports",
                    "exports",
                    "part",
                    "part_of",
                ]
                .contains(&e.kind.as_str())
                {
                    candidates.push((self.ids[&e.source], e.kind.clone()));
                }
            }
            if [
                "file",
                "class",
                "mixin",
                "enum",
                "extension",
                "extension_type",
                "interface",
                "struct",
                "record",
                "type",
            ]
            .contains(&n.kind.as_str())
            {
                for e in &self.outgoing[id] {
                    let e = &self.edges[*e];
                    if e.kind == "contains" {
                        candidates
                            .push((self.ids[&e.target], "member_of_changed_container".into()));
                    }
                }
            }
            for e in &self.outgoing[id] {
                let e = &self.edges[*e];
                if e.kind == "overrides" {
                    candidates.push((self.ids[&e.target], "dispatch_contract".into()));
                }
            }
            if let Some(p) = n.parent.as_ref().and_then(|p| self.ids.get(p))
                && self.nodes[*p].kind != "file"
            {
                candidates.push((*p, "container_of_affected_member".into()));
            }
            for (next, why) in candidates {
                if dist.contains_key(&next) {
                    continue;
                }
                if distance >= depth {
                    limited = true;
                    continue;
                }
                dist.insert(next, distance + 1);
                reasons.insert(next, (id, why));
                queue.push(next);
            }
            cursor += 1;
        }
        let mut found: Vec<_> = queue.into_iter().skip(1).collect();
        found.sort_by(|x, y| {
            dist[x]
                .cmp(&dist[y])
                .then_with(|| compare_text(&self.nodes[*x].id, &self.nodes[*y].id))
        });
        let files: BTreeSet<_> = found
            .iter()
            .map(|i| self.nodes[*i].file.clone())
            .filter(|f| self.snapshot.files.contains_key(f))
            .collect();
        let rows = found
            .iter()
            .map(|i| {
                let mut row = self.nodes[*i].row();
                let (via, why) = &reasons[i];
                row.extend([json!(dist[i]), json!(self.nodes[*via].id), json!(why)]);
                row
            })
            .collect();
        let mut cols = COLUMNS.to_vec();
        cols.extend(["distance", "via", "reason"]);
        Ok(self.table(c,json!(cols),rows,a,json!({"target":self.nodes[start].id,"conservative":true,"depth":depth,"depth_limited":limited,"affected_files":files.iter().take(c.max_results).collect::<Vec<_>>(),"affected_files_total":files.len()})))
    }
    pub fn snippet(&self, c: &Config, a: &Value) -> Result<Value> {
        let n = a["target"]
            .as_str()
            .map(|t| self.resolve(t))
            .transpose()?
            .map(|i| &self.nodes[i]);
        let file = a["file"]
            .as_str()
            .or(n.map(|n| n.file.as_str()))
            .ok_or_else(|| anyhow::anyhow!("Choose an indexed source file"))?;
        let r = self
            .snapshot
            .files
            .get(file)
            .ok_or_else(|| anyhow::anyhow!("Choose an indexed source file"))?;
        let content = fs::read_to_string(c.safe(file)?)?;
        if hash(&content) != r.hash {
            bail!("Source changed while reading; retry the query")
        }
        let lines: Vec<_> = content.split('\n').collect();
        let ctx = a["context"].as_u64().unwrap_or(2) as usize;
        if ctx > 20 {
            bail!("context must be 0..20")
        }
        let requested_start = a["start_line"]
            .as_u64()
            .map(|v| v as usize)
            .or(n.map(|n| n.line))
            .unwrap_or(1);
        let requested_end = a["end_line"]
            .as_u64()
            .map(|v| v as usize)
            .or(n.map(|n| n.end))
            .unwrap_or(requested_start);
        if requested_start == 0 || requested_end < requested_start || requested_start > lines.len()
        {
            bail!("Invalid line range")
        }
        let start = requested_start.saturating_sub(ctx).max(1);
        let desired = requested_end.saturating_add(ctx).min(lines.len());
        let budget = if c.compact(a) && a["end_line"].is_null() {
            c.max_snippet_lines.min(30)
        } else {
            c.max_snippet_lines
        };
        let end = desired.min(start + budget - 1);
        let text = lines[start - 1..end].join("\n");
        let truncated = end < desired || text.encode_utf16().count() > c.max_snippet_chars;
        let mut units = 0;
        let text: String = text
            .chars()
            .take_while(|ch| {
                units += ch.len_utf16();
                units <= c.max_snippet_chars
            })
            .collect();
        Ok(
            json!({"generation":self.snapshot.generation,"file":file,"start_line":start,"end_line":start+text.split('\n').count()-1,"truncated":truncated,"text":text}),
        )
    }
    pub fn architecture(&self, c: &Config, limit: usize) -> Value {
        let limit = limit.clamp(1, c.max_results);
        let symbols: Vec<_> = self
            .nodes
            .iter()
            .enumerate()
            .filter(|(_, n)| n.kind != "file" && n.kind != "external")
            .collect();
        let mut hubs = symbols.clone();
        hubs.sort_by(|(ia, a), (ib, b)| {
            self.incoming[*ib]
                .len()
                .cmp(&self.incoming[*ia].len())
                .then_with(|| compare_text(&a.id, &b.id))
        });
        let directories = counts(self.snapshot.files.keys().map(|f| {
            let parts: Vec<_> = f.split('/').collect();
            if parts.len() > 1 {
                parts[..parts.len() - 1]
                    .iter()
                    .take(2)
                    .copied()
                    .collect::<Vec<_>>()
                    .join("/")
            } else {
                ".".into()
            }
        }));
        let diagnostic_total: usize = self
            .snapshot
            .files
            .values()
            .map(|r| r.diagnostics.len())
            .sum();
        let samples: Vec<_> = self
            .snapshot
            .files
            .iter()
            .flat_map(|(f, r)| {
                r.diagnostics.iter().map(move |d| {
                    let mut d = d.clone();
                    d["file"] = json!(f);
                    if let Some(msg) = d["message"].as_str() {
                        let msg = msg.to_owned();
                        if msg.encode_utf16().count() > 512 {
                            d["message"] = json!(msg.chars().take(512).collect::<String>());
                            d["message_truncated"] = json!(true);
                        }
                    }
                    d
                })
            })
            .take(limit)
            .collect();
        json!({"generation":self.snapshot.generation,"files":self.snapshot.files.len(),"symbols":symbols.len(),"languages":counts(self.snapshot.files.keys().map(|f|language(f).to_owned())),"edges":self.edges.len(),"kinds":counts(symbols.iter().map(|(_,n)|n.kind.clone())),"tags":counts(symbols.iter().flat_map(|(_,n)|n.tags.clone())),"directories":directories.iter().take(c.max_results).collect::<BTreeMap<_,_>>(),"directories_total":directories.len(),"relations":counts(self.edges.iter().map(|e|e.kind.clone())),"diagnostics":counts(self.snapshot.files.values().flat_map(|r|r.diagnostics.iter().map(|d|d["severity"].as_str().unwrap_or("error").to_owned()))),"diagnostic_samples":samples,"diagnostic_samples_total":diagnostic_total,"unresolved_calls":self.snapshot.files.values().map(|r|r.unresolved_calls).sum::<usize>(),"dropped_edges":self.dropped,"skipped":self.snapshot.skipped.iter().take(c.max_results).collect::<Vec<_>>(),"skipped_total":self.snapshot.skipped.len(),"hubs":{"columns":["id","kind","name","file","line","tags","incoming_edges"],"rows":hubs.iter().take(limit).map(|(i,n)|{let mut row=n.row();row.push(json!(self.incoming[*i].len()));row}).collect::<Vec<_>>()},"precision":"Static semantic targets across Dart, TypeScript/JavaScript, Java, Go, Python, Rust, Swift, Objective-C and Kotlin; dynamic/callback flow, external Rust crates and macro expansion may be incomplete. Flutter tags are optional discovery hints."})
    }
    pub fn inspect(&self, c: &Config, a: &Value) -> Result<Value> {
        let i = self.resolve(a["target"].as_str().unwrap_or(""))?;
        let mut args = a.clone();
        args["target"] = json!(self.nodes[i].id);
        if args["limit"].is_null() {
            args["limit"] = json!(20);
        }
        let mut out = json!({"generation":self.snapshot.generation,"symbol":self.nodes[i].compact(),"callers":self.relations(c,&args,"in",Some(&["calls"]))?,"implementations":self.implementations(c,&args)?,"impact":self.affected(c,&args)?});
        for section in ["callers", "implementations", "impact"] {
            let v = &mut out[section];
            let total = v["total"].as_u64().unwrap_or(0);
            let size = v["rows"].as_array().map_or(0, |r| r.len()) as u64;
            v["omitted"] = json!(total - size);
            v["truncated"] = json!(total > size);
        }
        if a["include_snippet"] == true {
            out["snippet"] =
                self.snippet(c, &json!({"target":self.nodes[i].id,"detail":a["detail"]}))?;
        }
        Ok(out)
    }
    pub fn call(&self, c: &Config, name: &str, a: &Value) -> Result<Value> {
        match name {
            "search_symbol" | "search" => {
                let filter = self.file_filter(c, a)?;
                let mut out = self.search(c, a);
                // Preserve legacy valid-prefix output; invalid prefixes are always explained.
                if c.compact(a) || filter["file_filter"]["valid"] == false {
                    for (key, value) in filter.as_object().into_iter().flatten() {
                        out[key] = value.clone();
                    }
                }
                Ok(out)
            }
            "get_architecture" => Ok(self.architecture(
                c,
                a["limit"]
                    .as_u64()
                    .unwrap_or(if c.compact(a) { 5 } else { 20 }) as usize,
            )),
            "callers" => self.relations(c, a, "in", Some(&["calls"])),
            "callees" => self.relations(c, a, "out", Some(&["calls"])),
            "references" => self.relations(c, a, "in", Some(&["references"])),
            "neighbors" => {
                let ks = a["kinds"]
                    .as_array()
                    .map(|v| v.iter().filter_map(Value::as_str).collect::<Vec<_>>());
                self.relations(
                    c,
                    a,
                    a["direction"].as_str().unwrap_or("both"),
                    ks.as_deref(),
                )
            }
            "dependencies" => self.dependencies(c, a),
            "implementations" => self.implementations(c, a),
            "affected_by_change" | "blast_radius" => self.affected(c, a),
            "snippet" => self.snippet(c, a),
            "inspect_change" => self.inspect(c, a),
            _ => bail!("Unknown tool: {name}"),
        }
    }
}
fn counts(values: impl IntoIterator<Item = String>) -> BTreeMap<String, usize> {
    let mut out = BTreeMap::new();
    for v in values {
        *out.entry(v).or_default() += 1;
    }
    out
}
fn dart_value(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Array(a) => format!(
            "[{}]",
            a.iter().map(dart_value).collect::<Vec<_>>().join(", ")
        ),
        Value::Null => "null".into(),
        _ => v.to_string(),
    }
}
fn dart_join(row: &[Value], sep: &str) -> String {
    row.iter().map(dart_value).collect::<Vec<_>>().join(sep)
}
