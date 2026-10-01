use crate::{
    config::Config,
    filesystem::relative,
    model::{FileRecord, Node, hash, language},
};
use anyhow::{Context, Result, bail};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::PathBuf,
};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWriteExt},
    process::Command,
};
pub fn executable(c: &Config, name: &str) -> Result<PathBuf> {
    let name = c.runtime(name);
    let p = which::which(&name).with_context(|| format!("Native executable not found: {name}"))?;
    if ["cmd", "bat", "ps1"].iter().any(|x| {
        p.extension()
            .is_some_and(|e| e.to_string_lossy().eq_ignore_ascii_case(x))
    }) {
        bail!("runtime must be a native executable")
    }
    Ok(p)
}
pub fn dart(c: &Config) -> Result<PathBuf> {
    let native = if cfg!(windows) { "dart.exe" } else { "dart" };
    if let Some(sdk) = &c.sdk_path {
        return executable(c, &c.path(sdk).join("bin").join(native).to_string_lossy());
    }
    let path = which::which(c.runtime(&c.dart_path))?;
    // Flutter's known wrapper layout is resolved to its native SDK, never executed.
    if let Some(parent) = path.parent() {
        let sdk = parent.join("cache/dart-sdk/bin").join(native);
        if sdk.is_file() {
            return executable(c, &sdk.to_string_lossy());
        }
        let sdk = parent.join(native);
        if cfg!(windows) && sdk.is_file() {
            return executable(c, &sdk.to_string_lossy());
        }
    }
    executable(c, &c.dart_path)
}
pub fn python(c: &Config) -> String {
    c.python_path.clone().unwrap_or_else(|| {
        let path = c.assets().join(if cfg!(windows) {
            "semantic/.venv/Scripts/python.exe"
        } else {
            "semantic/.venv/bin/python"
        });
        if path.is_file() {
            path.to_string_lossy().into()
        } else if cfg!(windows) {
            "python".into()
        } else {
            "python3".into()
        }
    })
}
pub fn sdk(c: &Config) -> Option<PathBuf> {
    if let Some(p) = &c.sdk_path {
        return Some(c.path(p));
    }
    let dart = dart(c).ok()?.canonicalize().ok()?;
    let parent = dart.parent()?;
    for path in [parent.join(".."), parent.join("cache/dart-sdk")] {
        if path.join("version").is_file() {
            return path.canonicalize().ok();
        }
    }
    None
}
pub fn analyzer(c: &Config) -> String {
    if c.rust_analyzer_path != "rust-analyzer" {
        return c.runtime(&c.rust_analyzer_path);
    }
    let path = c.assets().join(if cfg!(windows) {
        "semantic/.tools/rust-analyzer.exe"
    } else {
        "semantic/.tools/rust-analyzer"
    });
    if path.is_file() {
        path.to_string_lossy().into()
    } else {
        c.rust_analyzer_path.clone()
    }
}
async fn bounded<R: AsyncRead + Unpin>(mut input: R, limit: usize, fatal: bool) -> Result<Vec<u8>> {
    let mut out = Vec::new();
    let mut buf = [0; 16384];
    loop {
        let n = input.read(&mut buf).await?;
        if n == 0 {
            break;
        }
        if fatal && out.len() + n > limit {
            bail!("Response exceeds 64 MiB")
        }
        let allowed = (limit - out.len()).min(n);
        out.extend_from_slice(&buf[..allowed]);
    }
    Ok(out)
}
pub async fn run(c: &Config, command: &[String], input: &str) -> Result<String> {
    let exe = executable(c, &command[0])?;
    let mut cmd = Command::new(exe);
    cmd.args(&command[1..])
        .current_dir(&c.root)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .env("DASH__SUPPRESS_ANALYTICS", "true");
    if let Ok(go) = executable(c, &c.go_path)
        && let Some(parent) = go.parent()
    {
        let mut paths = vec![parent.to_owned()];
        paths.extend(std::env::split_paths(
            &std::env::var_os("PATH").unwrap_or_default(),
        ));
        cmd.env("PATH", std::env::join_paths(paths)?);
    }
    let mut cmd = process_wrap::tokio::CommandWrap::from(cmd);
    cmd.wrap(process_wrap::tokio::KillOnDrop);
    #[cfg(unix)]
    cmd.wrap(process_wrap::tokio::ProcessGroup::leader());
    #[cfg(windows)]
    cmd.wrap(process_wrap::tokio::JobObject);
    let mut child = cmd.spawn()?;
    let mut stdin = child.stdin().take().context("provider stdin")?;
    let stdout = child.stdout().take().context("provider stdout")?;
    let stderr = child.stderr().take().context("provider stderr")?;
    let result = tokio::time::timeout(
        std::time::Duration::from_secs(c.provider_timeout_seconds),
        async {
            let write = async move {
                stdin.write_all(input.as_bytes()).await?;
                stdin.shutdown().await?;
                drop(stdin);
                Ok::<_, anyhow::Error>(())
            };
            let (_, out, errors, status) = tokio::try_join!(
                write,
                bounded(stdout, 64 * 1024 * 1024, true),
                bounded(stderr, 8192, false),
                async { Ok::<_, anyhow::Error>(child.wait().await?) }
            )?;
            if !status.success() {
                bail!("Exit {status}: {}", String::from_utf8_lossy(&errors))
            }
            Ok(String::from_utf8(out)?)
        },
    )
    .await;
    match result {
        Ok(Ok(s)) => Ok(s),
        other => {
            let _ = child.start_kill();
            let _ = child.wait().await;
            match other {
                Ok(Err(e)) => Err(e),
                _ => bail!("Timed out after {}s", c.provider_timeout_seconds),
            }
        }
    }
}
pub fn fingerprint(c: &Config) -> Result<String> {
    let mut values = BTreeMap::new();
    for key in [
        "GOFLAGS",
        "GOOS",
        "GOARCH",
        "CGO_ENABLED",
        "GOWORK",
        "GOTOOLCHAIN",
        "SDKROOT",
        "DEVELOPER_DIR",
        "TOOLCHAINS",
    ] {
        values.insert(key.into(), std::env::var(key).unwrap_or_default());
    }
    for e in walkdir::WalkDir::new(c.assets())
        .follow_links(false)
        .into_iter()
        .filter_entry(|e| {
            !e.file_type().is_dir()
                || ![
                    "node_modules",
                    ".venv",
                    ".dart_tool",
                    ".tools",
                    "__pycache__",
                    ".ruff_cache",
                    ".mypy_cache",
                ]
                .contains(&e.file_name().to_string_lossy().as_ref())
        })
    {
        let e = e?;
        if e.file_type().is_file() {
            values.insert(
                format!("asset:{}", relative(&c.assets(), e.path())),
                hash(fs::read(e.path())?),
            );
        }
    }
    for asset in [
        "typescript/node_modules/typescript/package.json",
        "semantic/.installed.json",
        "kotlin/.tools/installed.json",
        "kotlin/.tools/graph-plugin.jar",
        "dart/build/graph",
        "dart/build/graph.exe",
    ] {
        let p = c.assets().join(asset);
        if p.is_file() {
            values.insert(asset.into(), hash(fs::read(p)?));
        }
    }
    for name in [
        &c.node_path,
        &c.java_path,
        &c.go_path,
        &c.dart_path,
        &python(c),
        &analyzer(c),
        &c.swiftc_path,
    ] {
        let info = executable(c, name)
            .ok()
            .and_then(|p| {
                p.metadata()
                    .ok()
                    .map(|m| format!("{}:{}:{:?}", p.display(), m.len(), m.modified().ok()))
            })
            .unwrap_or_default();
        values.insert(format!("runtime:{name}"), info);
    }
    if let Some(sdk) = sdk(c) {
        let p = sdk.join("version");
        if p.is_file() {
            values.insert("dart_sdk".into(), hash(fs::read(p)?));
        }
    }
    Ok(hash(serde_json::to_vec(&values)?))
}
pub fn doctor(c: &Config) -> Value {
    let assets = c.assets();
    let state: Value = fs::read(assets.join("semantic/.installed.json"))
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or(json!({}));
    let has = |name: &str| executable(c, name).is_ok();
    json!({"providers_path":assets,"dart":{"available":sdk(c).is_some_and(|p|p.join("version").is_file())&&(dart(c).is_ok()&&assets.join("dart/bin/graph.dart").is_file()||assets.join(if cfg!(windows){"dart/build/graph.exe"}else{"dart/build/graph"}).is_file()),"engine":"Dart Analyzer 13.3.0"},"typescript_javascript":{"available":has(&c.node_path)&&assets.join("typescript/node_modules/typescript/package.json").is_file(),"engine":"TypeScript compiler API","runtime":c.node_path},"java":{"available":has(&c.java_path)&&assets.join("java/Graph.java").is_file(),"engine":"javac Trees","runtime":c.java_path},"go":{"available":has(&c.go_path)&&assets.join(if cfg!(windows){"go/graph.exe"}else{"go/graph"}).is_file(),"engine":"go/packages + go/types","runtime":c.go_path},"python":{"available":has(&python(c))&&(c.python_path.is_some()||!state["jedi"].is_null()),"engine":"Python AST + Jedi 0.20.0","runtime":python(c)},"rust":{"available":has(&python(c))&&has(&analyzer(c)),"engine":"rust-analyzer LSP + HIR","runtime":analyzer(c),"build_scripts":false,"proc_macros":false},"swift":{"available":has(&python(c))&&has(&c.swiftc_path),"engine":"Swift 6.2+ semantic JSON AST","runtime":c.swiftc_path},"objectivec":{"available":has(&python(c))&&(c.libclang_path.as_ref().is_some_and(|p|c.path(p).is_file())||!state["libclang"].is_null()),"engine":"libclang canonical cursors","runtime":c.libclang_path.clone().unwrap_or("adapter libclang".into())},"kotlin":{"available":has(&python(c))&&has(&c.java_path)&&assets.join("kotlin/.tools/graph-plugin.jar").is_file(),"engine":"Kotlin K2 2.3.10 resolved IR","runtime":c.java_path}})
}
pub async fn extract(
    c: &Config,
    hashes: &BTreeMap<String, String>,
    emit: &BTreeSet<String>,
) -> Result<BTreeMap<String, FileRecord>> {
    let mut output = BTreeMap::new();
    for lang in [
        "dart",
        "typescript",
        "java",
        "go",
        "python",
        "rust",
        "swift",
        "objectivec",
        "kotlin",
    ] {
        let matches =
            |f: &str| language(f) == lang || (lang == "typescript" && language(f) == "javascript");
        let selected: Vec<_> = emit.iter().filter(|f| matches(f)).cloned().collect();
        if selected.is_empty() {
            continue;
        }
        let assets = c.assets();
        let command: Vec<String> = match lang {
            "dart" => {
                let binary = assets.join(if cfg!(windows) {
                    "dart/build/graph.exe"
                } else {
                    "dart/build/graph"
                });
                if binary.is_file() {
                    vec![binary.to_string_lossy().into()]
                } else {
                    vec![
                        dart(c)
                            .map(|p| p.to_string_lossy().into_owned())
                            .unwrap_or_else(|_| c.runtime(&c.dart_path)),
                        assets.join("dart/bin/graph.dart").to_string_lossy().into(),
                    ]
                }
            }
            "typescript" => vec![
                c.node_path.clone(),
                assets.join("typescript/index.cjs").to_string_lossy().into(),
            ],
            "java" => vec![
                c.java_path.clone(),
                "--source".into(),
                "17".into(),
                assets.join("java/Graph.java").to_string_lossy().into(),
            ],
            "go" => vec![
                assets
                    .join(if cfg!(windows) {
                        "go/graph.exe"
                    } else {
                        "go/graph"
                    })
                    .to_string_lossy()
                    .into(),
            ],
            _ => vec![
                python(c),
                "-I".into(),
                "-X".into(),
                "utf8".into(),
                assets.join("semantic/index.py").to_string_lossy().into(),
                format!("--{lang}"),
            ],
        };
        let context: Vec<_> = hashes
            .iter()
            .filter(|(f, _)| matches(f))
            .map(|(f, h)| json!({"file":f,"hash":h}))
            .collect();
        let request = json!({"root":c.root,"files":context,"options":{"emit_files":selected,"flutter":c.flutter,"sdk_path":sdk(c),"classpath":c.java_classpath.iter().map(|p|c.path(p)).collect::<Vec<_>>(),"python_search_paths":c.python_search_paths.iter().map(|p|c.path(p)).collect::<Vec<_>>(),"rust_analyzer_path":executable(c,&analyzer(c)).ok().unwrap_or_else(||PathBuf::from(analyzer(c))),"rust_cfg":c.rust_cfg,"rust_sysroot_src":c.rust_sysroot_src.as_ref().map(|p|c.path(p)),"swiftc_path":c.runtime(&c.swiftc_path),"java_path":c.runtime(&c.java_path),"libclang_path":c.libclang_path.as_ref().map(|p|c.path(p)),"mobile_project_path":c.mobile_project_path,"adapter_directory":assets.join("semantic"),"timeout":c.provider_timeout_seconds,"max_file_bytes":c.max_file_bytes}});
        let batch = async {
            let data = run(c, &command, &request.to_string()).await?;
            let mut records: Vec<FileRecord> = serde_json::from_str(&data)?;
            let wanted: BTreeSet<_> = selected.iter().cloned().collect();
            let mut seen = BTreeSet::new();
            for r in &mut records {
                if !wanted.contains(&r.file)
                    || !seen.insert(r.file.clone())
                    || hashes.get(&r.file) != Some(&r.hash)
                {
                    bail!("Provider returned unexpected or stale file")
                }
                c.safe(&r.file)?;
                let text = fs::read_to_string(c.safe(&r.file)?)?;
                let units = match language(&r.file) {
                    "dart" | "typescript" | "javascript" | "java" => text.encode_utf16().count(),
                    "go" => text.len(),
                    _ => text.chars().count(),
                };
                let lines = text.split('\n').count();
                let mut ids = BTreeSet::new();
                for n in &r.nodes {
                    if !ids.insert(n.id.clone()) {
                        bail!("Duplicate provider symbol");
                    }
                    if n.kind == "external" {
                        if n.id != format!("uri::{}", n.file)
                            || n.offset != 0
                            || n.length != 0
                            || n.line != 0
                            || n.end != 0
                        {
                            bail!("Invalid external directive node");
                        }
                    } else if n.file != r.file
                        || n.line == 0
                        || n.end < n.line
                        || n.end > lines
                        || !n.id.starts_with(&format!("{}::", r.file))
                        || n.offset.checked_add(n.length).is_none_or(|end| end > units)
                    {
                        bail!("Invalid provider symbol location");
                    }
                }
                for e in &r.edges {
                    if e.file != r.file || e.line == 0 || e.confidence != "resolved" {
                        bail!("Invalid provider relation")
                    }
                }
                r.nodes.sort_by(|a, b| a.id.cmp(&b.id));
                r.edges.sort_by_key(|e| e.key());
                r.diagnostics.sort_by_key(Value::to_string);
            }
            if seen != wanted {
                bail!("Provider omitted indexed files")
            }
            Ok::<_, anyhow::Error>(records)
        }
        .await;
        match batch {
            Ok(records) => {
                for r in records {
                    output.insert(r.file.clone(), r);
                }
            }
            Err(e) => {
                for file in &selected {
                    let text = fs::read_to_string(c.safe(file)?)?;
                    output.insert(file.clone(),FileRecord{file:file.clone(),hash:hashes[file].clone(),nodes:vec![Node{id:format!("{file}::file"),name:file.clone(),qualified:file.clone(),kind:"file".into(),file:file.clone(),line:1,end:text.split('\n').count(),offset:0,length:text.encode_utf16().count(),parent:None,tags:vec![],synthetic:false}],edges:vec![],dependencies:vec![],diagnostics:vec![json!({"severity":"error","code":"provider_unavailable","message":format!("{lang} provider: {e:#}").chars().take(2000).collect::<String>(),"line":1})],unresolved_calls:0});
                }
            }
        }
    }
    Ok(output)
}
