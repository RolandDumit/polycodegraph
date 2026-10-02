use polycodegraph_core::{
    config::Config,
    index::Indexer,
    mcp,
    model::{Edge, FileRecord, Node, Snapshot, hash},
    providers,
    query::Graph,
    store::Store,
};
use serde_json::json;
use std::{collections::BTreeMap, fs};
fn config(dir: &tempfile::TempDir) -> Config {
    let mut c = Config::load(dir.path(), None).unwrap();
    c.providers_path = Some(dir.path().join("assets").to_string_lossy().into());
    fs::create_dir_all(c.assets()).unwrap();
    c
}
fn node(file: &str, name: &str, kind: &str) -> Node {
    Node {
        id: format!("{file}::{name}#{kind}"),
        name: name.into(),
        qualified: name.into(),
        kind: kind.into(),
        file: file.into(),
        line: 1,
        end: 1,
        offset: 0,
        length: 1,
        parent: None,
        tags: vec![],
        synthetic: false,
    }
}
fn graph() -> Graph {
    let file = "a.dart";
    let mut nodes = vec![
        node(file, "Repository", "class"),
        node(file, "Repository.fetch", "method"),
        node(file, "Memory.fetch", "method"),
        node(file, "use", "function"),
    ];
    nodes[1].parent = Some(nodes[0].id.clone());
    let edge = |s: usize, t: usize, kind: &str| Edge {
        source: nodes[s].id.clone(),
        target: nodes[t].id.clone(),
        kind: kind.into(),
        file: file.into(),
        line: 1,
        offset: s,
        confidence: "resolved".into(),
    };
    let edges = vec![
        edge(0, 1, "contains"),
        edge(2, 1, "overrides"),
        edge(3, 1, "calls"),
    ];
    Graph::new(Snapshot {
        generation: "generation".into(),
        files: BTreeMap::from([(
            file.into(),
            FileRecord {
                file: file.into(),
                hash: hash("abc\n"),
                nodes,
                edges,
                dependencies: vec![],
                diagnostics: vec![],
                unresolved_calls: 0,
                intent: Default::default(),
            },
        )]),
        ..Default::default()
    })
}
#[test]
fn search_pagination_and_ambiguity() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let g = graph();
    let r = g.search(&c, &json!({"query":"fetch","limit":1}));
    assert_eq!(r["total"], 2);
    assert_eq!(r["next_offset"], 1);
    assert_eq!(
        g.resolve("Repository.fetch").unwrap(),
        g.ids["a.dart::Repository.fetch#method"]
    );
    assert!(g.resolve("missing").is_err());
}
#[test]
fn impact_follows_dispatch_contract() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let g = graph();
    let r = g
        .affected(&c, &json!({"target":"Memory.fetch","depth":6}))
        .unwrap();
    assert!(r["rows"].as_array().unwrap().iter().any(|r| r[2] == "use"));
    assert_eq!(r["conservative"], true);
    let bounded = g
        .affected(&c, &json!({"target":"Memory.fetch","depth":1}))
        .unwrap();
    assert_eq!(bounded["depth_limited"], true);
}
#[test]
fn inspection_same_generation_and_omissions() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let r = graph()
        .inspect(&c, &json!({"target":"Repository.fetch","limit":1}))
        .unwrap();
    for k in ["callers", "implementations", "impact"] {
        assert_eq!(r[k]["generation"], r["generation"]);
        assert!(r[k].get("omitted").is_some());
    }
    assert!(r.get("snippet").is_none());
}
#[test]
fn configuration_rejects_unknown_and_traversal() {
    let d = tempfile::tempdir().unwrap();
    fs::write(d.path().join("polycodegraph.yaml"), "unknown: true").unwrap();
    assert!(Config::load(d.path(), None).is_err());
    fs::write(d.path().join("polycodegraph.yaml"), "cache: ../outside").unwrap();
    assert!(Config::load(d.path(), None).is_err());
    fs::write(
        d.path().join("polycodegraph.yaml"),
        "watch: false\nmax_results: 0",
    )
    .unwrap();
    assert!(Config::load(d.path(), None).is_err());
}
#[test]
fn schema_validation() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let t = mcp::tools(&c);
    assert_eq!(t.len(), 16);
    let s = t.iter().find(|t| t["name"] == "search_symbol").unwrap();
    assert!(mcp::validate(s, &json!({"query":"x","limit":-1})).is_err());
    assert!(mcp::validate(s, &json!({"query":"x","unknown":0})).is_err());
    assert!(mcp::validate(s, &json!({"query":"x","language":"kotlin"})).is_ok());
}
#[test]
fn storage_roundtrip_and_deleted_records() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let s = Store::new(&c).unwrap();
    let mut snap = (*graph().snapshot).clone();
    s.write(&snap).unwrap();
    assert_eq!(s.read().unwrap().unwrap().files.len(), 1);
    snap.files.clear();
    s.write(&snap).unwrap();
    assert_eq!(s.read().unwrap().unwrap().files.len(), 0);
    let db = rusqlite::Connection::open(&s.path).unwrap();
    assert_eq!(
        db.query_row("select count(*) from symbols", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        0
    );
}
#[test]
fn transaction_failure_preserves_generation() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let s = Store::new(&c).unwrap();
    let snap = graph().snapshot;
    s.write(&snap).unwrap();
    let db = rusqlite::Connection::open(&s.path).unwrap();
    db.execute_batch("CREATE TRIGGER reject_update BEFORE INSERT ON metadata BEGIN SELECT RAISE(ABORT,'injected'); END;").unwrap();
    let mut next = (*snap).clone();
    next.generation = "next".into();
    next.files.clear();
    assert!(s.write(&next).is_err());
    assert_eq!(s.read().unwrap().unwrap().generation, "generation");
    assert_eq!(s.read().unwrap().unwrap().files.len(), 1);
}
#[test]
fn corrupt_cache_rebuild() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let s = Store::new(&c).unwrap();
    fs::write(&s.path, b"broken database").unwrap();
    let i = Indexer::new(c).unwrap();
    assert!(i.graph.is_none());
    assert!(
        fs::read_dir(d.path().join(".polycodegraph"))
            .unwrap()
            .any(|p| p.unwrap().file_name().to_string_lossy().contains("corrupt"))
    );
}
#[test]
fn unicode_crlf_snippet_checks_source_hash() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let mut g = graph();
    let text = "α😀\r\nsecond\r\n";
    fs::write(d.path().join("a.dart"), text).unwrap();
    std::sync::Arc::make_mut(&mut g.snapshot)
        .files
        .get_mut("a.dart")
        .unwrap()
        .hash = hash(text);
    let r = g
        .snippet(
            &c,
            &json!({"file":"a.dart","start_line":1,"end_line":2,"context":0}),
        )
        .unwrap();
    assert_eq!(r["text"], "α😀\r\nsecond\r");
    fs::write(d.path().join("a.dart"), "modified").unwrap();
    assert!(g.snippet(&c, &json!({"file":"a.dart"})).is_err());
}
#[cfg(unix)]
#[test]
fn symlinks_rejected() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    std::os::unix::fs::symlink("/tmp", d.path().join("linked")).unwrap();
    assert!(c.safe("linked/secret").is_err());
    assert!(c.safe("../secret").is_err());
}
#[tokio::test]
async fn warm_queries_reuse_graph_without_scan() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let mut i = Indexer::new(c).unwrap();
    i.call("get_architecture", &json!({})).await.unwrap();
    let before = (
        i.metrics.scans,
        i.metrics.extractions,
        i.metrics.graph_builds,
    );
    for _ in 0..10 {
        i.call("search_symbol", &json!({"query":""})).await.unwrap();
    }
    assert_eq!(
        (
            i.metrics.scans,
            i.metrics.extractions,
            i.metrics.graph_builds
        ),
        before
    );
}
#[test]
fn change_detection_before_first_index_reports_environment_change() {
    let d = tempfile::tempdir().unwrap();
    let mut i = Indexer::new(config(&d)).unwrap();
    let detected = i.detect_changes().unwrap();
    assert_eq!(detected["indexed"], false);
    assert_eq!(detected["environment_changed"], true);
    assert!(i.graph.is_none(), "detection must not publish an index");
}
#[tokio::test]
async fn disabled_watcher_scans_every_query() {
    let d = tempfile::tempdir().unwrap();
    let mut c = config(&d);
    c.watch = false;
    let mut i = Indexer::new(c).unwrap();
    i.call("get_architecture", &json!({})).await.unwrap();
    let n = i.metrics.scans;
    i.call("get_architecture", &json!({})).await.unwrap();
    assert!(i.metrics.scans > n);
}
#[tokio::test]
async fn subprocess_timeout_and_overflow() {
    let d = tempfile::tempdir().unwrap();
    let mut c = config(&d);
    c.provider_timeout_seconds = 1;
    let cmd = if cfg!(windows) { "python" } else { "python3" };
    assert!(
        providers::run(
            &c,
            &[
                cmd.into(),
                "-c".into(),
                "import time; time.sleep(10)".into()
            ],
            ""
        )
        .await
        .is_err()
    );
    assert!(
        providers::run(
            &c,
            &[
                cmd.into(),
                "-c".into(),
                "import sys; sys.stdout.buffer.write(b'x' * (65*1024*1024))".into()
            ],
            ""
        )
        .await
        .is_err()
    );
}
#[tokio::test]
async fn subprocess_receives_eof() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let cmd = if cfg!(windows) { "python" } else { "python3" };
    let out = providers::run(
        &c,
        &[
            cmd.into(),
            "-c".into(),
            "import sys; print(sys.stdin.read())".into(),
        ],
        "hello",
    )
    .await
    .unwrap();
    assert_eq!(out.trim_end(), "hello");
}
#[tokio::test]
async fn real_framing_lifecycle_and_eof() {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let i = Indexer::new(c).unwrap();
    let (mut client, input) = tokio::io::duplex(2 * 1048576);
    let (output, mut responses) = tokio::io::duplex(2 * 1048576);
    let server = tokio::spawn(mcp::serve(input, output, i));
    client.write_all(b"invalid\n").await.unwrap();
    let requests = [
        json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"future","capabilities":{},"clientInfo":{}}}),
        json!({"jsonrpc":"2.0","method":"notifications/initialized"}),
        json!({"jsonrpc":"2.0","id":2,"method":"tools/list"}),
    ];
    for r in requests {
        client.write_all(format!("{r}\n").as_bytes()).await.unwrap();
    }
    client.write_all(&vec![b'x'; 1048577]).await.unwrap();
    client
        .write_all(b"\n{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"ping\"}\nunterminated")
        .await
        .unwrap();
    drop(client);
    let mut out = String::new();
    responses.read_to_string(&mut out).await.unwrap();
    server.await.unwrap().unwrap();
    let values: Vec<serde_json::Value> = out
        .lines()
        .map(|l| serde_json::from_str(l).unwrap())
        .collect();
    assert_eq!(
        values
            .iter()
            .filter(|v| v["error"]["code"] == -32700)
            .count(),
        3
    );
    assert_eq!(
        values.iter().find(|v| v["id"] == 1).unwrap()["result"]["protocolVersion"],
        "2025-11-25"
    );
    assert_eq!(
        values.iter().find(|v| v["id"] == 2).unwrap()["result"]["tools"]
            .as_array()
            .unwrap()
            .len(),
        16
    );
    assert_eq!(
        values.iter().find(|v| v["id"] == 3).unwrap()["result"],
        json!({})
    );
}

#[tokio::test]
async fn provider_timeout_terminates_descendants() {
    let d = tempfile::tempdir().unwrap();
    let mut c = config(&d);
    c.provider_timeout_seconds = 1;
    let marker = d.path().join("orphan-marker");
    let quoted = serde_json::to_string(&marker.to_string_lossy()).unwrap();
    let descendant =
        format!("import time,pathlib;time.sleep(2);pathlib.Path({quoted}).write_text('orphan')");
    let source = format!(
        "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{}]);time.sleep(30)",
        serde_json::to_string(&descendant).unwrap()
    );
    let cmd = if cfg!(windows) { "python" } else { "python3" };
    assert!(
        providers::run(&c, &[cmd.into(), "-c".into(), source], "")
            .await
            .is_err()
    );
    tokio::time::sleep(std::time::Duration::from_millis(1300)).await;
    assert!(!marker.exists(), "timed-out provider descendant survived");
}

#[test]
fn unicode_pagination_uses_legacy_utf16_order() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let files = ["😀.dart", "Ｚ.dart"]
        .iter()
        .map(|file| {
            (
                file.to_string(),
                FileRecord {
                    file: file.to_string(),
                    hash: hash("abc"),
                    nodes: vec![node(file, "example", "function")],
                    edges: vec![],
                    dependencies: vec![],
                    diagnostics: vec![],
                    unresolved_calls: 0,
                    intent: Default::default(),
                },
            )
        })
        .collect();
    let g = Graph::new(Snapshot {
        files,
        ..Default::default()
    });
    assert_eq!(
        g.search(&c, &json!({"query":"","limit":1}))["rows"][0][3],
        "😀.dart"
    );
}
