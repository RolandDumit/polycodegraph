use crate::{
    config::Config,
    model::{hash, language},
};
use anyhow::{Context, Result};
use std::{collections::BTreeMap, fs, path::Path};
use walkdir::WalkDir;
pub const IGNORED: &[&str] = &[
    ".git",
    ".dart_tool",
    ".polycodegraph",
    "build",
    "node_modules",
    "vendor",
    "target",
    "dist",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".tox",
    ".nox",
    ".build",
    ".gradle",
    "DerivedData",
    ".tools",
];
pub fn relative(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}
pub fn manifest(name: &str) -> bool {
    [
        "pubspec.yaml",
        "pubspec.lock",
        "analysis_options.yaml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "go.mod",
        "go.sum",
        "go.work",
        "go.work.sum",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "gradle.properties",
        "pyproject.toml",
        "requirements.txt",
        "requirements.lock",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "uv.lock",
        "setup.cfg",
        "setup.py",
        "Cargo.toml",
        "Cargo.lock",
        "rust-project.json",
        "Package.swift",
        "Package.resolved",
        "project.pbxproj",
        "libs.versions.toml",
        "rust-toolchain",
        "rust-toolchain.toml",
        "jsconfig.json",
        "polycodegraph.yaml",
        "polycodegraph.yml",
        "polycodegraph.json",
    ]
    .contains(&name)
        || name.starts_with("tsconfig")
        || name.ends_with(".xcconfig")
}
#[derive(Debug, Clone, Default)]
pub struct Scan {
    pub hashes: BTreeMap<String, String>,
    pub environment: BTreeMap<String, String>,
    pub skipped: Vec<String>,
    pub scopes: BTreeMap<String, String>,
}
pub fn scope(c: &Config, file: &str) -> String {
    let l = language(file);
    let l = if l == "javascript" { "typescript" } else { l };
    if ["swift", "objectivec", "kotlin"].contains(&l)
        && let Ok(path) = c.safe(&c.mobile_project_path)
        && let Ok(bytes) = fs::read(path)
        && let Ok(model) = serde_json::from_slice::<serde_json::Value>(&bytes)
        && let Some(modules) = model[l].as_array()
    {
        for (index, module) in modules.iter().enumerate() {
            if module["files"].as_array().is_some_and(|patterns| {
                patterns
                    .iter()
                    .filter_map(serde_json::Value::as_str)
                    .any(|pattern| {
                        globset::Glob::new(pattern)
                            .is_ok_and(|g| g.compile_matcher().is_match(file))
                    })
            }) {
                return format!("{l}:module:{index}");
            }
        }
    }
    let markers: &[&str] = match l {
        "dart" => &["pubspec.yaml"],
        "typescript" => &["tsconfig.json", "jsconfig.json"],
        "go" => &["go.mod"],
        "rust" => &["Cargo.toml"],
        _ => &[],
    };
    let mut d = c.root.join(file);
    d.pop();
    while d.starts_with(&c.root) {
        if markers.iter().any(|m| d.join(m).is_file()) {
            return format!("{l}:{}", relative(&c.root, &d));
        }
        if !d.pop() {
            break;
        }
    }
    format!("{l}:.")
}
pub fn scan(c: &Config) -> Result<Scan> {
    let (inc, exc) = c.globs()?;
    let cache = c.safe(&c.cache)?;
    let mut s = Scan::default();
    for e in WalkDir::new(&c.root)
        .follow_links(false)
        .sort_by_file_name()
        .into_iter()
        .filter_entry(|e| {
            e.depth() == 0
                || !e.file_type().is_dir()
                || (!IGNORED.contains(&e.file_name().to_string_lossy().as_ref())
                    && e.path() != cache)
        })
    {
        let e = e?;
        if e.depth() == 0 {
            continue;
        }
        let rel = relative(&c.root, e.path());
        if e.file_type().is_symlink() {
            s.skipped.push(rel);
            continue;
        }
        if !e.file_type().is_file() {
            continue;
        }
        let name = e.file_name().to_string_lossy();
        let lang = language(&rel);
        let env = manifest(&name) || rel == c.mobile_project_path;
        if lang == "unknown" && !env {
            continue;
        }
        let size = e.metadata()?.len();
        if lang != "unknown" && size > c.max_file_bytes as u64 {
            s.skipped.push(rel);
            continue;
        }
        let bytes = fs::read(e.path()).with_context(|| format!("reading {rel}"))?;
        let h = hash(bytes);
        if lang != "unknown" && inc.is_match(&rel) && !exc.is_match(&rel) {
            s.scopes.insert(rel.clone(), scope(c, &rel));
            s.hashes.insert(rel.clone(), h.clone());
        } else {
            s.environment.insert(rel.clone(), h.clone());
        }
        if env {
            s.environment.insert(rel, h);
        }
    }
    // Track package configuration without traversing SDK/build output.
    for e in WalkDir::new(&c.root)
        .follow_links(false)
        .into_iter()
        .filter_entry(|e| {
            e.depth() == 0
                || !e.file_type().is_dir()
                || !IGNORED
                    .iter()
                    .filter(|x| **x != ".dart_tool")
                    .any(|x| e.file_name() == *x)
        })
    {
        let e = e?;
        if e.file_type().is_dir() && e.file_name() == ".dart_tool" {
            let f = e.path().join("package_config.json");
            if f.is_file() && !fs::symlink_metadata(&f)?.file_type().is_symlink() {
                s.environment
                    .insert(relative(&c.root, &f), hash(fs::read(&f)?));
                track_dart_dependencies(c, &f, &mut s.environment)?;
            }
        }
    }
    track_prepared_context(c, &s.scopes, &mut s.environment)?;
    s.skipped.sort();
    Ok(s)
}

fn track_dart_dependencies(
    c: &Config,
    config: &Path,
    environment: &mut BTreeMap<String, String>,
) -> Result<()> {
    let bytes = fs::read(config)?;
    let package_config: serde_json::Value = serde_json::from_slice(&bytes)?;
    let base = url::Url::from_file_path(config)
        .map_err(|_| anyhow::anyhow!("invalid package configuration path"))?;
    for package in package_config["packages"].as_array().into_iter().flatten() {
        let Some(uri) = package["rootUri"].as_str() else {
            continue;
        };
        let Ok(root) = base
            .join(uri)
            .and_then(|u| u.join(package["packageUri"].as_str().unwrap_or("lib/")))
        else {
            continue;
        };
        let Ok(path) = root.to_file_path() else {
            continue;
        };
        if path.starts_with(&c.root) || !path.is_dir() {
            continue;
        }
        for entry in WalkDir::new(&path)
            .follow_links(false)
            .into_iter()
            .filter_entry(|e| {
                !e.file_type().is_dir()
                    || !IGNORED.contains(&e.file_name().to_string_lossy().as_ref())
            })
        {
            let entry = entry?;
            if entry.file_type().is_file() && entry.path().extension().is_some_and(|e| e == "dart")
            {
                environment.insert(
                    format!("external-dart:{}", entry.path().display()),
                    hash_file(entry.path())?,
                );
            }
        }
    }
    Ok(())
}

/// Conservatively map tracked context changes to semantic providers.
pub fn environment_languages(key: &str) -> Vec<&'static str> {
    let name = Path::new(key)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(key);
    if key.starts_with("external-dart:")
        || [
            "pubspec.yaml",
            "pubspec.lock",
            "package_config.json",
            "analysis_options.yaml",
        ]
        .contains(&name)
    {
        return vec!["dart"];
    }
    if key.starts_with("external-mobile:kotlin:") {
        return vec!["kotlin"];
    }
    if key.starts_with("external-mobile:") {
        return vec!["swift", "objectivec"];
    }
    if key.starts_with("external-java:") {
        return vec!["java", "kotlin"];
    }
    if key.starts_with("external-python:") {
        return vec!["python"];
    }
    if key.starts_with("external-node:")
        || [
            "tsconfig.json",
            "jsconfig.json",
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
        ]
        .contains(&name)
    {
        return vec!["typescript", "javascript"];
    }
    if ["go.mod", "go.sum", "go.work", "go.work.sum"].contains(&name) {
        return vec!["go"];
    }
    if ["Cargo.toml", "Cargo.lock", "rust-project.json"].contains(&name)
        || key.starts_with("external-rust:")
    {
        return vec!["rust"];
    }
    if [
        "pyproject.toml",
        "requirements.txt",
        "requirements.lock",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "uv.lock",
        "setup.cfg",
        "setup.py",
    ]
    .contains(&name)
    {
        return vec!["python"];
    }
    if name == "polycodegraph.mobile.json" {
        return vec!["swift", "objectivec", "kotlin"];
    }
    if [
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "gradle.properties",
        "libs.versions.toml",
    ]
    .contains(&name)
    {
        return vec!["java", "kotlin"];
    }
    if ["Package.swift", "Package.resolved", "project.pbxproj"].contains(&name)
        || name.ends_with(".xcconfig")
    {
        return vec!["swift", "objectivec"];
    }
    match language(key) {
        "unknown" => vec!["all"],
        "typescript" | "javascript" => vec!["typescript", "javascript"],
        lang => vec![lang],
    }
}

fn track_tree(
    path: &Path,
    prefix: &str,
    extensions: &[&str],
    environment: &mut BTreeMap<String, String>,
) -> Result<()> {
    if fs::symlink_metadata(path).is_ok_and(|m| m.file_type().is_symlink()) {
        environment.insert(
            format!("{prefix}:{}", path.display()),
            format!("symlink:{}", fs::read_link(path)?.display()),
        );
        return Ok(());
    }
    if !path.exists() {
        environment.insert(format!("{prefix}:{}", path.display()), "missing".into());
        return Ok(());
    }
    for entry in WalkDir::new(path)
        .follow_links(false)
        .into_iter()
        .filter_entry(|e| {
            !e.file_type().is_dir() || !IGNORED.contains(&e.file_name().to_string_lossy().as_ref())
        })
    {
        let entry = entry?;
        if entry.file_type().is_file()
            && (extensions.is_empty()
                || entry
                    .path()
                    .extension()
                    .is_some_and(|e| extensions.iter().any(|x| e == *x)))
        {
            environment.insert(
                format!("{prefix}:{}", entry.path().display()),
                hash_file(entry.path())?,
            );
        }
    }
    Ok(())
}
fn track_prepared_context(
    c: &Config,
    scopes: &BTreeMap<String, String>,
    environment: &mut BTreeMap<String, String>,
) -> Result<()> {
    // Explicit prepared contexts are data only: never resolve/download dependencies.
    if let Some(path) = &c.rust_sysroot_src {
        track_tree(&c.path(path), "external-rust", &["rs"], environment)?;
    }
    let model = c.safe(&c.mobile_project_path)?;
    if model.is_file() {
        let model: serde_json::Value = serde_json::from_slice(&fs::read(model)?)?;
        for lang in ["swift", "objectivec", "kotlin"] {
            for module in model[lang].as_array().into_iter().flatten() {
                for key in [
                    "classpath",
                    "include_paths",
                    "framework_paths",
                    "import_paths",
                ] {
                    for input in module[key]
                        .as_array()
                        .into_iter()
                        .flatten()
                        .filter_map(serde_json::Value::as_str)
                    {
                        track_tree(
                            &c.path(input),
                            &format!("external-mobile:{lang}"),
                            &[
                                "jar",
                                "class",
                                "h",
                                "modulemap",
                                "swiftinterface",
                                "swiftmodule",
                            ],
                            environment,
                        )?;
                    }
                }
                if let Some(input) = module["bridging_header"].as_str() {
                    track_tree(
                        &c.path(input),
                        &format!("external-mobile:{lang}"),
                        &["h"],
                        environment,
                    )?;
                }
            }
        }
    }
    for input in &c.java_classpath {
        track_tree(&c.path(input), "external-java", &[], environment)?;
    }
    for input in &c.python_search_paths {
        track_tree(
            &c.path(input),
            "external-python",
            &["py", "pyi"],
            environment,
        )?;
    }
    let project = c.root.join("rust-project.json");
    if project.is_file() {
        let project: serde_json::Value = serde_json::from_slice(&fs::read(project)?)?;
        for module in project["crates"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|v| v["root_module"].as_str())
        {
            let path = c.path(module);
            if !path.starts_with(&c.root)
                && let Some(parent) = path.parent()
            {
                track_tree(parent, "external-rust", &["rs"], environment)?;
            }
        }
    }
    let directories: std::collections::BTreeSet<_> = scopes
        .values()
        .filter_map(|s| s.strip_prefix("typescript:"))
        .map(|s| c.path(s).join("node_modules"))
        .collect();
    for node in directories {
        if node.is_dir() && !fs::symlink_metadata(&node)?.file_type().is_symlink() {
            for entry in fs::read_dir(node)? {
                let entry = entry?;
                track_tree(
                    &entry.path(),
                    "external-node",
                    &["ts", "tsx", "js", "jsx", "json"],
                    environment,
                )?;
            }
        }
    }
    Ok(())
}

pub fn hash_file(path: &Path) -> Result<String> {
    use sha2::{Digest, Sha256};
    use std::io::Read;
    let mut file = fs::File::open(path)?;
    let mut digest = Sha256::new();
    let mut buffer = [0; 65536];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}
/// Verify known semantic inputs without discovering/scanning the repository.
/// Added inputs and unobserved events are also recovered by reconciliation.
pub fn context_unchanged(
    c: &Config,
    inputs: &BTreeMap<String, String>,
    languages: &std::collections::BTreeSet<&str>,
) -> Result<bool> {
    for (key, expected) in inputs {
        if key == "provider_runtime" {
            if crate::providers::fingerprint(c)? != *expected {
                return Ok(false);
            }
            continue;
        }
        let involved = environment_languages(key);
        if !involved
            .iter()
            .any(|l| *l == "all" || languages.contains(l))
        {
            continue;
        }
        let path = if let Some(path) = key
            .strip_prefix("external-mobile:")
            .and_then(|p| p.split_once(':').map(|(_, p)| p))
        {
            std::path::PathBuf::from(path)
        } else if key.starts_with("external-") {
            std::path::PathBuf::from(key.split_once(':').map_or(key.as_str(), |(_, p)| p))
        } else {
            c.path(key)
        };
        let actual = if expected.starts_with("symlink:") {
            fs::read_link(path)
                .map(|p| format!("symlink:{}", p.display()))
                .ok()
        } else if expected == "missing" && !path.exists() {
            Some("missing".into())
        } else {
            hash_file(&path).ok()
        };
        if actual.as_ref() != Some(expected) {
            return Ok(false);
        }
    }
    Ok(true)
}
