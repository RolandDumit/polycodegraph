//! Lexical discovery only. Anchors/expansions retain the existing resolver evidence.
use crate::{
    config::Config,
    model::{hash, language},
    query::Graph,
};
use anyhow::{Result, bail};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    sync::Arc,
};

const MAX_BYTES: usize = 8 * 1024 * 1024;
const MAX_LINES: usize = 100_000;
const MAX_TERM_BYTES: usize = 16 * 1024 * 1024;
#[derive(Default)]
pub struct LexicalIndex {
    documents: Vec<Document>,
    frequencies: BTreeMap<String, usize>,
    pub bytes: usize,
    pub files: usize,
    pub incomplete: bool,
    pub work: usize,
    pub term_bytes: usize,
    postings: BTreeMap<String, Vec<usize>>,
    excluded: BTreeMap<String, &'static str>,
    excluded_total: usize,
}
struct Document {
    file: String,
    line: usize,
    anchor: Option<String>,
    terms: BTreeSet<String>,
    fields: BTreeSet<String>,
}
fn terms(text: &str) -> BTreeSet<String> {
    let mut output = BTreeSet::new();
    for word in text.split(|c: char| !c.is_alphanumeric()) {
        if word.is_empty() {
            continue;
        }
        output.insert(word.to_lowercase());
        let mut piece = String::new();
        let mut lower = false;
        for ch in word.chars() {
            if ch.is_uppercase() && lower && !piece.is_empty() {
                output.insert(piece.to_lowercase());
                piece.clear();
            }
            piece.push(ch);
            lower = ch.is_lowercase() || ch.is_numeric();
        }
        if !piece.is_empty() {
            output.insert(piece.to_lowercase());
        }
    }
    output
}
impl LexicalIndex {
    fn build(g: &Graph, c: &Config, prefix: &str, lang: Option<&str>) -> Result<Self> {
        let mut index = Self::default();
        for (file, record) in &g.snapshot.files {
            if (!prefix.is_empty() && file != prefix && !file.starts_with(&format!("{prefix}/")))
                || lang.is_some_and(|wanted| language(file) != wanted)
            {
                continue;
            }
            let path = c.safe(file)?;
            let size = fs::metadata(&path)?.len() as usize;
            if size > c.max_file_bytes || index.bytes.saturating_add(size) > MAX_BYTES {
                index.exclude(file, "source_byte_budget");
                continue;
            }
            let mut bytes = vec![];
            fs::File::open(path)?
                .take((c.max_file_bytes + 1) as u64)
                .read_to_end(&mut bytes)?;
            if bytes.len() > c.max_file_bytes || index.bytes.saturating_add(bytes.len()) > MAX_BYTES
            {
                index.exclude(file, "source_byte_budget");
                continue;
            }
            if hash(&bytes) != record.hash {
                bail!("stale: lexical source differs from snapshot; reconcile and restart");
            }
            index.bytes += bytes.len();
            index.files += 1;
            let text = String::from_utf8(bytes)?;
            // Sweep declaration intervals once instead of scanning all nodes per line.
            let mut declarations: Vec<_> =
                record.nodes.iter().filter(|n| n.kind != "file").collect();
            declarations.sort_by(|a, b| a.line.cmp(&b.line).then(a.id.cmp(&b.id)));
            index.work += declarations.len();
            let mut next = 0;
            let mut active = BTreeSet::new();
            let mut endings = BTreeSet::new();
            let file_terms = terms(file);
            for (i, line) in text.split('\n').enumerate() {
                index.work += 1;
                while endings
                    .first()
                    .is_some_and(|(end, _): &(usize, usize)| *end <= i)
                {
                    let (_, ordinal) = endings.pop_first().expect("nonempty end queue");
                    let n = declarations[ordinal];
                    active.remove(&(n.end.saturating_sub(n.line), n.id.as_str(), ordinal));
                }
                while next < declarations.len() && declarations[next].line <= i + 1 {
                    let n = declarations[next];
                    if n.end > i {
                        active.insert((n.end.saturating_sub(n.line), n.id.as_str(), next));
                        endings.insert((n.end, next));
                    }
                    next += 1;
                }
                if index.documents.len() >= MAX_LINES {
                    index.exclude(file, "line_budget");
                    break;
                }
                let mut tokens = terms(line);
                if tokens.is_empty() {
                    continue;
                }
                let anchor = active.first().map(|(_, id, _)| (*id).to_owned());
                let mut fields = file_terms.clone();
                if let Some(id) = &anchor {
                    fields.extend(terms(id));
                }
                tokens.extend(fields.iter().cloned());
                let token_bytes = tokens.iter().map(String::len).sum::<usize>()
                    + fields.iter().map(String::len).sum::<usize>();
                if index.term_bytes.saturating_add(token_bytes) > MAX_TERM_BYTES {
                    index.exclude(file, "term_budget");
                    break;
                }
                index.term_bytes += token_bytes;
                index.work += tokens.len();
                for token in &tokens {
                    *index.frequencies.entry(token.clone()).or_default() += 1;
                    index
                        .postings
                        .entry(token.clone())
                        .or_default()
                        .push(index.documents.len());
                }
                index.documents.push(Document {
                    file: file.clone(),
                    line: i + 1,
                    anchor,
                    terms: tokens,
                    fields,
                });
            }
        }
        Ok(index)
    }
    fn exclude(&mut self, file: &str, reason: &'static str) {
        self.incomplete = true;
        self.excluded_total += 1;
        if self.excluded.len() < 128 {
            self.excluded.insert(file.to_owned(), reason);
        }
    }
}
pub fn search(g: &Graph, c: &Config, args: &Value) -> Result<Value> {
    let query = args["query"].as_str().unwrap_or("");
    if query.len() > 8192 {
        bail!("lexical query exceeds 8192-byte discovery budget; use a focused query");
    }
    let wanted = terms(query);
    if wanted.len() > 64 {
        bail!("lexical query exceeds 64-term discovery budget; use a focused query");
    }
    if wanted.is_empty() {
        bail!(
            "lexical search requires content/identifier terms; use default search for an empty inventory"
        );
    }
    let prefix = args["file"].as_str().unwrap_or("").trim_end_matches('/');
    if !prefix.is_empty() {
        crate::intents::validate_path(c, prefix)?;
    }
    let lang = args["language"].as_str();
    let key = json!([prefix, lang, c.fingerprint()?]).to_string();
    let cached = g
        .lexical
        .lock()
        .map_err(|_| anyhow::anyhow!("lexical cache unavailable"))?
        .get(&key)
        .cloned();
    let index = if let Some(index) = cached {
        index
    } else {
        // No shared lock while reading/hashing source. Snapshot owns invalidation.
        let built = Arc::new(LexicalIndex::build(g, c, prefix, lang)?);
        let mut cache = g
            .lexical
            .lock()
            .map_err(|_| anyhow::anyhow!("lexical cache unavailable"))?;
        if cache.len() >= 2 && !cache.contains_key(&key) {
            cache.pop_first();
        }
        Arc::clone(cache.entry(key).or_insert(built))
    };
    let bm25 = args["ranking"] == "bm25";
    let grouped = args["group_by"] == "anchor";
    let exact = g.resolve(query).ok().map(|i| g.nodes[i].id.as_str());
    let mut candidates = BTreeSet::new();
    for term in &wanted {
        candidates.extend(index.postings.get(term).into_iter().flatten().copied());
    }
    if let Some(id) = exact {
        candidates.extend(
            index
                .documents
                .iter()
                .enumerate()
                .filter_map(|(i, d)| (d.anchor.as_deref() == Some(id)).then_some(i)),
        );
    }
    let average = index.documents.iter().map(|d| d.terms.len()).sum::<usize>() as f64
        / index.documents.len().max(1) as f64;
    let mut ranked: Vec<_> = candidates
        .iter()
        .map(|i| &index.documents[*i])
        .filter(|d| {
            args["anchor"]
                .as_str()
                .is_none_or(|id| d.anchor.as_deref() == Some(id))
        })
        .filter(|d| {
            prefix.is_empty() || d.file == prefix || d.file.starts_with(&format!("{prefix}/"))
        })
        .filter(|d| {
            args["language"]
                .as_str()
                .is_none_or(|l| language(&d.file) == l)
        })
        .filter(|d| {
            args["kind"].as_str().is_none_or(|kind| {
                d.anchor
                    .as_ref()
                    .and_then(|id| g.ids.get(id))
                    .is_some_and(|i| g.nodes[*i].kind == kind)
            })
        })
        .filter(|d| {
            args["tag"].as_str().is_none_or(|tag| {
                d.anchor
                    .as_ref()
                    .and_then(|id| g.ids.get(id))
                    .is_some_and(|i| g.nodes[*i].tags.iter().any(|t| t == tag))
            })
        })
        .filter_map(|d| {
            let matched: Vec<_> = wanted.intersection(&d.terms).collect();
            if matched.is_empty() && !(exact.is_some() && exact == d.anchor.as_deref()) {
                return None;
            }
            let score: f64 = matched
                .iter()
                .map(|term| {
                    if bm25 {
                        let n = index.documents.len() as f64;
                        let df = index.frequencies[*term] as f64;
                        let idf = (1. + (n - df + 0.5) / (df + 0.5)).ln();
                        let normalization =
                            1.2 * (0.25 + 0.75 * d.terms.len() as f64 / average.max(1.));
                        return idf * 2.2 / (1. + normalization)
                            * if d.fields.contains(*term) { 2. } else { 1. };
                    }
                    ((index.documents.len() + 1) as f64 / (index.frequencies[*term] + 1) as f64)
                        .ln()
                        + 1.
                })
                .sum();
            Some((
                d,
                score
                    + if exact.is_some() && exact == d.anchor.as_deref() {
                        1000.
                    } else {
                        0.
                    },
            ))
        })
        .collect();
    ranked.sort_by(|(a, sa), (b, sb)| {
        sb.total_cmp(sa)
            .then_with(|| a.file.cmp(&b.file))
            .then(a.line.cmp(&b.line))
    });
    let mut matches = BTreeMap::<String, Vec<usize>>::new();
    for (d, _) in &ranked {
        matches
            .entry(
                d.anchor
                    .clone()
                    .unwrap_or_else(|| format!("{}::file", d.file)),
            )
            .or_default()
            .push(d.line);
    }
    if grouped {
        let mut seen = BTreeSet::new();
        ranked.retain(|(d, _)| {
            seen.insert(
                d.anchor
                    .clone()
                    .unwrap_or_else(|| format!("{}::file", d.file)),
            )
        });
    }
    let total = ranked.len();
    let offset = args["offset"].as_u64().unwrap_or(0) as usize;
    let limit = (args["limit"].as_u64().unwrap_or(10) as usize).min(c.max_results);
    let selected: Vec<_> = ranked.into_iter().skip(offset).take(limit).collect();
    // Validate selected source identities again before emitting cached content matches.
    for file in selected
        .iter()
        .map(|(d, _)| &d.file)
        .collect::<BTreeSet<_>>()
    {
        let mut bytes = vec![];
        fs::File::open(c.safe(file)?)?
            .take((c.max_file_bytes + 1) as u64)
            .read_to_end(&mut bytes)?;
        if bytes.len() > c.max_file_bytes || hash(bytes) != g.snapshot.files[file].hash {
            bail!("stale: lexical match source changed; reconcile and restart");
        }
    }
    let mode = args["expand"].as_str().unwrap_or("none");
    let mut edges = BTreeMap::new();
    let mut steps = 0;
    if mode != "none" {
        for id in selected
            .iter()
            .filter_map(|(d, _)| d.anchor.as_ref())
            .collect::<BTreeSet<_>>()
        {
            for edge in g
                .context
                .edges(
                    g,
                    id,
                    mode == "callers",
                    &["calls", "references", "overrides"],
                )
                .take(41usize.saturating_sub(steps))
            {
                steps += 1;
                if steps > 40 {
                    break;
                }
                edges.insert(serde_json::to_string(edge)?, edge);
            }
            if steps > 40 {
                break;
            }
        }
    }
    let rows: Vec<_> = selected
        .iter()
        .map(|(d, score)| {
            let mut row = json!([
                d.file,
                d.line,
                d.anchor,
                score,
                "lexical_candidate; no new resolved relation"
            ]);
            if grouped {
                let lines = &matches[&d
                    .anchor
                    .clone()
                    .unwrap_or_else(|| format!("{}::file", d.file))];
                row.as_array_mut().expect("row").extend([
                    json!(lines.len()),
                    json!(lines.iter().take(3).collect::<Vec<_>>()),
                ]);
            }
            row
        })
        .collect();
    let mut result = json!({"mode":"lexical","generation":g.snapshot.generation,"columns":["file","line","anchor_id","retrieval_score","confidence"],"rows":rows,"offset":offset,"total":if index.incomplete{Value::Null}else{json!(total)},"discovered_total":total,"next_offset":if offset+selected.len()<total{json!(offset+selected.len())}else{Value::Null},"collection_complete":!index.incomplete && offset+selected.len()>=total,"index":{"files":index.files,"source_bytes":index.bytes,"max_bytes":MAX_BYTES,"max_lines":MAX_LINES,"max_term_bytes":MAX_TERM_BYTES,"term_bytes":index.term_bytes,"build_work":index.work,"incomplete":index.incomplete,"ranking":"line-document term overlap weighted by inverse document frequency; deterministic lexical baseline, not embeddings/BM25"},"expansion":{"mode":mode,"steps":steps.min(40),"incomplete":steps>40,"relations":edges.into_values().collect::<Vec<_>>(),"confidence":"existing provider semantic evidence only"},"limits":["Lexical score is retrieval relevance, not semantic confidence; no match proves absence of behavior","Use snippet for source and inspect_change with anchor_id for required structural inventories"]});
    result["group_by"] = json!(if grouped { "anchor" } else { "line" });
    result["index"]["scope"] = json!({"file":prefix,"language":lang});
    result["index"]["excluded_files"] = json!(index.excluded);
    result["index"]["excluded_total"] = json!(index.excluded_total);
    result["index"]["excluded_omitted"] =
        json!(index.excluded_total.saturating_sub(index.excluded.len()));
    result["index"]["cache_capacity"] = json!(2);
    if bm25 {
        result["index"]["ranking"] = json!(
            "bm25 binary term presence, k1=1.2 b=0.75; name/path fields weight 2; experimental lexical score, not confidence"
        );
    }
    if grouped {
        result["columns"]
            .as_array_mut()
            .expect("columns")
            .extend([json!("match_count"), json!("match_lines")]);
        result["match_details"] = json!(
            "Repeat mode=lexical, group_by=line with the same query/file/ranking and anchor_id as anchor; paginate offset. Unanchored file matches use the file filter without anchor."
        );
    }
    Ok(result)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn names_paths_and_unicode_have_useful_terms() {
        let t = terms("lib/UserRepository.fetch_value réseau");
        for word in [
            "lib",
            "user",
            "repository",
            "userrepository",
            "fetch",
            "value",
            "réseau",
        ] {
            assert!(t.contains(word));
        }
    }
}
