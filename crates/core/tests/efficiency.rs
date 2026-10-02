use polycodegraph_core::{
    config::{Config, ResponseProfile},
    index::Indexer,
    mcp,
    model::{Edge, FileRecord, Node, Snapshot, hash},
    query::Graph,
    store::Store,
};
use serde_json::{Value, json};
use std::fs;

fn config(d: &tempfile::TempDir) -> Config {
    let mut c = Config::load(d.path(), None).unwrap();
    c.providers_path = Some(d.path().join("assets").to_string_lossy().into());
    fs::create_dir_all(c.assets()).unwrap();
    c
}
fn graph(files: &[&str]) -> Graph {
    let files = files
        .iter()
        .map(|f| {
            let mut nodes: Vec<_> = (0..60)
                .map(|i| Node {
                    id: format!("{f}::n{i}#function"),
                    name: format!("n{i}"),
                    qualified: format!("n{i}"),
                    file: (*f).into(),
                    kind: "function".into(),
                    line: 1,
                    end: 100,
                    offset: i,
                    length: 1,
                    parent: None,
                    tags: vec![],
                    synthetic: false,
                })
                .collect();
            nodes[0].kind = "class".into();
            let edges = (1..60)
                .map(|i| Edge {
                    source: nodes[i].id.clone(),
                    target: nodes[0].id.clone(),
                    kind: "calls".into(),
                    file: (*f).into(),
                    line: 1,
                    offset: i,
                    confidence: "resolved".into(),
                })
                .collect();
            (
                (*f).into(),
                FileRecord {
                    file: (*f).into(),
                    hash: hash("x\n".repeat(100)),
                    nodes,
                    edges,
                    dependencies: vec![],
                    diagnostics: vec![],
                    unresolved_calls: 0,
                    intent: Default::default(),
                },
            )
        })
        .collect();
    Graph::new(Snapshot {
        files,
        generation: "same".into(),
        ..Default::default()
    })
}
#[test]
fn profile_changes_do_not_invalidate_index_and_reject_unknown_profiles() {
    let d = tempfile::tempdir().unwrap();
    let mut c = config(&d);
    let before = c.fingerprint().unwrap();
    let legacy = serde_json::to_string(&c).unwrap();
    assert_eq!(before, hash(&legacy));
    c.response_profile = ResponseProfile::Compact;
    assert_eq!(before, c.fingerprint().unwrap());
    fs::write(
        d.path().join("polycodegraph.yaml"),
        "response_profile: mystery",
    )
    .unwrap();
    assert!(Config::load(d.path(), None).is_err());
}
#[test]
fn compact_defaults_full_override_and_pagination_preserve_sites() {
    let d = tempfile::tempdir().unwrap();
    let mut c = config(&d);
    c.response_profile = ResponseProfile::Compact;
    let g = graph(&["lib/a.dart"]);
    let page = g.call(&c, "search_symbol", &json!({"query":"n"})).unwrap();
    assert_eq!(page["rows"].as_array().unwrap().len(), 10);
    assert_eq!(page["next_offset"], 10);
    assert_eq!(page["omitted"], 50);
    let full = g
        .call(&c, "search_symbol", &json!({"query":"n","detail":"full"}))
        .unwrap();
    assert_eq!(full["rows"].as_array().unwrap().len(), 50);
    assert!(full.get("omitted").is_none());
    let explicit = json!({"target":"lib/a.dart::n0#function","limit":60});
    let compact = g.call(&c, "callers", &explicit).unwrap();
    let mut full_args = explicit.clone();
    full_args["detail"] = json!("full");
    let full = g.call(&c, "callers", &full_args).unwrap();
    for k in [
        "rows",
        "columns",
        "total",
        "generation",
        "target",
        "next_offset",
    ] {
        assert_eq!(compact[k], full[k]);
    }
    assert_eq!(
        compact["rows"].as_array().unwrap().len(),
        59,
        "distinct call sites must not merge"
    );
    let default = g
        .call(&c, "callers", &json!({"target":"lib/a.dart::n0#function"}))
        .unwrap();
    assert_eq!(default["next_offset"], 20);
    let last = g
        .call(
            &c,
            "callers",
            &json!({"target":"lib/a.dart::n0#function","offset":58}),
        )
        .unwrap();
    assert_eq!(last["next_offset"], Value::Null);
    assert_eq!(last["rows"].as_array().unwrap().len(), 1);
}
#[test]
fn paths_distinguish_valid_empty_wrong_root_and_ambiguous_suggestions() {
    let d = tempfile::tempdir().unwrap();
    let mut c = config(&d);
    c.response_profile = ResponseProfile::Compact;
    let g = graph(&["app/lib/a.dart"]);
    let query = |file: &str| g.call(&c, "search_symbol", &json!({"query":"absent","file":file}));
    let valid = query("app/lib/").unwrap();
    assert_eq!(valid["total"], 0);
    assert_eq!(valid["file_filter"]["valid"], true);
    assert!(valid.get("warning").is_none());
    let invalid = query("lib/").unwrap();
    assert_eq!(invalid["file_filter"]["valid"], false);
    assert_eq!(invalid["file_filter"]["suggested_prefix"], "app/lib/");
    assert_eq!(invalid["total"], 0);
    for unsafe_path in ["/app/lib", "../lib", "C:/lib", "..\\lib"] {
        assert!(query(unsafe_path).is_err());
    }
    let ambiguous = graph(&["app/lib/a.dart", "other/lib/a.dart"])
        .call(&c, "search_symbol", &json!({"query":"n","file":"lib/"}))
        .unwrap();
    assert!(ambiguous["file_filter"].get("suggested_prefix").is_none());
    let missing = query("not-indexed/").unwrap();
    assert!(missing["file_filter"].get("suggested_prefix").is_none());
}
#[test]
fn implicit_snippet_small_explicit_windows_and_full_override() {
    let d = tempfile::tempdir().unwrap();
    let mut c = config(&d);
    c.response_profile = ResponseProfile::Compact;
    fs::create_dir(d.path().join("lib")).unwrap();
    fs::write(d.path().join("lib/a.dart"), "x\n".repeat(100)).unwrap();
    let g = graph(&["lib/a.dart"]);
    let implicit = g
        .call(&c, "snippet", &json!({"target":"lib/a.dart::n0#function"}))
        .unwrap();
    assert_eq!(implicit["end_line"], 30);
    assert_eq!(implicit["truncated"], true);
    let full = g
        .call(
            &c,
            "snippet",
            &json!({"target":"lib/a.dart::n0#function","detail":"full"}),
        )
        .unwrap();
    assert_eq!(full["truncated"], false);
    let explicit = g
        .call(
            &c,
            "snippet",
            &json!({"file":"lib/a.dart","start_line":31,"end_line":70,"context":0}),
        )
        .unwrap();
    assert_eq!(explicit["end_line"], 70);
    assert_eq!(explicit["truncated"], false);
    let inspect = g
        .call(
            &c,
            "inspect_change",
            &json!({"target":"lib/a.dart::n0#function","depth":1,"limit":1,"include_snippet":true}),
        )
        .unwrap();
    assert_eq!(inspect["snippet"]["end_line"], 30);
    assert_eq!(inspect["impact"]["depth"], 1);
}
#[tokio::test]
async fn unchanged_scans_force_health_same_generation_and_recoverable_details() {
    let d = tempfile::tempdir().unwrap();
    let mut c = config(&d);
    c.response_profile = ResponseProfile::Compact;
    let mut i = Indexer::new(c).unwrap();
    let first = i.call("index_repository", &json!({})).await.unwrap();
    let scans = i.metrics.scans;
    let builds = i.metrics.graph_builds;
    let second = i.call("index_repository", &json!({})).await.unwrap();
    assert_eq!(second["outcome"], "unchanged");
    assert!(i.metrics.scans > scans);
    assert_eq!(i.metrics.graph_builds, builds);
    assert_eq!(second["generation"], first["generation"]);
    let forced = i
        .call("index_repository", &json!({"force":true}))
        .await
        .unwrap();
    assert_eq!(forced["update"]["full"], true);
    assert!(i.metrics.graph_builds > builds);
    // Simulate another writer publishing diagnostics without changing source generation.
    let d = tempfile::tempdir().unwrap();
    let mut c = config(&d);
    c.response_profile = ResponseProfile::Compact;
    fs::write(d.path().join("a.dart"), "x").unwrap();
    let mut i = Indexer::new(c).unwrap();
    // Prepare a real failure once; later inject health-only differences into that same cache.
    i.call("index_repository", &json!({})).await.unwrap();
    let mut snap = (*i.graph.as_ref().unwrap().snapshot).clone();
    let generation = snap.generation.clone();
    let diagnostics = vec![
        json!({"severity":"error","code":"changed","file":"original-provider-field","message":"x".repeat(3000),"line":1,"extra":{"provider_field":true}}),
        json!({"severity":"warning","code":"w","message":"warning"}),
    ];
    snap.files.get_mut("a.dart").unwrap().diagnostics = diagnostics.clone();
    Store::new(&i.config).unwrap().write(&snap).unwrap();
    let summary = i.call("index_repository", &json!({})).await.unwrap();
    assert_eq!(summary["generation"], generation);
    assert_eq!(summary["outcome"], "issues");
    assert_eq!(summary["update"]["state"], "unchanged");
    assert_eq!(summary["diagnostics"]["counts"]["error"], 1);
    assert_eq!(summary["diagnostics"]["errors"]["new_or_changed_total"], 1);
    assert_ne!(summary["health_fingerprint"], second["health_fingerprint"]);
    let page = i
        .call("status", &json!({"section":"diagnostics","limit":1}))
        .await
        .unwrap();
    assert_eq!(page["items"][0]["diagnostic"], diagnostics[0]);
    assert_eq!(page["items"][0]["file"], "a.dart");
    assert_eq!(page["total"], 2);
    assert_eq!(page["next_offset"], 1);
    let next = i
        .call(
            "status",
            &json!({"section":"diagnostics","limit":1,"offset":1}),
        )
        .await
        .unwrap();
    assert_eq!(next["items"][0]["diagnostic"]["code"], "w");
    assert_eq!(next["next_offset"], Value::Null);
    let mut changed_health = (*i.graph.as_ref().unwrap().snapshot).clone();
    changed_health.files.get_mut("a.dart").unwrap().diagnostics[1]["message"] =
        json!("changed warning, same counts");
    Store::new(&i.config)
        .unwrap()
        .write(&changed_health)
        .unwrap();
    let changed = i.call("index_repository", &json!({})).await.unwrap();
    assert_eq!(changed["generation"], generation);
    assert_ne!(changed["health_fingerprint"], summary["health_fingerprint"]);
    assert_eq!(
        changed["diagnostics"]["counts"],
        summary["diagnostics"]["counts"]
    );
    assert_eq!(changed["diagnostics"]["errors"]["new_or_changed_total"], 0);
    let legacy = i.call("status", &json!({"detail":"full"})).await.unwrap();
    assert!(legacy.get("hubs").is_some());
    assert!(legacy.get("metrics").is_some());
    assert!(
        i.call("index_repository", &json!({"force":true}))
            .await
            .is_err(),
        "failed provider update must not become compact success"
    );
    assert_eq!(i.graph.as_ref().unwrap().snapshot.generation, generation);
}
#[tokio::test]
async fn every_omitted_update_diagnostic_and_skipped_file_is_pageable() {
    let d = tempfile::tempdir().unwrap();
    let mut c = config(&d);
    c.response_profile = ResponseProfile::Compact;
    c.max_results = 3;
    c.max_file_bytes = 100;
    for n in 0..8 {
        fs::write(d.path().join(format!("a{n}.dart")), "class A {}").unwrap();
    }
    fs::write(d.path().join("oversize.dart"), "x".repeat(101)).unwrap();
    let mut i = Indexer::new(c).unwrap();
    let summary = i.call("index_repository", &json!({})).await.unwrap();
    assert_eq!(summary["update"]["changed"], 8);
    assert_eq!(summary["diagnostics"]["total"], 8);
    assert_eq!(summary["diagnostics"]["errors"]["omitted"], 5);
    assert_eq!(summary["coverage"]["skipped"], 1);
    let skipped = i
        .call("status", &json!({"section":"skipped"}))
        .await
        .unwrap();
    assert_eq!(skipped["total"], 1);
    assert_eq!(skipped["items"][0], "oversize.dart");
    let mut names = vec![];
    let mut offset = 0;
    loop {
        let page = i
            .call(
                "status",
                &json!({"section":"update","limit":3,"offset":offset}),
            )
            .await
            .unwrap();
        assert_eq!(page["changed"]["generation"], summary["generation"]);
        names.extend(page["changed"]["items"].as_array().unwrap().iter().cloned());
        if let Some(next) = page["changed"]["next_offset"].as_u64() {
            offset = next;
        } else {
            break;
        }
    }
    assert_eq!(names.len(), 8);
    assert_eq!(
        names
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect::<std::collections::BTreeSet<_>>()
            .len(),
        8
    );
    let last = i
        .call(
            "status",
            &json!({"section":"diagnostics","offset":6,"limit":3}),
        )
        .await
        .unwrap();
    assert_eq!(last["items"].as_array().unwrap().len(), 2);
    assert_eq!(last["next_offset"], Value::Null);
}
#[tokio::test]
async fn profile_reload_reuses_semantic_records_and_cli_status_does_not_index() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    fs::write(
        d.path().join("polycodegraph.yaml"),
        format!("providers_path: {}", c.providers_path.as_ref().unwrap()),
    )
    .unwrap();
    let mut i = Indexer::new(Config::load(d.path(), None).unwrap()).unwrap();
    let detected = i.detect_changes().unwrap();
    assert_eq!(
        i.cached_status(&detected).unwrap()["outcome"],
        "not_indexed"
    );
    assert!(i.graph.is_none());
    let first = i.call("index_repository", &json!({})).await.unwrap();
    let builds = i.metrics.graph_builds;
    fs::write(
        d.path().join("polycodegraph.yaml"),
        format!(
            "response_profile: compact\nproviders_path: {}",
            i.config.providers_path.as_ref().unwrap()
        ),
    )
    .unwrap();
    let compact = i.call("index_repository", &json!({})).await.unwrap();
    assert_eq!(compact["generation"], first["generation"]);
    assert_eq!(compact["outcome"], "unchanged");
    assert_eq!(i.metrics.graph_builds, builds);
    assert_eq!(i.metrics.extractions, 0);
}
#[test]
fn schemas_allow_modes_and_sections_but_reject_unknown_fields() {
    let d = tempfile::tempdir().unwrap();
    let c = config(&d);
    let tools = mcp::tools(&c);
    let s = tools.iter().find(|t| t["name"] == "status").unwrap();
    assert!(
        mcp::validate(
            s,
            &json!({"section":"diagnostics","limit":1,"detail":"full"})
        )
        .is_ok()
    );
    for args in [
        json!({"detail":"unknown"}),
        json!({"section":"secrets"}),
        json!({"offset":-1}),
        json!({"unknown":true}),
    ] {
        assert!(mcp::validate(s, &args).is_err());
    }
    assert_eq!(tools.len(), 16);
}
