use clap::Parser;
use polycodegraph_core::{
    config::{Config, ResponseProfile},
    index::Indexer,
    mcp, providers, setup,
};
use serde_json::json;
use std::path::PathBuf;
#[derive(Parser)]
#[command(
    name = "polycodegraph",
    version,
    about = "Local semantic code graph and MCP server"
)]
struct Args {
    #[arg(default_value = "help")]
    command: String,
    #[arg(long, default_value = ".")]
    root: PathBuf,
    #[arg(long)]
    config: Option<PathBuf>,
    #[arg(long)]
    force: bool,
    #[arg(long)]
    languages: Option<String>,
    #[arg(long)]
    dev: bool,
    #[arg(long, value_parser=["legacy","compact"])]
    response_profile: Option<String>,
    #[arg(long)]
    tool_profile: Option<String>,
}
#[tokio::main]
async fn main() {
    let args = match Args::try_parse() {
        Ok(a) => a,
        Err(e) => {
            let rc = if matches!(
                e.kind(),
                clap::error::ErrorKind::DisplayHelp | clap::error::ErrorKind::DisplayVersion
            ) {
                0
            } else {
                64
            };
            let _ = e.print();
            std::process::exit(rc)
        }
    };
    if args.command == "help" {
        println!(
            "polycodegraph <init|index|serve|status|doctor|setup> [--root PATH] [--config PATH] [--force]\nsetup: [--languages dart,typescript,...] [--dev]"
        );
        return;
    }
    if !["init", "index", "serve", "status", "doctor", "setup"].contains(&args.command.as_str()) {
        eprintln!("polycodegraph: unknown command");
        std::process::exit(64)
    }
    let mut c = match Config::load(&args.root, args.config.as_deref()) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("polycodegraph: {e:#}");
            std::process::exit(if e.downcast_ref::<std::io::Error>().is_some() {
                74
            } else {
                64
            })
        }
    };
    if let Some(profile) = args.response_profile.as_deref() {
        let profile = if profile == "compact" {
            ResponseProfile::Compact
        } else {
            ResponseProfile::Legacy
        };
        c.response_profile = profile;
        c.response_profile_override = Some(profile);
    }
    let result: anyhow::Result<()> = async {
        if let Some(profile)=args.tool_profile.as_deref() {
        let profile=match profile {"full"=>polycodegraph_core::config::ToolProfile::Full,"agent"=>polycodegraph_core::config::ToolProfile::Agent,_=>anyhow::bail!("tool-profile must be full or agent")};
        c.tool_profile=profile;c.tool_profile_override=Some(profile);
    }
    match args.command.as_str() {
            "doctor" => println!("{}", providers::doctor(&c)),
            "init" => {
                for name in ["polycodegraph.yaml", "polycodegraph.yml", "polycodegraph.json"] {
                    if c.root.join(name).exists() { anyhow::bail!("Configuration already exists") }
                }
                let text = serde_json::to_string_pretty(&Config::default())?;
                std::fs::write(c.safe("polycodegraph.yaml")?, format!("# JSON is valid YAML; paths are repository-relative.\n{text}\n"))?;
                println!("{}", json!({"created":"polycodegraph.yaml"}));
            }
            "setup" => setup::setup(&c, args.languages.as_deref(), args.dev).await?,
            "serve" => mcp::serve(tokio::io::stdin(), tokio::io::stdout(), Indexer::new(c)?).await?,
            "index" => {
                let mut index = Indexer::new(c)?;
                let report = if index.config.response_profile == ResponseProfile::Compact {
                    index.call("index_repository", &json!({"force":args.force})).await?
                } else { index.refresh(true,args.force).await? };
                println!("{report}");
            }
            "status" => {
                let mut index = Indexer::new(c)?;
                let changes = index.detect_changes()?;
                if index.config.response_profile == ResponseProfile::Compact {
                    println!("{}", index.cached_status(&changes)?);
                    return Ok(());
                }
                let mut v = json!({"indexed":index.graph.is_some(),"changes":changes,"freshness":index.freshness()});
                if let Some(g) = &index.graph {
                    let arch = g.architecture(&index.config, 5);
                    for (k, x) in arch.as_object().into_iter().flatten() { v[k] = x.clone(); }
                }
                println!("{v}");
            }
            _ => unreachable!("validated command"),
        }
        Ok(())
    }.await;
    if let Err(e) = result {
        eprintln!("polycodegraph: {e:#}");
        std::process::exit(if e.downcast_ref::<std::io::Error>().is_some() {
            74
        } else if e.to_string().contains("Configuration already exists") {
            64
        } else {
            1
        })
    }
}
