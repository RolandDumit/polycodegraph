use crate::{config::Config, filesystem, model::language, providers};
use anyhow::{Result, bail};
use serde_json::{Value, json};
use std::{collections::BTreeSet, fs, path::Path};
use tokio::process::Command;
async fn invoke(command: &str, args: &[String], cwd: &Path) -> Result<()> {
    let status = Command::new(command)
        .args(args)
        .current_dir(cwd)
        .env("DASH__SUPPRESS_ANALYTICS", "true")
        .status()
        .await?;
    if !status.success() {
        bail!("Setup command failed: {command} ({status})")
    }
    Ok(())
}
fn args(xs: &[&str]) -> Vec<String> {
    xs.iter().map(|s| s.to_string()).collect()
}
pub async fn setup(c: &Config, languages: Option<&str>, dev: bool) -> Result<()> {
    let wanted: BTreeSet<String> = if let Some(l) = languages {
        l.split(',').map(|s| s.trim().to_owned()).collect()
    } else {
        filesystem::scan(c)?
            .hashes
            .keys()
            .map(|f| language(f).into())
            .collect()
    };
    for l in &wanted {
        if ![
            "dart",
            "typescript",
            "javascript",
            "java",
            "go",
            "python",
            "rust",
            "swift",
            "objectivec",
            "kotlin",
        ]
        .contains(&l.as_str())
        {
            bail!("Unknown language: {l}")
        }
    }
    let assets = c.assets();
    let has = |l: &str| wanted.contains(l);
    if has("dart") {
        let dir = assets.join("dart");
        invoke(
            &providers::dart(c)?.to_string_lossy(),
            &args(&["pub", "get", "--enforce-lockfile"]),
            &dir,
        )
        .await?;
        fs::create_dir_all(dir.join("build"))?;
        let output = dir.join(if cfg!(windows) {
            "build/graph.exe"
        } else {
            "build/graph"
        });
        invoke(
            &providers::dart(c)?.to_string_lossy(),
            &[
                "compile".into(),
                "exe".into(),
                "bin/graph.dart".into(),
                "-o".into(),
                output.to_string_lossy().into(),
            ],
            &dir,
        )
        .await?;
    }
    if has("typescript") || has("javascript") {
        let npm = std::env::var("NPM_CLI")
            .ok()
            .map(std::path::PathBuf::from)
            .or_else(|| {
                providers::executable(c, &c.node_path)
                    .ok()
                    .and_then(|node| node.canonicalize().ok())
                    .and_then(|node| {
                        node.parent().and_then(|p| {
                            [
                                p.join("../lib/node_modules/npm/bin/npm-cli.js"),
                                p.join("node_modules/npm/bin/npm-cli.js"),
                            ]
                            .into_iter()
                            .find(|p| p.is_file())
                        })
                    })
            })
            .filter(|p| p.is_file())
            .or_else(|| {
                which::which("npm")
                    .ok()
                    .and_then(|p| p.canonicalize().ok())
                    .filter(|p| p.extension().is_some_and(|e| e == "js"))
            })
            .ok_or_else(|| anyhow::anyhow!("Set NPM_CLI to npm-cli.js"))?;
        invoke(
            &c.runtime(&c.node_path),
            &[
                npm.to_string_lossy().into(),
                "ci".into(),
                "--ignore-scripts".into(),
            ],
            &assets.join("typescript"),
        )
        .await?;
    }
    if has("java") {
        invoke(&c.runtime(&c.java_path), &args(&["-version"]), &assets).await?;
    }
    if has("go") {
        invoke(
            &c.runtime(&c.go_path),
            &args(&["mod", "verify"]),
            &assets.join("go"),
        )
        .await?;
        invoke(
            &c.runtime(&c.go_path),
            &args(&[
                "build",
                "-buildvcs=false",
                "-mod=readonly",
                "-o",
                if cfg!(windows) { "graph.exe" } else { "graph" },
                ".",
            ]),
            &assets.join("go"),
        )
        .await?;
    }
    if ["python", "rust", "swift", "objectivec", "kotlin"]
        .iter()
        .any(|l| has(l))
    {
        let dir = assets.join("semantic");
        let base = std::env::var("PYTHON").unwrap_or(if cfg!(windows) {
            "python".into()
        } else {
            "python3".into()
        });
        let venv = dir.join(".venv");
        if !venv.exists() {
            invoke(
                &base,
                &[
                    "-I".into(),
                    "-m".into(),
                    "venv".into(),
                    venv.to_string_lossy().into(),
                ],
                &assets,
            )
            .await?;
        }
        let py = providers::python(c);
        let state_path = dir.join(".installed.json");
        let mut state: Value = fs::read(&state_path)
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or(json!({}));
        if has("python") || has("objectivec") {
            for (lang, lock) in [
                ("python", "requirements.lock"),
                ("objectivec", "requirements-mobile.lock"),
            ] {
                if has(lang) {
                    invoke(
                        &py,
                        &[
                            "-I".into(),
                            "-m".into(),
                            "pip".into(),
                            "install".into(),
                            "--disable-pip-version-check".into(),
                            "--require-hashes".into(),
                            "--only-binary=:all:".into(),
                            "-r".into(),
                            dir.join(lock).to_string_lossy().into(),
                        ],
                        &dir,
                    )
                    .await?;
                }
            }
            if has("python") {
                state["jedi"] = json!("0.20.0");
                state["parso"] = json!("0.8.7");
            }
            if has("objectivec") {
                state["libclang"] = json!("18.1.1");
            }
        }
        if has("rust") {
            if std::env::var("RUST_ANALYZER").is_err() {
                invoke(
                    &py,
                    &[
                        "-I".into(),
                        dir.join("setup_rust_analyzer.py").to_string_lossy().into(),
                    ],
                    &dir,
                )
                .await?;
            }
            state["rust_analyzer"] = json!("2026-09-28");
        }
        if has("kotlin") {
            invoke(
                &py,
                &[
                    "-I".into(),
                    dir.join("setup_mobile.py").to_string_lossy().into(),
                    c.runtime(&c.java_path),
                ],
                &dir,
            )
            .await?;
            state["kotlin"] = json!("2.3.10");
        }
        if has("swift") {
            invoke(&c.runtime(&c.swiftc_path), &args(&["--version"]), &dir).await?;
            state["swift"] = json!("native Swift 6.2+");
        }
        if dev {
            invoke(
                &py,
                &args(&[
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--only-binary=:all:",
                    "ruff==0.16.9",
                    "mypy==2.3.1",
                ]),
                &dir,
            )
            .await?;
            state["dev_tools"] = json!(true);
        }
        fs::write(state_path, serde_json::to_vec(&state)?)?;
    }
    Ok(())
}
