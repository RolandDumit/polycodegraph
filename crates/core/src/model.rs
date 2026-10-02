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
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
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
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
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
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct IntentMetadata {
    #[serde(
        default,
        skip_serializing_if = "Value::is_null",
        deserialize_with = "decode_ast"
    )]
    pub ast: Value,
    #[serde(default)]
    pub symbols: Vec<Node>,
    #[serde(default)]
    pub relations: Vec<Edge>,
    #[serde(default)]
    pub tests: Vec<Value>,
    #[serde(default)]
    pub capabilities: Vec<String>,
}
impl IntentMetadata {
    fn empty(&self) -> bool {
        self.ast.is_null()
            && self.symbols.is_empty()
            && self.relations.is_empty()
            && self.tests.is_empty()
            && self.capabilities.is_empty()
    }
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
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
    #[serde(default, skip_serializing_if = "IntentMetadata::empty")]
    pub intent: IntentMetadata,
}
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
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

// Provider-only compact transport expands once, before validation/publication.
fn decode_ast<'de, D: serde::Deserializer<'de>>(decoder: D) -> Result<Value, D::Error> {
    use serde::de::Error;
    let mut ast = Value::deserialize(decoder)?;
    if ast["format"] != "pcg-ast-1" {
        return Ok(ast);
    }
    let scopes = ast["scopes"]
        .as_array()
        .ok_or_else(|| D::Error::custom("Missing AST scopes"))?
        .clone();
    let scope = |v: &Value| -> Result<Value, D::Error> {
        scopes
            .get(v.as_u64().unwrap_or(u64::MAX) as usize)
            .filter(|v| v.is_string())
            .cloned()
            .ok_or_else(|| D::Error::custom("Invalid AST scope index"))
    };
    let bindings = ast["bindings"]
        .as_array()
        .ok_or_else(|| D::Error::custom("Missing AST bindings"))?
        .clone();
    for (section, width) in [
        ("bindings", 9),
        ("uses", 8),
        ("statements", 6),
        ("controls", 6),
    ] {
        let input = ast[section]
            .as_array()
            .ok_or_else(|| D::Error::custom("Missing AST section"))?;
        let mut output = Vec::with_capacity(input.len());
        for row in input {
            let row = row
                .as_array()
                .filter(|r| r.len() == width)
                .ok_or_else(|| D::Error::custom("Invalid AST row"))?;
            output.push(match section {
                "bindings" => serde_json::json!({"id":row[0],"name":row[1],"kind":row[2],"type":row[3],"line":row[4],"end":row[5],"offset":row[6],"end_offset":row[7],"scope":scope(&row[8])?}),
                "uses" => {
                    let binding = if row[5].is_null() || row[5].is_string() {row[5].clone()} else {bindings.get(row[5].as_u64().unwrap_or(u64::MAX) as usize).and_then(|v|v.get(0)).filter(|v|v.is_string()).cloned().ok_or_else(|| D::Error::custom("Invalid AST binding index"))?};
                    serde_json::json!({"line":row[0],"end":row[1],"offset":row[2],"end_offset":row[3],"scope":scope(&row[4])?,"binding":binding,"read":row[6],"write":row[7]})
                },
                "statements" => serde_json::json!({"line":row[0],"end":row[1],"offset":row[2],"end_offset":row[3],"scope":scope(&row[4])?,"block":row[5]}),
                _ => serde_json::json!({"line":row[0],"end":row[1],"offset":row[2],"end_offset":row[3],"scope":scope(&row[4])?,"kind":row[5]}),
            });
        }
        ast[section] = Value::Array(output);
    }
    if let Some(object) = ast.as_object_mut() {
        object.remove("format");
        object.remove("scopes");
    }
    Ok(ast)
}
