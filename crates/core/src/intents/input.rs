use anyhow::{Result, bail};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Intent {
    Rename,
    ChangeSignature,
    FindTests,
    ReviewChange,
    ExplainSymbol,
    TraceFlow,
    MoveSymbol,
    RemoveSymbol,
    ReplaceDependency,
    ExtractSymbol,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Budget {
    pub max_chars: usize,
    pub max_items: usize,
    pub max_files: usize,
    pub max_traversal: usize,
}
impl Default for Budget {
    fn default() -> Self {
        Self {
            max_chars: 12000,
            max_items: 40,
            max_files: 12,
            max_traversal: 10000,
        }
    }
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Rename {
    pub new_name: Option<String>,
    pub scope: Option<String>,
    pub include_impact: bool,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Signature {
    pub added_parameters: Vec<String>,
    pub removed_parameters: Vec<String>,
    pub renamed_parameters: std::collections::BTreeMap<String, String>,
    pub required: Option<bool>,
    pub return_type: Option<String>,
    pub asynchronous: Option<bool>,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Tests {
    pub test_scope: Option<String>,
    pub framework: Option<String>,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Review {
    pub files: Vec<String>,
    pub baseline: Option<String>,
    pub capture_baseline: bool,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Explain {
    pub focus: Option<String>,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Flow {
    pub destination: Option<String>,
    pub direction: Option<String>,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Move {
    pub destination: String,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Remove {
    pub group: Vec<String>,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Replace {
    pub replacement: Option<String>,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Extract {
    pub file: String,
    pub start_line: usize,
    pub end_line: usize,
    pub kind: Option<String>,
}
#[derive(Debug, Clone, Serialize)]
#[serde(untagged)]
pub enum Options {
    Rename(Rename),
    Signature(Signature),
    Tests(Tests),
    Review(Review),
    Explain(Explain),
    Flow(Flow),
    Move(Move),
    Remove(Remove),
    Replace(Replace),
    Extract(Extract),
}
#[derive(Debug, Clone, Serialize)]
pub struct Request {
    pub intent: Intent,
    pub target: String,
    pub options: Options,
    pub budget: Budget,
    pub depth: usize,
    pub detail: Option<String>,
}
impl Request {
    pub fn parse(a: &Value) -> Result<Self> {
        let intent: Intent = serde_json::from_value(a["intent"].clone())?;
        let target = a["target"]
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("target required"))?
            .to_owned();
        if target.is_empty() || target.len() > 4096 {
            bail!("Invalid target")
        }
        let options = a.get("options").cloned().unwrap_or(json!({}));
        let options = match intent {
            Intent::Rename => Options::Rename(serde_json::from_value(options)?),
            Intent::ChangeSignature => Options::Signature(serde_json::from_value(options)?),
            Intent::FindTests => Options::Tests(serde_json::from_value(options)?),
            Intent::ReviewChange => Options::Review(serde_json::from_value(options)?),
            Intent::ExplainSymbol => Options::Explain(serde_json::from_value(options)?),
            Intent::TraceFlow => Options::Flow(serde_json::from_value(options)?),
            Intent::MoveSymbol => Options::Move(serde_json::from_value(options)?),
            Intent::RemoveSymbol => Options::Remove(serde_json::from_value(options)?),
            Intent::ReplaceDependency => Options::Replace(serde_json::from_value(options)?),
            Intent::ExtractSymbol => Options::Extract(serde_json::from_value(options)?),
        };
        let budget: Budget = a
            .get("budget")
            .map(|v| serde_json::from_value(v.clone()))
            .transpose()?
            .unwrap_or_default();
        if !(3000..=100000).contains(&budget.max_chars)
            || !(1..=200).contains(&budget.max_items)
            || !(1..=32).contains(&budget.max_files)
            || !(1..=100000).contains(&budget.max_traversal)
        {
            bail!(
                "Impossible/out-of-range intent budget (chars 3000..100000, items 1..200, files 1..32, traversal 1..100000)"
            )
        }
        let depth = a["depth"].as_u64().unwrap_or(2) as usize;
        if !(1..=32).contains(&depth) {
            bail!("depth must be 1..32")
        }
        for legacy in ["offset", "limit", "include_snippet"] {
            if a.get(legacy).is_some() {
                bail!("{legacy} is for inspect_change without intent; use budget/cursor")
            }
        }
        match &options {
            Options::Rename(v) => {
                if let Some(n) = &v.new_name {
                    identifier(n)?;
                }
            }
            Options::Signature(v) => {
                if v.added_parameters.len()
                    + v.removed_parameters.len()
                    + v.renamed_parameters.len()
                    > 32
                {
                    bail!("Too many parameter changes")
                }
                for n in v
                    .added_parameters
                    .iter()
                    .chain(&v.removed_parameters)
                    .chain(v.renamed_parameters.keys())
                    .chain(v.renamed_parameters.values())
                {
                    identifier(n)?;
                }
                if v.return_type.as_ref().is_some_and(|s| s.len() > 512) {
                    bail!("return_type too long")
                }
            }
            Options::Explain(v)
                if v.focus.as_ref().is_some_and(|s| {
                    !["contract", "implementation", "dependencies"].contains(&s.as_str())
                }) =>
            {
                bail!("Unknown focus")
            }
            Options::Flow(v)
                if v.direction
                    .as_ref()
                    .is_some_and(|s| !["in", "out"].contains(&s.as_str())) =>
            {
                bail!("direction must be in/out")
            }
            Options::Review(v)
                if v.files.len() > 32 || (v.capture_baseline && v.baseline.is_some()) =>
            {
                bail!("Invalid baseline/files options")
            }
            Options::Remove(v) if v.group.len() > 32 => bail!("group exceeds 32 targets"),
            Options::Extract(v)
                if v.start_line == 0
                    || v.end_line < v.start_line
                    || v.kind
                        .as_ref()
                        .is_some_and(|s| !["function", "component"].contains(&s.as_str())) =>
            {
                bail!("Invalid extraction region/kind")
            }
            _ => {}
        }
        Ok(Self {
            intent,
            target,
            options,
            budget,
            depth,
            detail: a["detail"].as_str().map(str::to_owned),
        })
    }
}
fn identifier(name: &str) -> Result<()> {
    let mut chars = name.chars();
    if !chars
        .next()
        .is_some_and(|c| c == '_' || c == '$' || c.is_alphabetic())
        || name.chars().count() > 128
        || !chars.all(|c| c == '_' || c == '$' || c.is_alphanumeric())
    {
        bail!("new/parameter name must be an identifier; compiler validity remains unverified")
    }
    Ok(())
}
