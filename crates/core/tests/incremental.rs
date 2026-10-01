use polycodegraph_core::{config::Config, index::Indexer, model::hash, store::Store};
use serde_json::json;
use std::{fs, time::Duration};
// Deliberately tiny provider: tests the orchestrator contract, not language semantics.
// Full semantic coverage is checked against v0.4.0 by tool/smoke.py.
fn fixture() -> (tempfile::TempDir, tempfile::TempDir, Config) {
    let root = tempfile::tempdir().unwrap();
    let assets = tempfile::tempdir().unwrap();
    fs::create_dir_all(assets.path().join("typescript")).unwrap();
    fs::write(assets.path().join("typescript/index.cjs"), r#"
import json,sys,pathlib,time
r=json.load(sys.stdin);root=pathlib.Path(r['root']);out=[]
marker=root/'race.once'
if marker.exists():
    marker.unlink(); f=root/'a/first.ts';f.write_text(f.read_text()+'\n// concurrent edit')
if (root/'slow.once').exists():
    (root/'slow.once').unlink();time.sleep(.3)
if (root/'fail.once').exists(): sys.exit(2)
for f in r['files']:
    if f['file'] not in r['options']['emit_files']:continue
    name=f['file'];n={'id':name+'::run#function','name':'run','q':'run','kind':'function','file':name,'line':1,'end':1,'offset':0,'length':1}
    deps=['a/first.ts'] if name=='c/dependent.ts' else []
    out.append({'file':name,'hash':f['hash'],'nodes':[n],'edges':[], 'dependencies':deps,'diagnostics':[],'unresolved_calls':0})
json.dump(out,sys.stdout)
"#).unwrap();
    for (dir, file) in [("a", "first"), ("b", "independent"), ("c", "dependent")] {
        fs::create_dir_all(root.path().join(dir)).unwrap();
        fs::write(root.path().join(dir).join("tsconfig.json"), "{}").unwrap();
        fs::write(
            root.path().join(dir).join(format!("{file}.ts")),
            "function run() {}\n",
        )
        .unwrap();
    }
    let mut c = Config::load(root.path(), None).unwrap();
    c.providers_path = Some(assets.path().to_string_lossy().into());
    c.node_path = if cfg!(windows) { "python" } else { "python3" }.into();
    c.watch_debounce_ms = 10;
    (root, assets, c)
}
async fn delivered(i: &Indexer) {
    for _ in 0..100 {
        if i.freshness()["pending_updates"].as_u64().unwrap() > 0 {
            return;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    panic!("watcher did not deliver an event")
}
#[tokio::test]
async fn independent_scopes_and_old_dependency_invalidation() {
    let (root, _assets, c) = fixture();
    let mut i = Indexer::new(c).unwrap();
    i.refresh(true, false).await.unwrap();
    let scans = i.metrics.scans;
    let p = root.path().join("a/first.ts");
    fs::write(&p, "function run() { return 1; }\n").unwrap();
    fs::write(&p, "function run() { return 2; }\n").unwrap();
    delivered(&i).await;
    let r = i.refresh(false, false).await.unwrap();
    assert_eq!(r["reindexed"], json!(["a/first.ts", "c/dependent.ts"]));
    assert_eq!(
        i.metrics.scans, scans,
        "no full scan between reconciliations"
    );
    let metrics = (
        i.metrics.scans,
        i.metrics.extractions,
        i.metrics.graph_builds,
    );
    i.refresh(false, false).await.unwrap();
    assert_eq!(
        (
            i.metrics.scans,
            i.metrics.extractions,
            i.metrics.graph_builds
        ),
        metrics
    );
}
#[tokio::test]
async fn atomic_replace_rename_delete_and_detect_without_publish() {
    let (root, _assets, c) = fixture();
    let mut i = Indexer::new(c).unwrap();
    i.refresh(true, false).await.unwrap();
    let generation = i.graph.as_ref().unwrap().snapshot.generation.clone();
    let temp = root.path().join("a/saved.tmp");
    fs::write(&temp, "function renamed() {}\n").unwrap();
    // Windows replacement APIs differ; remove destination before rename there.
    if cfg!(windows) {
        fs::remove_file(root.path().join("a/first.ts")).unwrap();
    }
    fs::rename(temp, root.path().join("a/first.ts")).unwrap();
    let detected = i.detect_changes().unwrap();
    assert_eq!(detected["changed"], json!(["a/first.ts"]));
    assert_eq!(i.graph.as_ref().unwrap().snapshot.generation, generation);
    delivered(&i).await;
    i.refresh(false, false).await.unwrap();
    fs::rename(
        root.path().join("a/first.ts"),
        root.path().join("a/renamed.ts"),
    )
    .unwrap();
    delivered(&i).await;
    let r = i.refresh(false, false).await.unwrap();
    assert_eq!(r["deleted"], json!(["a/first.ts"]));
    assert!(
        i.graph
            .as_ref()
            .unwrap()
            .snapshot
            .files
            .contains_key("a/renamed.ts")
    );
    fs::remove_file(root.path().join("a/renamed.ts")).unwrap();
    delivered(&i).await;
    i.refresh(false, false).await.unwrap();
    assert!(
        !i.graph
            .as_ref()
            .unwrap()
            .snapshot
            .files
            .contains_key("a/renamed.ts")
    );
}
#[tokio::test]
async fn concurrent_source_edit_retries_and_provider_failure_retains_generation() {
    let (root, _assets, c) = fixture();
    let mut i = Indexer::new(c).unwrap();
    i.refresh(true, false).await.unwrap();
    fs::write(root.path().join("race.once"), "").unwrap();
    let r = i.refresh(true, true).await.unwrap();
    assert!(r["full"].as_bool().unwrap());
    let snap = &i.graph.as_ref().unwrap().snapshot;
    assert_eq!(
        snap.files["a/first.ts"].hash,
        hash(fs::read(root.path().join("a/first.ts")).unwrap())
    );
    let generation = snap.generation.clone();
    fs::write(root.path().join("fail.once"), "").unwrap();
    assert!(i.refresh(true, true).await.is_err());
    assert_eq!(i.graph.as_ref().unwrap().snapshot.generation, generation);
    assert_eq!(i.store.read().unwrap().unwrap().generation, generation);
}
#[tokio::test]
async fn concurrent_writers_reload_a_committed_generation() {
    let (root, _assets, c) = fixture();
    let mut first = Indexer::new(c.clone()).unwrap();
    let mut second = Indexer::new(c).unwrap();
    first.refresh(true, false).await.unwrap();
    fs::write(
        root.path().join("a/first.ts"),
        "function run() { return 9; }\n",
    )
    .unwrap();
    let (a, b) = tokio::join!(first.refresh(true, false), second.refresh(true, false));
    a.unwrap();
    b.unwrap();
    assert_eq!(
        first.graph.as_ref().unwrap().snapshot.generation,
        second.graph.as_ref().unwrap().snapshot.generation
    );
    let saved = Store::new(&first.config).unwrap().read().unwrap().unwrap();
    assert_eq!(
        saved.generation,
        first.graph.as_ref().unwrap().snapshot.generation
    );
}
#[tokio::test]
async fn configuration_change_rebuilds_even_without_source_edits() {
    let (root, _assets, c) = fixture();
    let mut i = Indexer::new(c.clone()).unwrap();
    i.refresh(true, false).await.unwrap();
    let previous = i.graph.as_ref().unwrap().snapshot.generation.clone();
    let mut changed = c.clone();
    changed.include = vec!["a/*.ts".into()];
    fs::write(
        root.path().join("polycodegraph.json"),
        serde_json::to_vec(&changed).unwrap(),
    )
    .unwrap();
    delivered(&i).await;
    i.refresh(false, false).await.unwrap();
    assert_ne!(i.graph.as_ref().unwrap().snapshot.generation, previous);
    assert_eq!(i.graph.as_ref().unwrap().snapshot.files.len(), 1);
}
#[cfg(unix)]
#[test]
fn sqlite_sidecar_symlink_is_rejected() {
    let (root, _assets, c) = fixture();
    let store = Store::new(&c).unwrap();
    let outside = root.path().join("outside");
    fs::write(&outside, "untouched").unwrap();
    std::os::unix::fs::symlink(
        &outside,
        root.path().join(".polycodegraph/index.sqlite-wal"),
    )
    .unwrap();
    assert!(store.write(&Default::default()).is_err());
    assert_eq!(fs::read_to_string(outside).unwrap(), "untouched");
}

#[tokio::test]
async fn mcp_cancellation_duplicates_and_queue_bound() {
    use polycodegraph_core::mcp;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    let (root, _assets, c) = fixture();
    let mut i = Indexer::new(c).unwrap();
    i.refresh(true, false).await.unwrap();
    fs::write(root.path().join("slow.once"), "").unwrap();
    let (mut client, input) = tokio::io::duplex(1048576);
    let (output, mut responses) = tokio::io::duplex(1048576);
    let server = tokio::spawn(mcp::serve(input, output, i));
    let init = json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{}}});
    let ready = json!({"jsonrpc":"2.0","method":"notifications/initialized"});
    let index = |id| json!({"jsonrpc":"2.0","id":id,"method":"tools/call","params":{"name":"index_repository","arguments":{"force":true}}});
    for r in [init, ready, index(2)] {
        client.write_all(format!("{r}\n").as_bytes()).await.unwrap();
    }
    tokio::time::sleep(Duration::from_millis(150)).await;
    let commands = [
        index(3),
        json!({"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":3}}),
        json!({"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":2}}),
        index(2),
    ];
    for r in commands {
        client.write_all(format!("{r}\n").as_bytes()).await.unwrap();
    }
    for id in 10..90 {
        let r = json!({"jsonrpc":"2.0","id":id,"method":"ping"});
        client.write_all(format!("{r}\n").as_bytes()).await.unwrap();
    }
    drop(client);
    let mut result = String::new();
    responses.read_to_string(&mut result).await.unwrap();
    server.await.unwrap().unwrap();
    let responses: Vec<serde_json::Value> = result
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    assert!(
        responses
            .iter()
            .any(|r| r["id"] == 2 && r["error"]["code"] == -32600)
    );
    assert!(
        !responses
            .iter()
            .any(|r| (r["id"] == 2 || r["id"] == 3) && r.get("result").is_some())
    );
    assert!(
        responses
            .iter()
            .any(|r| r["error"]["message"] == "Server queue full")
    );
    assert!(
        responses.iter().any(|r| r["result"] == json!({})),
        "serialized work continues after cancellation"
    );
}

#[tokio::test]
async fn prepared_external_context_changes_invalidate_without_source_edits() {
    let (root, assets, c) = fixture();
    fs::create_dir_all(root.path().join("a/node_modules/library")).unwrap();
    let external = root.path().join("a/node_modules/library/types.d.ts");
    fs::write(&external, "export const value: string;\n").unwrap();
    let mut i = Indexer::new(c).unwrap();
    i.refresh(true, false).await.unwrap();
    let previous = i.graph.as_ref().unwrap().snapshot.generation.clone();
    fs::write(external, "export const value: number;\n").unwrap();
    let detected = i.detect_changes().unwrap();
    assert_eq!(detected["changed"], json!([]));
    assert_eq!(detected["environment_changed"], true);
    i.refresh(true, false).await.unwrap();
    assert_ne!(i.graph.as_ref().unwrap().snapshot.generation, previous);
    assert!(
        i.graph
            .as_ref()
            .unwrap()
            .snapshot
            .environment_inputs
            .keys()
            .any(|k| k.starts_with("external-node:"))
    );
    assert!(assets.path().exists());
}
#[tokio::test]
async fn corrupted_database_while_running_recovers_with_coherent_generation() {
    let (_root, _assets, c) = fixture();
    let mut i = Indexer::new(c).unwrap();
    i.refresh(true, false).await.unwrap();
    let previous = i.graph.as_ref().unwrap().snapshot.generation.clone();
    fs::write(&i.store.path, "corrupt").unwrap();
    let result = i.refresh(true, false).await.unwrap();
    assert_eq!(result["full"], true);
    assert_eq!(i.store.read().unwrap().unwrap().generation, previous);
}
