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
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum View {
    Locations,
    Contracts,
    EditContext,
    FullEvidence,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Format {
    Audit,
    Lean,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourcePolicy {
    Intent,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ClientContext {
    pub epoch: String,
    pub root_id: String,
    pub generation: String,
    pub health_fingerprint: String,
    pub environment_fingerprint: String,
    #[serde(default)]
    pub known_windows: Vec<String>,
    #[serde(default)]
    pub rehydrate: bool,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Budget {
    pub max_chars: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_source_chars: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_collection_items: Option<usize>,
    pub max_items: usize,
    pub max_files: usize,
    pub max_traversal: usize,
}
impl Default for Budget {
    fn default() -> Self {
        Self {
            max_chars: 12000,
            max_source_chars: None,
            max_tokens: None,
            max_collection_items: None,
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
    pub include_tests: bool,
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
    pub capture_mode: Option<String>,
    pub strict_scope: bool,
    pub new_files: Vec<String>,
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
    pub view: Option<View>,
    pub context: Option<ClientContext>,
    pub format: Option<Format>,
    pub source_policy: Option<SourcePolicy>,
}
impl Request {
    pub fn lean(&self) -> bool {
        self.format == Some(Format::Lean)
    }
    pub fn parse(a: &Value) -> Result<Self> {
        let format: Option<Format> = a
            .get("format")
            .map(|v| serde_json::from_value(v.clone()))
            .transpose()?;
        let intent: Intent = serde_json::from_value(a["intent"].clone())?;
        let source_policy: Option<SourcePolicy> = a
            .get("source_policy")
            .map(|v| serde_json::from_value(v.clone()))
            .transpose()?;
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
            || budget.max_source_chars.is_some_and(|n| n > 100000)
            || budget
                .max_tokens
                .is_some_and(|n| !(256..=32000).contains(&n))
            || budget
                .max_collection_items
                .is_some_and(|n| !(1..=100000).contains(&n))
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
                if v.files.len() > 32
                    || v.new_files.len() > 32
                    || v.new_files
                        .iter()
                        .collect::<std::collections::BTreeSet<_>>()
                        .len()
                        != v.new_files.len()
                    || (!v.new_files.is_empty()
                        && ((!v.strict_scope && format != Some(Format::Lean))
                            || !v.capture_baseline))
                    || (v.capture_baseline && v.baseline.is_some())
                    || v.capture_mode.as_ref().is_some_and(|mode| {
                        !v.capture_baseline || !["minimal", "context"].contains(&mode.as_str())
                    }) =>
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
        let view = a
            .get("view")
            .map(|v| serde_json::from_value(v.clone()))
            .transpose()?;
        let context: Option<ClientContext> = a
            .get("context")
            .map(|v| serde_json::from_value(v.clone()))
            .transpose()?;
        if context.as_ref().is_some_and(|v| {
            v.epoch.is_empty()
                || v.epoch.len() > 128
                || v.root_id.len() != 64
                || v.known_windows.len() > 256
                || v.known_windows.iter().any(|id| id.len() != 64)
                || v.generation.len() > 128
                || v.health_fingerprint.len() > 128
        }) {
            bail!("Invalid client context identity/window acknowledgement");
        }
        if format == Some(Format::Lean) && context.is_some() {
            bail!("lean results are self-contained; retained-window context requires audit format")
        }
        let mut options = options;
        if format == Some(Format::Lean)
            && let Options::Review(v) = &mut options
        {
            v.strict_scope = true;
        }
        Ok(Self {
            intent,
            target,
            options,
            budget,
            depth,
            detail: a["detail"].as_str().map(str::to_owned),
            view: view.or_else(|| {
                if source_policy == Some(SourcePolicy::Intent) {
                    Some(match intent {
                        Intent::Rename => View::Locations,
                        Intent::ChangeSignature => View::Contracts,
                        _ => View::EditContext,
                    })
                } else {
                    (format == Some(Format::Lean)).then_some(View::EditContext)
                }
            }),
            context,
            format,
            source_policy,
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
