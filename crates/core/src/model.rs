use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
pub fn hash(bytes: impl AsRef<[u8]>) -> String {
    format!("{:x}", Sha256::digest(bytes.as_ref()))
}
pub fn language(file: &str) -> &'static str {
    match file.rsplit('.').next().unwrap_or("") {
        "dart" => "dart",
        "ts" | "tsx" => "typescript",
        "js" | "jsx" | "mjs" | "cjs" => "javascript",
        "java" => "java",
        "go" => "go",
        "py" | "pyi" => "python",
        "rs" => "rust",
        "swift" => "swift",
        "kt" => "kotlin",
        "h" | "m" | "mm" => "objectivec",
        _ => "unknown",
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Node {
    pub id: String,
    pub name: String,
    pub kind: String,
    pub file: String,
    pub line: usize,
    #[serde(rename = "q")]
    pub qualified: String,
    #[serde(rename = "end")]
    pub end: usize,
    pub offset: usize,
    pub length: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent: Option<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub synthetic: bool,
}
impl Node {
    pub fn row(&self) -> Vec<Value> {
        vec![
            json!(self.id),
            json!(self.kind),
            json!(self.name),
            json!(self.file),
            json!(self.line),
            json!(self.tags),
        ]
    }
    pub fn compact(&self) -> Value {
        let mut v = json!({"id":self.id,"kind":self.kind,"name":self.name,"file":self.file,"line":self.line});
        if !self.tags.is_empty() {
            v["tags"] = json!(self.tags);
        }
        if self.synthetic {
            v["synthetic"] = json!(true);
        }
        v
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Edge {
    pub source: String,
    pub target: String,
    pub kind: String,
    pub file: String,
    pub line: usize,
    pub offset: usize,
    #[serde(default = "resolved")]
    pub confidence: String,
}
fn resolved() -> String {
    "resolved".into()
}
impl Edge {
    pub fn key(&self) -> String {
        format!(
            "{}|{}|{}|{}|{}",
            self.source, self.target, self.kind, self.file, self.offset
        )
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileRecord {
    pub file: String,
    pub hash: String,
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub dependencies: Vec<String>,
    #[serde(default)]
    pub diagnostics: Vec<Value>,
    #[serde(default, rename = "unresolvedCalls")]
    pub unresolved_calls: usize,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Snapshot {
    pub root: String,
    pub fingerprint: String,
    pub environment: String,
    #[serde(default)]
    pub environment_inputs: BTreeMap<String, String>,
    pub generation: String,
    pub files: BTreeMap<String, FileRecord>,
    pub skipped: Vec<String>,
    #[serde(default)]
    pub scopes: BTreeMap<String, String>,
}

/// Preserve Dart's UTF-16 string ordering for stable public pagination.
pub fn compare_text(a: &str, b: &str) -> std::cmp::Ordering {
    if a.is_ascii() && b.is_ascii() {
        a.cmp(b)
    } else {
        a.encode_utf16().cmp(b.encode_utf16())
    }
}
#[derive(Eq, PartialEq)]
pub struct TextOrder(pub String);
impl Ord for TextOrder {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        compare_text(&self.0, &other.0)
    }
}
impl PartialOrd for TextOrder {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}
