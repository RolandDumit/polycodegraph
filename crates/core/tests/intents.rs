use polycodegraph_core::{
    config::Config,
    intents::State,
    mcp,
    model::{Edge, FileRecord, Node, Snapshot, hash},
    query::Graph,
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs};
fn fixture(ext: &str) -> (tempfile::TempDir, Config, Graph) {
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    let file = format!("api.{ext}");
    let text = "// unicode 🦀\r\napi declaration\r\ncaller api api\r\ntest helper\r\nwire data unchanged\r\n";
    fs::write(d.path().join(&file), text).unwrap();
    let nodes: Vec<_> = [
        ("file", "file", 1usize),
        ("api", "method", 2),
        ("caller", "function", 3),
        ("testHelper", "function", 4),
    ]
    .into_iter()
    .map(|(name, kind, line)| Node {
        id: if kind == "file" {
            format!("{file}::file")
        } else {
            format!("{file}::{name}#{kind}")
        },
        name: name.into(),
        kind: kind.into(),
        file: file.clone(),
        line,
        qualified: name.into(),
        end: 5,
        offset: line * 10,
        length: 10,
        parent: None,
        tags: vec![],
        synthetic: false,
    })
    .collect();
    let edges: Vec<_> = [("calls", 30usize), ("references", 34), ("references", 38)]
        .into_iter()
        .map(|(kind, offset)| Edge {
            source: nodes[2].id.clone(),
            target: nodes[1].id.clone(),
            kind: kind.into(),
            file: file.clone(),
            line: 3,
            offset,
            confidence: "resolved".into(),
        })
        .collect();
    let record = FileRecord {
        file: file.clone(),
        hash: hash(text),
        nodes,
        edges,
        dependencies: vec![],
        diagnostics: vec![],
        unresolved_calls: 0,
        intent: Default::default(),
    };
    let g = Graph::new(Snapshot {
        files: BTreeMap::from([(file, record)]),
        generation: "original".into(),
        ..Default::default()
    });
    (d, c, g)
}
fn request(intent: &str, ext: &str) -> Value {
    let options = match intent {
        "move_symbol" => json!({"destination":format!("moved.{ext}")}),
        "extract_symbol" => json!({"file":format!("api.{ext}"),"start_line":2,"end_line":3}),
        "review_change" => json!({"files":[format!("api.{ext}")]}),
        _ => json!({}),
    };
    json!({"intent":intent,"target":"api","options":options})
}
#[test]
fn ten_intents_ten_languages_use_static_evidence_and_preserve_primitives() {
    for ext in [
        "dart", "ts", "js", "java", "go", "py", "rs", "swift", "m", "kt",
    ] {
        let (_d, c, g) = fixture(ext);
        let mut state = State::default();
        let old = g
            .call(&c, "inspect_change", &json!({"target":"api","limit":1}))
            .unwrap();
        for intent in [
            "rename",
            "change_signature",
            "find_tests",
            "review_change",
            "explain_symbol",
            "trace_flow",
            "move_symbol",
            "remove_symbol",
            "replace_dependency",
            "extract_symbol",
        ] {
            let mut a = request(intent, ext);
            if intent == "review_change" {
                a["target"] = json!(format!("api.{ext}"));
            }
            let v = state.prepare(&g, &c, &a, json!({"mode":"test"})).unwrap();
            assert_eq!(v["intent"], intent);
            assert_eq!(v["generation"], "original");
            assert!(!v["health_fingerprint"].is_null());
            assert!(v.to_string().chars().count() <= 12000);
            if intent == "extract_symbol" {
                assert_eq!(v["outcome"], "unsupported");
                assert!(v["facts"]["suggested_signature"].is_null());
            }
            for group in v["files"].as_array().unwrap() {
                for s in group["snippets"].as_array().unwrap() {
                    let text = fs::read_to_string(c.safe(group["file"].as_str().unwrap()).unwrap())
                        .unwrap();
                    let start = s["start_line"].as_u64().unwrap() as usize;
                    let end = s["end_line"].as_u64().unwrap() as usize;
                    assert_eq!(
                        s["text"],
                        text.split('\n')
                            .skip(start - 1)
                            .take(end - start + 1)
                            .collect::<Vec<_>>()
                            .join("\n")
                    );
                }
            }
        }
        assert_eq!(
            old,
            g.call(&c, "inspect_change", &json!({"target":"api","limit":1}))
                .unwrap()
        );
    }
}
#[test]
fn cursor_budget_dedup_sites_argument_root_and_health_binding() {
    let (_d, c, g) = fixture("dart");
    let mut state = State::default();
    let mut a = json!({"intent":"rename","target":"api","budget":{"max_items":1}});
    let mut records = vec![];
    let mut calls = 0;
    loop {
        let v = state.prepare(&g, &c, &a, json!({})).unwrap();
        records.extend(v["evidence"]["rows"].as_array().unwrap().clone());
        calls += 1;
        if v["next_cursor"].is_null() {
            break;
        }
        a["cursor"] = v["next_cursor"].clone();
    }
    assert_eq!(calls, 4);
    assert_eq!(records.len(), 4);
    assert_eq!(
        records.iter().filter(|r| r[3] == "references").count(),
        2,
        "same-line distinct sites survive dedup"
    );
    let mut bad = a.clone();
    bad["target"] = json!("caller");
    assert!(state.prepare(&g, &c, &bad, json!({})).is_err());
    let mut changed = (*g.snapshot).clone();
    changed
        .files
        .get_mut("api.dart")
        .unwrap()
        .diagnostics
        .push(json!({"code":"new","severity":"error","message":"changed"}));
    let changed = Graph::new(changed);
    let v = state.prepare(&changed, &c, &a, json!({})).unwrap();
    assert_eq!(v["restart_required"], true);
    assert_eq!(v["generation"], "original");
    let mut bad = a.clone();
    bad["cursor"] = json!("f".repeat(64));
    assert_eq!(
        state.prepare(&g, &c, &bad, json!({})).unwrap()["restart_required"],
        true
    );
    let d2 = tempfile::tempdir().unwrap();
    let c2 = Config::load(d2.path(), None).unwrap();
    assert!(state.prepare(&g, &c2, &a, json!({})).is_err());
}
#[test]
fn stale_text_never_mixes_with_old_graph_and_no_refs_is_not_safe() {
    let (d, c, g) = fixture("dart");
    let mut s = State::default();
    fs::write(d.path().join("api.dart"), "changed\n").unwrap();
    let v = s
        .prepare(
            &g,
            &c,
            &json!({"intent":"rename","target":"api"}),
            json!({}),
        )
        .unwrap();
    assert_eq!(v["restart_required"], true);
    assert!(v.get("files").is_none());
}
#[test]
fn typed_options_schema_reject_unknown_incompatible_and_traversal() {
    let (_d, c, g) = fixture("dart");
    let spec = mcp::tools(&c)
        .into_iter()
        .find(|s| s["name"] == "inspect_change")
        .unwrap();
    let mut state = State::default();
    for a in [
        json!({"intent":"unknown","target":"api"}),
        json!({"intent":"rename","target":"api","options":{"destination":"new.dart"}}),
        json!({"intent":"rename","target":"api","budget":{"tokens":1}}),
        json!({"target":"api","options":{}}),
        json!({"intent":"rename","target":"api","budget":{"max_chars":10}}),
        json!({"intent":"rename","target":"api","limit":10}),
    ] {
        assert!(mcp::validate(&spec, &a).is_err(), "{a}");
    }
    for target in ["../outside.dart", "/outside.dart", "C:\\outside.dart"] {
        assert!(
            state
                .prepare(
                    &g,
                    &c,
                    &json!({"target":target,"intent":"rename"}),
                    json!({})
                )
                .is_err()
        );
    }
    let a =
        json!({"intent":"move_symbol","target":"api","options":{"destination":"../outside.dart"}});
    assert!(state.prepare(&g, &c, &a, json!({})).is_err());
    let mut snapshot = (*g.snapshot).clone();
    snapshot.files.get_mut("api.dart").unwrap().nodes[1].qualified = "Class.api".into();
    let mut duplicate = snapshot.files["api.dart"].nodes[1].clone();
    duplicate.id = "api.dart::other.api#method".into();
    duplicate.qualified = "other.api".into();
    snapshot
        .files
        .get_mut("api.dart")
        .unwrap()
        .nodes
        .push(duplicate);
    let ambiguous = Graph::new(snapshot);
    assert!(
        state
            .prepare(
                &ambiguous,
                &c,
                &json!({"intent":"rename","target":"api"}),
                json!({})
            )
            .is_err()
    );
}
#[test]
fn explicit_baseline_detects_deleted_added_and_diagnostics_without_guessing_rename() {
    let (_d, c, g) = fixture("dart");
    let mut s = State::default();
    let capture =
        json!({"target":"api.dart","intent":"review_change","options":{"capture_baseline":true}});
    let before = s.prepare(&g, &c, &capture, json!({})).unwrap();
    let handle = before["facts"]["baseline"]["handle"].clone();
    assert!(handle.is_string());
    let mut snapshot = (*g.snapshot).clone();
    let record = snapshot.files.get_mut("api.dart").unwrap();
    record.nodes[1].id = "api.dart::renamed#method".into();
    record.nodes[1].name = "renamed".into();
    record
        .diagnostics
        .push(json!({"code":"new","message":"new error","severity":"error"}));
    snapshot.generation = "after".into();
    let after = Graph::new(snapshot);
    let v = s
        .prepare(
            &after,
            &c,
            &json!({"target":"api.dart","intent":"review_change","options":{"baseline":handle}}),
            json!({}),
        )
        .unwrap();
    assert_eq!(v["facts"]["comparison_verified"], true);
    assert_eq!(v["facts"]["baseline_generation"], "original");
    assert_eq!(v["sections"]["removed_symbols"]["total"], 1);
    assert_eq!(v["sections"]["added_symbols"]["total"], 1);
    assert_eq!(v["facts"]["diagnostic_changes"][0]["change"], "new");
    let v = s
        .prepare(
            &after,
            &c,
            &json!({"target":"api.dart","intent":"review_change","options":{"baseline":"unknown"}}),
            json!({}),
        )
        .unwrap();
    assert_eq!(v["restart_required"], true);
}

#[test]
fn extraction_uses_ast_identity_and_reports_unproved_signature() {
    let (_d, c, original) = fixture("dart");
    let mut snapshot = (*original.snapshot).clone();
    let scope = snapshot.files["api.dart"].nodes[1].id.clone();
    snapshot.files.get_mut("api.dart").unwrap().intent.ast = json!({
        "version":1,"offset_unit":"utf16",
        "statements":[{"line":3,"end":3,"offset":30,"end_offset":45,"block":20,"scope":scope}],
        "bindings":[{"id":"api.dart@22","name":"input","kind":"parameter","line":2,"offset":22},{"id":"api.dart@32","name":"result","kind":"local","line":3,"offset":32}],
        "uses":[{"line":3,"offset":34,"scope":scope,"binding":"api.dart@22","read":true,"write":true},{"line":4,"offset":46,"scope":scope,"binding":"api.dart@32","read":true,"write":false}],
        "controls":[{"line":3,"offset":40,"kind":"return"}],"limitations":["fixture compiler facts"]
    });
    let g = Graph::new(snapshot);
    let args = json!({"target":"api","intent":"extract_symbol","options":{"file":"api.dart","start_line":3,"end_line":3}});
    let v = State::default().prepare(&g, &c, &args, json!({})).unwrap();
    assert_eq!(v["outcome"], "partial");
    assert_eq!(v["facts"]["capture_reads"]["ids"], json!(["api.dart@22"]));
    assert_eq!(
        v["facts"]["external_mutations"]["ids"],
        json!(["api.dart@22"])
    );
    assert_eq!(
        v["facts"]["locals_used_after"]["ids"],
        json!(["api.dart@32"])
    );
    assert_eq!(v["facts"]["control_exits"]["total"], 1);
    assert!(v["facts"]["suggested_signature"].is_null());
    let mut invalid = args.clone();
    invalid["options"]["start_line"] = json!(2);
    assert!(
        State::default()
            .prepare(&g, &c, &invalid, json!({}))
            .is_err()
    );
    let mut bounded = args;
    bounded["budget"] = json!({"max_traversal":1});
    let limited = State::default()
        .prepare(&g, &c, &bounded, json!({}))
        .unwrap();
    assert_eq!(limited["evidence"]["exploration_limited"], true);
    assert!(limited["evidence"]["total"].is_null());
}

#[test]
fn packed_ast_transport_is_lossless_and_rejects_bad_indexes() {
    let raw = json!({"ast":{"format":"pcg-ast-1","version":1,"offset_unit":"utf16","scopes":["f::fn#function"],"bindings":[["f@2","input","parameter","int",1,1,2,7,0]],"uses":[[2,2,10,15,0,0,true,false]],"statements":[[2,2,8,15,0,7]],"controls":[[3,3,16,22,0,"return"]],"limitations":[]}});
    let context: polycodegraph_core::model::IntentMetadata =
        serde_json::from_value(raw.clone()).unwrap();
    assert_eq!(context.ast["uses"][0]["binding"], "f@2");
    assert_eq!(context.ast["statements"][0]["end_offset"], 15);
    assert_eq!(context.ast["controls"][0]["scope"], "f::fn#function");
    let cached = serde_json::to_value(&context).unwrap();
    let restored: polycodegraph_core::model::IntentMetadata =
        serde_json::from_value(cached).unwrap();
    assert_eq!(context, restored);
    let mut invalid = raw;
    invalid["ast"]["uses"][0][5] = json!(99);
    assert!(serde_json::from_value::<polycodegraph_core::model::IntentMetadata>(invalid).is_err());
}

#[test]
fn baseline_capacity_evicts_oldest_and_keeps_explicit_file_scope() {
    let (_d, c, g) = fixture("ts");
    let mut state = State::default();
    let capture =
        json!({"target":"api.ts","intent":"review_change","options":{"capture_baseline":true}});
    let first =
        state.prepare(&g, &c, &capture, json!({})).unwrap()["facts"]["baseline"]["handle"].clone();
    for _ in 0..2 {
        state.prepare(&g, &c, &capture, json!({})).unwrap();
    }
    let evicted = state
        .prepare(
            &g,
            &c,
            &json!({"target":"api.ts","intent":"review_change","options":{"baseline":first}}),
            json!({}),
        )
        .unwrap();
    assert_eq!(evicted["restart_required"], true);
}

#[test]
fn review_pages_recover_full_new_and_resolved_diagnostics() {
    let (_d, c, original) = fixture("java");
    let mut before = (*original.snapshot).clone();
    let old_message = "old diagnostic ".repeat(60);
    before
        .files
        .get_mut("api.java")
        .unwrap()
        .diagnostics
        .push(json!({"severity":"error","code":"old","line":2,"message":old_message}));
    let old = Graph::new(before.clone());
    let mut state = State::default();
    let handle=state.prepare(&old,&c,&json!({"target":"api.java","intent":"review_change","options":{"capture_baseline":true}}),json!({})).unwrap()["facts"]["baseline"]["handle"].clone();
    before.files.get_mut("api.java").unwrap().diagnostics =
        vec![json!({"severity":"warning","code":"new","line":3,"message":"new diagnostic"})];
    let g = Graph::new(before);
    let mut args = json!({"target":"api.java","intent":"review_change","options":{"baseline":handle},"budget":{"max_items":1}});
    let mut messages = vec![];
    loop {
        let v = state.prepare(&g, &c, &args, json!({})).unwrap();
        messages.extend(
            v["details"]
                .as_object()
                .unwrap()
                .values()
                .map(|d| d["message"].as_str().unwrap().to_owned()),
        );
        if v["next_cursor"].is_null() {
            break;
        }
        args["cursor"] = v["next_cursor"].clone();
    }
    assert!(messages.contains(&old_message));
    assert!(messages.contains(&"new diagnostic".to_string()));
}

#[test]
fn static_flow_reaches_override_alternatives_without_reversing_calls() {
    let (_d, c, g) = fixture("dart");
    let mut snapshot = (*g.snapshot).clone();
    let r = snapshot.files.get_mut("api.dart").unwrap();
    let mut implementation = r.nodes[1].clone();
    implementation.id = "api.dart::implementation#method".into();
    implementation.name = "implementation".into();
    implementation.qualified = "implementation".into();
    let mut leaf = implementation.clone();
    leaf.id = "api.dart::leaf#method".into();
    leaf.name = "leaf".into();
    leaf.qualified = "leaf".into();
    for (source, target, kind, offset) in [
        (&implementation.id, &r.nodes[1].id, "overrides", 41),
        (&implementation.id, &leaf.id, "calls", 42),
        (&leaf.id, &r.nodes[2].id, "calls", 43), // cycle
        (&r.nodes[3].id, &leaf.id, "references", 44),
    ] {
        r.edges.push(Edge {
            source: source.clone(),
            target: target.clone(),
            kind: kind.into(),
            file: "api.dart".into(),
            line: 4,
            offset,
            confidence: "resolved".into(),
        });
    }
    r.unresolved_calls = 1;
    r.nodes.extend([implementation, leaf]);
    let g = Graph::new(snapshot);
    let mut state = State::default();
    let v = state.prepare(&g, &c, &json!({"intent":"trace_flow","target":"caller","depth":4,"options":{"destination":"leaf"}}), json!({})).unwrap();
    assert_eq!(v["facts"]["destination_found"], true);
    assert_eq!(
        v["facts"]["unresolved_frontiers"]["files"][0]["unresolved_calls_in_file"],
        1
    );
    let rows = v["evidence"]["rows"].as_array().unwrap();
    assert!(rows.iter().any(|r| r[3] == "overrides"));
    assert!(!rows.iter().any(|r| r[3] == "references"));
    assert!(!rows.iter().any(|r| r[1] == "api.dart::testHelper#function"));
    let v = state
        .prepare(
            &g,
            &c,
            &json!({"intent":"trace_flow","target":"caller","depth":4}),
            json!({}),
        )
        .unwrap();
    assert!(
        v["evidence"]["rows"].as_array().unwrap().len() <= 5,
        "cycles terminate and sites deduplicate"
    );
}

#[test]
fn explain_focus_prioritizes_direct_dependencies_and_class_implementations() {
    let (_d, c, g) = fixture("dart");
    let mut snapshot = (*g.snapshot).clone();
    let r = snapshot.files.get_mut("api.dart").unwrap();
    r.edges.push(Edge {
        source: r.nodes[1].id.clone(),
        target: r.nodes[3].id.clone(),
        kind: "calls".into(),
        file: "api.dart".into(),
        line: 2,
        offset: 25,
        confidence: "resolved".into(),
    });
    r.edges.push(Edge {
        source: r.nodes[2].id.clone(),
        target: r.nodes[1].id.clone(),
        kind: "implements".into(),
        file: "api.dart".into(),
        line: 3,
        offset: 35,
        confidence: "resolved".into(),
    });
    let g = Graph::new(snapshot);
    let mut state = State::default();
    for (focus, expected) in [("dependencies", "calls"), ("implementation", "implements")] {
        let mut a = json!({"intent":"explain_symbol","target":"api","options":{"focus":focus},"budget":{"max_items":1}});
        let first = state.prepare(&g, &c, &a, json!({})).unwrap();
        assert_eq!(first["evidence"]["rows"][0][3], "declaration");
        a["cursor"] = first["next_cursor"].clone();
        let page = state.prepare(&g, &c, &a, json!({})).unwrap();
        assert_eq!(page["evidence"]["rows"][0][3], expected);
    }
}

#[test]
fn review_detects_body_only_source_edit_and_retains_conservative_consumers() {
    let (d, c, original) = fixture("ts");
    let mut state = State::default();
    let handle = state.prepare(&original, &c, &json!({"intent":"review_change","target":"api.ts","options":{"capture_baseline":true}}), json!({})).unwrap()["facts"]["baseline"]["handle"].clone();
    let text = fs::read_to_string(d.path().join("api.ts"))
        .unwrap()
        .replace("wire data unchanged", "wire date unchanged");
    fs::write(d.path().join("api.ts"), &text).unwrap();
    let mut snapshot = (*original.snapshot).clone();
    snapshot.files.get_mut("api.ts").unwrap().hash = hash(&text);
    snapshot.generation = "body-edited".into();
    let edited = Graph::new(snapshot);
    let v = state
        .prepare(
            &edited,
            &c,
            &json!({"intent":"review_change","target":"api.ts","options":{"baseline":handle}}),
            json!({}),
        )
        .unwrap();
    assert_eq!(v["sections"]["source_changes"]["total"], 1);
    assert!(v["sections"]["file_context"]["total"].as_u64().unwrap() > 0);
    assert!(
        v["sections"]["affected_consumers"]["total"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert!(v["sections"].get("changed_symbols").is_none());
    assert_eq!(v["outcome"], "partial");
    assert!(
        v["details"]
            .as_object()
            .unwrap()
            .values()
            .any(|v| v["before_hash"] != v["after_hash"])
    );
}
