//! Bounded source comparison against explicit, hash-checked session capture.
use crate::{
    config::Config,
    model::{FileRecord, Node, Snapshot, hash},
    query::Graph,
};
use anyhow::{Result, bail};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    sync::Arc,
};

pub fn read(c: &Config, file: &str, expected: &str) -> Result<String> {
    let mut bytes = vec![];
    fs::File::open(c.safe(file)?)?
        .take((c.max_file_bytes + 1) as u64)
        .read_to_end(&mut bytes)?;
    if bytes.len() > c.max_file_bytes || hash(&bytes) != expected {
        bail!("stale: source differs from snapshot during review capture/comparison")
    }
    Ok(String::from_utf8(bytes)?)
}
pub fn capture(
    g: &Graph,
    c: &Config,
    files: &[String],
) -> Result<(Arc<Snapshot>, BTreeMap<String, String>, usize)> {
    let mut sources = BTreeMap::new();
    for file in files {
        if let Some(r) = g.snapshot.files.get(file) {
            sources.insert(file.clone(), read(c, file, &r.hash)?);
        }
    }
    for file in files {
        if let Some(r) = g.snapshot.files.get(file) {
            read(c, file, &r.hash)?;
        }
    }
    // Full semantic snapshot is shared for historical cross-file consumers. Sources
    // are copied only for explicit files. Account serialization without allocating it.
    let snapshot_bytes = *g.accounted_bytes.get_or_init(|| {
        struct Counter(usize);
        impl std::io::Write for Counter {
            fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
                self.0 += buf.len();
                Ok(buf.len())
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Ok(())
            }
        }
        let mut count = Counter(0);
        serde_json::to_writer(&mut count, g.snapshot.as_ref())
            .expect("snapshot JSON to infallible counter");
        count.0
    });
    let bytes = snapshot_bytes + sources.values().map(String::len).sum::<usize>();
    Ok((g.snapshot.clone(), sources, bytes))
}
pub fn same_declaration(a: &Node, b: &Node) -> bool {
    a.id == b.id
        && a.kind == b.kind
        && a.name == b.name
        && a.qualified == b.qualified
        && a.parent == b.parent
        && a.tags == b.tags
        && a.synthetic == b.synthetic
}
#[derive(Default)]
pub struct Localization {
    pub seeds: BTreeSet<String>,
    pub hunks: Vec<Hunk>,
    pub kind: String,
    pub fallback: Option<String>,
    pub work: usize,
}
#[derive(Clone, Serialize)]
pub struct Hunk {
    pub before_start: usize,
    pub before_end: usize,
    pub after_start: usize,
    pub after_end: usize,
}
// Whitespace outside literals is presentation. Preserve literals and comment contents,
// including escaped quotes, so a changed string is never erased as formatting.
fn normalized(text: &str) -> String {
    let mut result = String::new();
    let mut quote = None;
    let mut escaped = false;
    let mut space = false;
    let mut line_comment = false;
    let mut previous = ' ';
    let mut line_content = false;
    for ch in text.chars() {
        if line_comment {
            result.push(ch);
            if ch == '\n' {
                line_comment = false;
                line_content = false;
            }
            continue;
        }
        if let Some(q) = quote {
            result.push(ch);
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == q {
                quote = None;
            }
        } else if ch == '\n' {
            // Preserve significant line breaks (JS automatic semicolons, Swift, etc.).
            // Empty lines outside literals/comments can be ignored safely.
            if line_content {
                result.push('\n');
            }
            line_content = false;
            space = false;
        } else if ch.is_whitespace() {
            space = true;
        } else {
            if space && line_content {
                result.push(' ');
            }
            space = false;
            result.push(ch);
            line_content = true;
            if ch == '/' && previous == '/' {
                line_comment = true;
            }
            if ['\'', '"', '`'].contains(&ch) {
                quote = Some(ch);
            }
        }
        previous = ch;
    }
    result.trim_end_matches('\n').to_owned()
}
fn header(text: &str) -> Option<String> {
    // Conservative fallback: only recognize a body opening after a declaration.
    let mut quote = None;
    let mut escaped = false;
    for (i, ch) in text.char_indices() {
        if let Some(q) = quote {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == q {
                quote = None;
            }
        } else if ['\'', '"', '`'].contains(&ch) {
            quote = Some(ch);
        } else if ch == '{' {
            return Some(normalized(&text[..i]));
        }
    }
    None
}
fn declaration_text(lines: &[&str], n: &Node) -> String {
    lines
        .iter()
        .skip(n.line.saturating_sub(1))
        .take(n.end.saturating_sub(n.line) + 1)
        .copied()
        .collect::<Vec<_>>()
        .join("\n")
}
pub fn localize(
    c: &Config,
    file: &str,
    before: Option<&str>,
    after: Option<&FileRecord>,
    allowance: usize,
) -> Result<Localization> {
    let mut result = Localization {
        kind: "global".into(),
        ..Default::default()
    };
    let (Some(before), Some(after)) = (before, after) else {
        return Ok(result);
    };
    let text = read(c, file, &after.hash)?;
    if crate::model::language(file) != "python" && normalized(before) == normalized(&text) {
        result.kind = "formatting".into();
        return Ok(result);
    }
    let a: Vec<_> = before.split('\n').collect();
    let b: Vec<_> = text.split('\n').collect();
    // Linear synchronization with unique unchanged lines. Each examined line is work.
    // Repetitive/large ambiguous runs fall back instead of quadratic LCS allocation.
    let mut i = 0;
    let mut j = 0;
    while i < a.len() || j < b.len() {
        if result.work >= allowance {
            result.fallback = Some("line comparison work budget exhausted".into());
            return Ok(result);
        }
        result.work += 1;
        if i < a.len() && j < b.len() && a[i] == b[j] {
            i += 1;
            j += 1;
            continue;
        }
        let (start_i, start_j) = (i, j);
        let mut sync = None;
        'search: for distance in 1..=64 {
            for left in 0..=distance {
                if result.work >= allowance {
                    break 'search;
                }
                result.work += 1;
                let right = distance - left;
                if i + left < a.len() && j + right < b.len() && a[i + left] == b[j + right] {
                    sync = Some((i + left, j + right));
                    break 'search;
                }
            }
        }
        let (end_i, end_j) = sync.unwrap_or((a.len(), b.len()));
        result.hunks.push(Hunk {
            before_start: start_i + 1,
            before_end: end_i.max(start_i + 1),
            after_start: start_j + 1,
            after_end: end_j.max(start_j + 1),
        });
        i = end_i;
        j = end_j;
        if sync.is_none() {
            break;
        }
    }
    let mut body = true;
    for h in &result.hunks {
        let candidates: Vec<_> = after
            .nodes
            .iter()
            .filter(|n| n.kind != "file" && n.line <= h.after_start && n.end >= h.after_end)
            .collect();
        let Some(n) = candidates.iter().min_by_key(|n| n.end - n.line) else {
            result.fallback =
                Some("changed range outside a declaration (import/global/deletion)".into());
            break;
        };
        if candidates
            .iter()
            .filter(|x| x.end - x.line == n.end - n.line)
            .count()
            != 1
        {
            result.fallback = Some("ambiguous containing declarations".into());
            break;
        }
        result.seeds.insert(n.id.clone());
        // AST scopes can establish that all changes start inside a body. Same-line
        // brace fallback checks the complete header, not offsets in foreign units.
        let ast_body = after.intent.ast["statements"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|s| s["scope"].as_str() == Some(&n.id))
            .filter_map(|s| s["line"].as_u64())
            .min()
            .is_some_and(|line| {
                line as usize > n.line && h.after_start >= line as usize && h.before_start > n.line
            });
        let new_decl = declaration_text(&b, n);
        let old_start = n.line as isize + h.before_start as isize - h.after_start as isize;
        let old_end = n.end as isize + h.before_end as isize - h.after_end as isize;
        let old_decl = if old_start > 0 && old_end >= old_start {
            a.iter()
                .skip(old_start as usize - 1)
                .take((old_end - old_start + 1) as usize)
                .copied()
                .collect::<Vec<_>>()
                .join("\n")
        } else {
            String::new()
        };
        let header_equal = ["function", "method", "constructor", "getter", "setter"]
            .contains(&n.kind.as_str())
            && header(&old_decl)
                .zip(header(&new_decl))
                .is_some_and(|(a, b)| !a.is_empty() && a == b);
        if !ast_body && !header_equal {
            body = false;
        }
    }
    if result.fallback.is_some() {
        result.seeds.clear();
        result.kind = "global".into();
    } else {
        result.kind = if body {
            "body"
        } else {
            "contract_or_initializer"
        }
        .into();
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::normalized;
    #[test]
    fn presentation_comparison_preserves_semantically_significant_newlines_and_literals() {
        assert_ne!(normalized("return\nvalue;"), normalized("return value;"));
        assert_ne!(
            normalized("const s = `one\ntwo`;"),
            normalized("const s = `one two`;")
        );
        assert_ne!(
            normalized("const s = 'a  b';"),
            normalized("const s = 'a b';")
        );
        assert_eq!(
            normalized("\nfunction f() {\r\n  return 1;\r\n}\r\n"),
            normalized("function f() {\nreturn 1;\n}\n")
        );
    }
}
