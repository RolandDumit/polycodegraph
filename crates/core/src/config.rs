use crate::model::hash;
use anyhow::{Context, Result, bail};
use globset::{Glob, GlobSet, GlobSetBuilder};
use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::{Component, Path, PathBuf},
};
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ResponseProfile {
    #[default]
    Legacy,
    Compact,
}
impl ResponseProfile {
    fn is_legacy(&self) -> bool {
        *self == Self::Legacy
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    #[serde(skip)]
    pub root: PathBuf,
    #[serde(skip)]
    pub config_file: Option<PathBuf>,
    pub include: Vec<String>,
    pub exclude: Vec<String>,
    pub cache: String,
    pub flutter: bool,
    pub sdk_path: Option<String>,
    pub providers_path: Option<String>,
    pub dart_path: String,
    pub node_path: String,
    pub java_path: String,
    pub go_path: String,
    pub python_path: Option<String>,
    pub rust_analyzer_path: String,
    pub rust_sysroot_src: Option<String>,
    pub swiftc_path: String,
    pub libclang_path: Option<String>,
    pub mobile_project_path: String,
    pub python_search_paths: Vec<String>,
    pub rust_cfg: Vec<String>,
    pub java_classpath: Vec<String>,
    pub max_results: usize,
    pub max_snippet_lines: usize,
    pub max_snippet_chars: usize,
    pub max_file_bytes: usize,
    pub provider_timeout_seconds: u64,
    pub watch: bool,
    pub watch_debounce_ms: u64,
    pub reconcile_interval_seconds: u64,
    #[serde(skip_serializing_if = "ResponseProfile::is_legacy")]
    pub response_profile: ResponseProfile,
    #[serde(skip)]
    pub response_profile_override: Option<ResponseProfile>,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            root: PathBuf::new(),
            config_file: None,
            include: [
                "dart", "ts", "tsx", "js", "jsx", "mjs", "cjs", "java", "go", "py", "pyi", "rs",
                "swift", "kt", "h", "m", "mm",
            ]
            .iter()
            .map(|x| format!("**/*.{x}"))
            .collect(),
            exclude: vec![
                "**/.git/**".into(),
                "**/.dart_tool/**".into(),
                "**/build/**".into(),
                "**/.polycodegraph/**".into(),
            ],
            cache: ".polycodegraph".into(),
            flutter: true,
            sdk_path: None,
            providers_path: None,
            dart_path: "dart".into(),
            node_path: "node".into(),
            java_path: "java".into(),
            go_path: "go".into(),
            python_path: None,
            rust_analyzer_path: "rust-analyzer".into(),
            rust_sysroot_src: None,
            swiftc_path: "swiftc".into(),
            libclang_path: None,
            mobile_project_path: "polycodegraph.mobile.json".into(),
            python_search_paths: vec![],
            rust_cfg: vec![],
            java_classpath: vec![],
            max_results: 200,
            max_snippet_lines: 120,
            max_snippet_chars: 16000,
            max_file_bytes: 2097152,
            provider_timeout_seconds: 120,
            watch: true,
            watch_debounce_ms: 200,
            reconcile_interval_seconds: 30,
            response_profile: ResponseProfile::Legacy,
            response_profile_override: None,
        }
    }
}
impl Config {
    pub fn load(root: &Path, explicit: Option<&Path>) -> Result<Self> {
        let root = dunce::canonicalize(root).context("repository root must exist")?;
        if !root.is_dir() {
            bail!("repository root must be a directory")
        }
        let config_file = explicit.map(|p| {
            if p.is_absolute() {
                p.to_owned()
            } else {
                root.join(p)
            }
        });
        let path = explicit
            .map(|p| {
                if p.is_absolute() {
                    p.to_owned()
                } else {
                    root.join(p)
                }
            })
            .or_else(|| {
                [
                    "polycodegraph.yaml",
                    "polycodegraph.yml",
                    "polycodegraph.json",
                ]
                .iter()
                .map(|x| root.join(x))
                .find(|p| p.is_file())
            });
        let mut c: Self = if let Some(p) = path {
            let text = fs::read_to_string(&p)?;
            if p.extension().is_some_and(|e| e == "json") {
                serde_json::from_str(&text)?
            } else {
                serde_yaml::from_str(&text)?
            }
        } else {
            Self::default()
        };
        c.root = root;
        c.config_file = config_file;
        c.validate()?;
        Ok(c)
    }
    pub fn disk_fingerprint(&self) -> Result<String> {
        let candidates = self
            .config_file
            .clone()
            .map(|p| vec![p])
            .unwrap_or_else(|| {
                [
                    "polycodegraph.yaml",
                    "polycodegraph.yml",
                    "polycodegraph.json",
                ]
                .iter()
                .map(|p| self.root.join(p))
                .collect()
            });
        let mut values = Vec::new();
        for path in candidates {
            values.push((
                path.to_string_lossy().into_owned(),
                if path.exists() {
                    Some(hash(fs::read(path)?))
                } else {
                    None
                },
            ));
        }
        Ok(hash(serde_json::to_vec(&values)?))
    }
    pub fn validate(&self) -> Result<()> {
        if self.cache.is_empty() || self.cache == "." {
            bail!("cache must be a directory inside the repository")
        }
        self.safe(&self.cache)?;
        self.safe(&self.mobile_project_path)?;
        if [
            self.max_results,
            self.max_snippet_lines,
            self.max_snippet_chars,
            self.max_file_bytes,
        ]
        .contains(&0)
            || self.provider_timeout_seconds == 0
            || self.reconcile_interval_seconds == 0
        {
            bail!("limits must be positive")
        }
        self.globs()?;
        Ok(())
    }
    pub fn safe(&self, name: &str) -> Result<PathBuf> {
        let p = Path::new(name);
        if p.is_absolute() {
            bail!("path must be repository-relative")
        }
        let mut out = self.root.clone();
        for c in p.components() {
            match c {
                Component::Normal(s) => out.push(s),
                Component::CurDir => {}
                _ => bail!("path escapes repository"),
            };
            if let Ok(m) = fs::symlink_metadata(&out)
                && m.file_type().is_symlink()
            {
                bail!("symlink paths are not allowed")
            }
        }
        if out == self.root {
            bail!("choose a path inside the repository")
        }
        Ok(out)
    }
    pub fn path(&self, name: &str) -> PathBuf {
        let p = Path::new(name);
        if p.is_absolute() {
            p.to_owned()
        } else {
            self.root.join(p)
        }
    }
    pub fn runtime(&self, name: &str) -> String {
        if name.contains('/') || name.contains('\\') {
            self.path(name).to_string_lossy().into()
        } else {
            name.into()
        }
    }
    pub fn globs(&self) -> Result<(GlobSet, GlobSet)> {
        fn build(v: &[String]) -> Result<GlobSet> {
            let mut b = GlobSetBuilder::new();
            for s in v {
                b.add(Glob::new(s)?);
            }
            Ok(b.build()?)
        }
        Ok((build(&self.include)?, build(&self.exclude)?))
    }
    pub fn fingerprint(&self) -> Result<String> {
        // Presentation changes must not invalidate semantic records or the 0.5 cache.
        let mut value = serde_json::to_value(self)?;
        value
            .as_object_mut()
            .expect("configuration object")
            .remove("response_profile");
        Ok(hash(serde_json::to_vec(&value)?))
    }
    pub fn compact(&self, args: &serde_json::Value) -> bool {
        match args["detail"].as_str() {
            Some("full") => false,
            Some("compact") => true,
            _ => self.response_profile == ResponseProfile::Compact,
        }
    }
    pub fn assets(&self) -> PathBuf {
        if let Some(p) = &self.providers_path {
            return self.path(p);
        }
        if let Ok(exe) = std::env::current_exe()
            && let Some(dir) = exe.parent()
        {
            for p in [
                dir.join("providers"),
                dir.join("../providers"),
                dir.join("../../providers"),
            ] {
                if p.is_dir() {
                    return p;
                }
            }
        }
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../providers")
    }
}
