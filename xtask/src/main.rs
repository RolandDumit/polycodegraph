use anyhow::{Result, bail};
use std::{path::PathBuf, process::Command};
fn run(args: &[&str]) -> Result<()> {
    let status = Command::new("cargo").args(args).status()?;
    if !status.success() {
        bail!("cargo {args:?} failed")
    }
    Ok(())
}
fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("check") => {
            run(&["fmt", "--all", "--", "--check"])?;
            run(&[
                "clippy",
                "--workspace",
                "--all-targets",
                "--",
                "-D",
                "warnings",
            ])?;
            run(&["test", "--workspace"])?;
        }
        Some("bench") => {
            run(&[
                "build",
                "--release",
                "-p",
                "polycodegraph-core",
                "--example",
                "benchmark",
            ])?;
            let root = std::env::args().nth(2).ok_or_else(|| {
                anyhow::anyhow!("cargo xtask bench <corpus-directory-with-bench.dart>")
            })?;
            let binary = if cfg!(windows) {
                "target/release/examples/benchmark.exe"
            } else {
                "target/release/examples/benchmark"
            };
            let status = Command::new(binary).arg(root).status()?;
            if !status.success() {
                bail!("benchmark failed")
            }
        }
        Some("package") => {
            run(&["build", "--release", "-p", "polycodegraph"])?;
            let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
            let output = root.join("dist/polycodegraph");
            std::fs::create_dir_all(&output)?;
            let binary = if cfg!(windows) {
                "polycodegraph.exe"
            } else {
                "polycodegraph"
            };
            let target = std::env::var_os("CARGO_TARGET_DIR")
                .map(PathBuf::from)
                .unwrap_or_else(|| root.join("target"));
            let assets = match args.as_slice() {
                [_] => root.join("providers"),
                [_, flag, directory] if flag == "--providers" => PathBuf::from(directory),
                _ => bail!("Use cargo xtask package [--providers <prepared-assets-directory>]"),
            };
            std::fs::copy(target.join("release").join(binary), output.join(binary))?;
            copy_assets(&assets, &output.join("providers"))?;
            copy_assets(&root.join("docs"), &output.join("docs"))?;
            let clients = output.join("clients");
            std::fs::create_dir_all(&clients)?;
            for name in [
                "efficiency_client.py",
                "efficiency_collection.py",
                "efficiency_ledger.py",
                "efficiency_workflow.py",
                "efficiency_binding.py",
                "efficiency_transport.py",
                "efficiency_mcp.py",
            ] {
                std::fs::copy(root.join("tool").join(name), clients.join(name))?;
            }
            for name in ["README.md", "LICENSE"] {
                std::fs::copy(root.join(name), output.join(name))?;
            }
            std::fs::write(
                output.join("manifest.json"),
                serde_json::to_vec_pretty(
                    &serde_json::json!({"version":env!("CARGO_PKG_VERSION"),"os":std::env::consts::OS,"arch":std::env::consts::ARCH,"rust_toolchain":"1.99.0","dart_sdk_build":"3.13.2","dart_analyzer":"13.3.0","typescript":"6.0.2","go_build":"1.27.1","go_tools":"0.43.0","jedi":"0.20.0","parso":"0.8.7","java_source":"17","swift":"6.2+","rust_analyzer":"2026-09-28","kotlin":"2.3.10","libclang":"18.1.1","requires":"See README for selected provider runtimes; virtual environments must be prepared on destination"}),
                )?,
            )?;
        }
        _ => bail!("Use cargo xtask check|package|bench <corpus>"),
    };
    Ok(())
}
fn copy_assets(from: &std::path::Path, to: &std::path::Path) -> Result<()> {
    std::fs::create_dir_all(to)?;
    for item in std::fs::read_dir(from)? {
        let item = item?;
        let name = item.file_name();
        if [
            ".venv",
            ".tools",
            ".dart_tool",
            "node_modules",
            ".installed.json",
            "__pycache__",
            ".ruff_cache",
            ".mypy_cache",
        ]
        .iter()
        .any(|n| name == *n)
        {
            continue;
        }
        let ty = item.file_type()?;
        if ty.is_symlink() {
            continue;
        }
        if ty.is_dir() {
            copy_assets(&item.path(), &to.join(name))?;
        } else {
            std::fs::copy(item.path(), to.join(name))?;
        }
    }
    Ok(())
}
