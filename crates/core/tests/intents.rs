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
fn intent_source_policy_preserves_all_sites_and_respects_explicit_view() {
    let (_d, c, g) = fixture("ts");
    let mut state = State::default();
    let original = state
        .prepare(
            &g,
            &c,
            &json!({"intent":"rename","target":"api","format":"lean"}),
            json!({}),
        )
        .unwrap();
    let locations = state
        .prepare(
            &g,
            &c,
            &json!({"intent":"rename","target":"api","format":"lean","source_policy":"intent"}),
            json!({}),
        )
        .unwrap();
    assert_eq!(original["records"], locations["records"]);
    assert_eq!(locations["sources"], json!([]));
    assert_eq!(locations["source_selection"]["view"], "locations");
    let explicit = state.prepare(&g, &c, &json!({"intent":"rename","target":"api","format":"lean","source_policy":"intent","view":"full_evidence"}), json!({})).unwrap();
    assert_eq!(explicit["records"], original["records"]);
    assert!(!explicit["sources"].as_array().unwrap().is_empty());
    let signature = state.prepare(&g, &c, &json!({"intent":"change_signature","target":"api","format":"lean","source_policy":"intent"}), json!({})).unwrap();
    assert_eq!(signature["source_selection"]["view"], "contracts");
}
#[test]
fn lexical_anchor_groups_do_not_let_repeated_lines_hide_other_anchors() {
    let (d, c, g) = fixture("ts");
    let text = format!(
        "function api() {{\n{}\n}}\nfunction caller() {{ throw 'échec réseau'; }}\n",
        "  throw 'échec réseau';\n".repeat(50)
    );
    fs::write(d.path().join("api.ts"), &text).unwrap();
    let mut snapshot = (*g.snapshot).clone();
    let record = snapshot.files.get_mut("api.ts").unwrap();
    record.hash = hash(text);
    record.nodes.retain(|n| n.name != "testHelper");
    record.nodes[1].line = 1;
    record.nodes[1].end = 53;
    record.nodes[2].line = 54;
    record.nodes[2].end = 54;
    let g = Graph::new(snapshot);
    let args = json!({"query":"échec réseau","mode":"lexical","limit":2});
    let line = g.call(&c, "search_symbol", &args).unwrap();
    assert_eq!(line["rows"][0][2], line["rows"][1][2]);
    let mut grouped = args.clone();
    grouped["group_by"] = json!("anchor");
    let anchors = g.call(&c, "search_symbol", &grouped).unwrap();
    assert_eq!(anchors["rows"].as_array().unwrap().len(), 2);
    assert_ne!(anchors["rows"][0][2], anchors["rows"][1][2]);
    assert!(anchors["rows"][0][5].as_u64().unwrap() >= 50);
    let mut details = args;
    details["anchor"] = anchors["rows"][0][2].clone();
    let details = g.call(&c, "search_symbol", &details).unwrap();
    assert_eq!(details["discovered_total"], anchors["rows"][0][5]);
    grouped["ranking"] = json!("bm25");
    let ablation = g.call(&c, "search_symbol", &grouped).unwrap();
    assert_eq!(ablation, g.call(&c, "search_symbol", &grouped).unwrap());
    assert_eq!(ablation["discovered_total"], anchors["discovered_total"]);
    fs::write(d.path().join("api.ts"), "changed source").unwrap();
    assert!(
        g.call(&c, "search_symbol", &grouped)
            .unwrap_err()
            .to_string()
            .contains("stale")
    );
}
#[test]
fn lexical_scope_builds_before_global_caps_and_reports_excluded_files() {
    let (d, c, g) = fixture("ts");
    let text = "noise\n".repeat(100001);
    fs::write(d.path().join("a.ts"), &text).unwrap();
    let mut snapshot = (*g.snapshot).clone();
    snapshot.files.insert(
        "a.ts".into(),
        FileRecord {
            file: "a.ts".into(),
            hash: hash(text),
            nodes: vec![],
            edges: vec![],
            dependencies: vec![],
            diagnostics: vec![],
            unresolved_calls: 0,
            intent: Default::default(),
        },
    );
    let g = Graph::new(snapshot);
    let global = g
        .call(
            &c,
            "search_symbol",
            &json!({"query":"wire","mode":"lexical"}),
        )
        .unwrap();
    assert_eq!(global["index"]["incomplete"], true);
    assert_eq!(global["total"], Value::Null);
    assert_eq!(global["index"]["excluded_files"]["api.ts"], "line_budget");
    let scoped = g
        .call(
            &c,
            "search_symbol",
            &json!({"query":"wire","mode":"lexical","file":"api.ts"}),
        )
        .unwrap();
    assert_eq!(scoped["index"]["incomplete"], false);
    assert_eq!(scoped["rows"].as_array().unwrap().len(), 1);
    assert_eq!(scoped["index"]["files"], 1);
    assert_eq!(scoped["index"]["scope"]["file"], "api.ts");
    for query in [
        json!({"query":"wire","mode":"lexical","language":"typescript"}),
        json!({"query":"wire","mode":"lexical","file":"api.ts"}),
    ] {
        g.call(&c, "search_symbol", &query).unwrap();
    }
    // File-filter validation rejects traversal before scoped source access.
    assert!(
        g.call(
            &c,
            "search_symbol",
            &json!({"query":"wire","mode":"lexical","file":"../api.ts"})
        )
        .is_err()
    );
}
#[test]
fn separate_source_budget_keeps_required_inventory_and_visible_truncation() {
    let (_d, c, g) = fixture("ts");
    let mut state = State::default();
    let args = json!({"intent":"rename","target":"api","format":"lean","view":"full_evidence"});
    let original = state.prepare(&g, &c, &args, json!({})).unwrap();
    for size in [0, 8, 32] {
        let mut bounded = args.clone();
        bounded["budget"] = json!({"max_source_chars":size});
        let result = state.prepare(&g, &c, &bounded, json!({})).unwrap();
        assert_eq!(original["records"], result["records"]);
        assert!(
            result["source_selection"]["emitted_source_chars"]
                .as_u64()
                .unwrap()
                <= size
        );
        assert_eq!(result["source_windows_incomplete"], true);
        assert_eq!(
            result["completion"]["required_inventory"],
            original["completion"]["required_inventory"]
        );
    }
    let mut invalid = args;
    invalid["budget"] = json!({"max_source_chars":100001});
    assert!(state.prepare(&g, &c, &invalid, json!({})).is_err());
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
fn review_detects_source_edit_without_claiming_all_declarations_changed() {
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
    assert_eq!(
        v["facts"]["localization"][0]["seeds"]
            .as_array()
            .unwrap()
            .len(),
        1
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

fn large_review(count: usize) -> (tempfile::TempDir, Config, Graph, String) {
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    let text: String = (0..count)
        .map(|i| format!("function f{i}() {{ return 0; }}\n"))
        .collect();
    fs::write(d.path().join("sample.ts"), &text).unwrap();
    let nodes = (0..count)
        .map(|i| Node {
            id: format!("sample.ts::f{i}#function"),
            name: format!("f{i}"),
            qualified: format!("f{i}"),
            kind: "function".into(),
            file: "sample.ts".into(),
            line: i + 1,
            end: i + 1,
            offset: 0,
            length: 1,
            parent: None,
            tags: vec![],
            synthetic: false,
        })
        .collect();
    let record = FileRecord {
        file: "sample.ts".into(),
        hash: hash(&text),
        nodes,
        edges: vec![],
        dependencies: vec![],
        diagnostics: vec![],
        unresolved_calls: 0,
        intent: Default::default(),
    };
    let g = Graph::new(Snapshot {
        files: BTreeMap::from([("sample.ts".into(), record)]),
        generation: "before".into(),
        ..Default::default()
    });
    (d, c, g, text)
}
#[test]
fn large_review_limits_stay_constant_and_pages_exhaust_the_inventory() {
    let mut warning_count = None;
    for count in [1, 40, 100, 140] {
        let (d, c, g, text) = large_review(count);
        let mut s = State::default();
        let capture=s.prepare(&g,&c,&json!({"intent":"review_change","target":"sample.ts","options":{"capture_baseline":true},"budget":{"max_chars":100000}}),json!({})).unwrap();
        let text = text.replacen("return 0", "return 1", 1);
        fs::write(d.path().join("sample.ts"), &text).unwrap();
        let mut snapshot = (*g.snapshot).clone();
        snapshot.files.get_mut("sample.ts").unwrap().hash = hash(&text);
        snapshot.generation = "after".into();
        let after = Graph::new(snapshot);
        let mut args = json!({"intent":"review_change","target":"sample.ts","options":{"baseline":capture["facts"]["baseline"]["handle"]}});
        let mut ids = std::collections::BTreeSet::new();
        let mut iterations = 0;
        loop {
            let v = s.prepare(&after, &c, &args, json!({})).unwrap();
            iterations += 1;
            assert!(iterations < 200);
            let n = v["limits"].as_array().unwrap().len();
            assert_eq!(*warning_count.get_or_insert(n), n);
            for row in v["evidence"]["rows"].as_array().unwrap() {
                assert!(ids.insert(row[0].as_str().unwrap().to_owned()));
            }
            assert_eq!(
                v["evidence"]["page_count"].as_u64().unwrap() as usize,
                v["evidence"]["rows"].as_array().unwrap().len()
            );
            if v["next_cursor"].is_null() {
                assert_eq!(v["evidence"]["remaining_after_page"], 0);
                assert_eq!(v["evidence"]["collection_complete"], true);
                break;
            }
            assert!(v["evidence"]["remaining_after_page"].as_u64().unwrap() > 0);
            args["cursor"] = v["next_cursor"].clone();
        }
        assert_eq!(ids.len(), 2, "one source event and one changed declaration");
    }
}

fn edited_graph(g: &Graph, file: &str, text: &str) -> Graph {
    let mut snapshot = (*g.snapshot).clone();
    snapshot.files.get_mut(file).unwrap().hash = hash(text);
    snapshot.generation = hash(text)[..20].into();
    Graph::new(snapshot)
}
#[test]
fn minimal_capture_uses_current_working_tree_and_localizes_body_contract_and_formatting() {
    for (replacement, expected) in [
        ("return 9", "body"),
        ("function f0(value: number)", "contract_or_initializer"),
        ("\nfunction f0", "formatting"),
    ] {
        let (d, c, g, text) = large_review(140);
        // The captured baseline already differs from any putative clean checkout.
        let before = text.replacen("return 0", "return 7", 1);
        fs::write(d.path().join("sample.ts"), &before).unwrap();
        let g = edited_graph(&g, "sample.ts", &before);
        let mut s = State::default();
        let capture=s.prepare(&g,&c,&json!({"target":"sample.ts","intent":"review_change","options":{"capture_baseline":true,"capture_mode":"minimal"}}),json!({})).unwrap();
        assert!(capture["evidence"]["rows"].as_array().unwrap().is_empty());
        let after = match expected {
            "body" => before.replacen("return 7", replacement, 1),
            "formatting" => before.replacen("function f0", replacement, 1),
            _ => before.replacen("function f0()", replacement, 1),
        };
        fs::write(d.path().join("sample.ts"), &after).unwrap();
        let mut updated = (*g.snapshot).clone();
        updated.files.get_mut("sample.ts").unwrap().hash = hash(&after);
        updated.generation = "new".into();
        if expected == "formatting" {
            for n in &mut updated.files.get_mut("sample.ts").unwrap().nodes {
                n.line += 1;
                n.end += 1;
            }
        }
        let after = Graph::new(updated);
        let v=s.prepare(&after,&c,&json!({"target":"sample.ts","intent":"review_change","options":{"baseline":capture["facts"]["baseline"]["handle"]},"view":"locations"}),json!({})).unwrap();
        assert_eq!(v["facts"]["localization"][0]["kind"], expected);
        assert_eq!(v["facts"]["baseline_generation"], g.snapshot.generation);
        assert!(v["evidence"]["rows"].as_array().unwrap().len() <= 2);
        for f in v["files"].as_array().unwrap() {
            assert!(f["snippets"].as_array().unwrap().is_empty());
        }
    }
}
#[test]
fn import_fallback_and_removed_declaration_keep_cross_file_consumers() {
    let (d, c, g, text) = large_review(3);
    let mut snapshot = (*g.snapshot).clone();
    let caller = Node {
        id: "use.ts::caller#function".into(),
        name: "caller".into(),
        qualified: "caller".into(),
        file: "use.ts".into(),
        line: 1,
        end: 1,
        kind: "function".into(),
        offset: 0,
        length: 1,
        parent: None,
        tags: vec![],
        synthetic: false,
    };
    let edge = Edge {
        source: caller.id.clone(),
        target: "sample.ts::f0#function".into(),
        kind: "calls".into(),
        file: "use.ts".into(),
        line: 1,
        offset: 1,
        confidence: "resolved".into(),
    };
    fs::write(d.path().join("use.ts"), "function caller() { f0(); }\n").unwrap();
    snapshot.files.insert(
        "use.ts".into(),
        FileRecord {
            file: "use.ts".into(),
            hash: hash("function caller() { f0(); }\n"),
            nodes: vec![caller],
            edges: vec![edge],
            dependencies: vec![],
            diagnostics: vec![],
            unresolved_calls: 0,
            intent: Default::default(),
        },
    );
    let g = Graph::new(snapshot);
    let mut s = State::default();
    let capture=s.prepare(&g,&c,&json!({"target":"sample.ts","intent":"review_change","options":{"capture_baseline":true,"capture_mode":"minimal"}}),json!({})).unwrap();
    let new_text = format!("import './use';\n{text}");
    fs::write(d.path().join("sample.ts"), &new_text).unwrap();
    let mut snapshot = (*g.snapshot).clone();
    let r = snapshot.files.get_mut("sample.ts").unwrap();
    r.hash = hash(&new_text);
    for n in &mut r.nodes {
        n.line += 1;
        n.end += 1;
    }
    snapshot.generation = "imports".into();
    let after = Graph::new(snapshot);
    let v=s.prepare(&after,&c,&json!({"target":"sample.ts","intent":"review_change","options":{"baseline":capture["facts"]["baseline"]["handle"]},"view":"locations"}),json!({})).unwrap();
    assert!(v["facts"]["localization"][0]["fallback"].is_string());
    assert_eq!(v["sections"]["affected_consumers"]["total"], 1);
    let mut snapshot = (*g.snapshot).clone();
    snapshot.files.remove("sample.ts");
    snapshot.generation = "deleted".into();
    fs::remove_file(d.path().join("sample.ts")).unwrap();
    let after = Graph::new(snapshot);
    let v=s.prepare(&after,&c,&json!({"target":"sample.ts","intent":"review_change","options":{"baseline":capture["facts"]["baseline"]["handle"]},"view":"locations"}),json!({})).unwrap();
    assert!(
        v["evidence"]["rows"]
            .as_array()
            .unwrap()
            .iter()
            .any(|r| r[3] == "calls" && r[10] == "before")
    );
    assert_eq!(v["facts"]["files"], json!(["sample.ts"]));
}
#[test]
fn explicit_missing_file_scope_can_compare_an_addition() {
    let (d, c, g, _) = large_review(1);
    let mut s = State::default();
    let capture=s.prepare(&g,&c,&json!({"target":"new.ts","intent":"review_change","options":{"files":["new.ts"],"capture_baseline":true,"capture_mode":"minimal"}}),json!({})).unwrap();
    fs::write(d.path().join("new.ts"), "function created() {}\n").unwrap();
    let mut snapshot = (*g.snapshot).clone();
    let mut record = snapshot.files["sample.ts"].clone();
    record.file = "new.ts".into();
    record.hash = hash("function created() {}\n");
    for n in &mut record.nodes {
        n.file = "new.ts".into();
        n.id = "new.ts::created#function".into();
        n.name = "created".into();
        n.qualified = "created".into();
    }
    snapshot.files.insert("new.ts".into(), record);
    let after = Graph::new(snapshot);
    let v=s.prepare(&after,&c,&json!({"target":"new.ts","intent":"review_change","options":{"baseline":capture["facts"]["baseline"]["handle"]},"view":"locations"}),json!({})).unwrap();
    assert_eq!(v["sections"]["added_symbols"]["total"], 1);
    assert_eq!(v["sections"]["source_changes"]["total"], 1);
}
#[test]
fn views_acknowledgement_rehydrate_and_semantic_invalidation_preserve_sites() {
    let (_d, c, g) = fixture("dart");
    let mut s = State::default();
    let args = json!({"intent":"rename","target":"api","view":"contracts"});
    let first = s.prepare(&g, &c, &args, json!({})).unwrap();
    let windows: Vec<_> = first["files"]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|f| f["snippets"].as_array().unwrap())
        .map(|w| w["window_id"].clone())
        .collect();
    assert!(!windows.is_empty());
    let mut context = json!({"epoch":"one","root_id":first["context"]["root_id"],"generation":first["generation"],"health_fingerprint":first["health_fingerprint"],"environment_fingerprint":g.snapshot.environment,"known_windows":windows});
    let mut acknowledged = args.clone();
    acknowledged["context"] = context.clone();
    let second = s.prepare(&g, &c, &acknowledged, json!({})).unwrap();
    assert!(second["context"]["suppressed_windows"].as_u64().unwrap() > 0);
    assert_eq!(second["evidence"], first["evidence"]);
    assert!(second.to_string().len() < first.to_string().len() + 300); // tiny fixture may be smaller than protocol overhead
    for w in second["files"]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|f| f["snippets"].as_array().unwrap())
    {
        assert!(w.get("text").is_none());
    }
    context["epoch"] = json!("after-compaction");
    context["rehydrate"] = json!(true);
    acknowledged["context"] = context.clone();
    let rehydrated = s.prepare(&g, &c, &acknowledged, json!({})).unwrap();
    assert_eq!(rehydrated["context"]["suppressed_windows"], 0);
    for change in ["health", "dependency"] {
        let mut snapshot = (*g.snapshot).clone();
        if change == "health" {
            snapshot
                .files
                .get_mut("api.dart")
                .unwrap()
                .diagnostics
                .push(json!({"code":"new","severity":"error","message":"new coverage problem"}));
        } else {
            snapshot.environment = "new-dependency".into();
        }
        let new = Graph::new(snapshot);
        context["rehydrate"] = json!(false);
        acknowledged["context"] = context.clone();
        let v = s.prepare(&new, &c, &acknowledged, json!({})).unwrap();
        assert_eq!(v["context"]["reset_required"], true);
        assert_eq!(v["context"]["suppressed_windows"], 0);
    }
    let locations = s
        .prepare(
            &g,
            &c,
            &json!({"intent":"rename","target":"api","view":"locations"}),
            json!({}),
        )
        .unwrap();
    assert_eq!(locations["evidence"], first["evidence"]);
    assert!(
        locations["files"]
            .as_array()
            .unwrap()
            .iter()
            .all(|f| f["snippets"].as_array().unwrap().is_empty())
    );
}
#[test]
fn collection_cap_is_explicit_and_token_budget_counts_the_whole_result() {
    let (_d, c, g) = fixture("dart");
    let mut s = State::default();
    let v=s.prepare(&g,&c,&json!({"intent":"rename","target":"api","view":"locations","budget":{"max_collection_items":1,"max_tokens":2048}}),json!({})).unwrap();
    assert_eq!(v["evidence"]["page_count"], 1);
    assert_eq!(v["evidence"]["remaining_after_page"], 3);
    assert_eq!(v["evidence"]["collection_complete"], false);
    assert!(v["next_cursor"].is_null());
    assert!(
        v["limit_causes"]
            .as_array()
            .unwrap()
            .contains(&json!("collection_budget"))
    );
    assert_eq!(
        v["token_budget"]["estimated_tokens"].as_u64().unwrap() as usize,
        v.to_string().chars().count().div_ceil(4)
    );
    assert!(s.prepare(&g,&c,&json!({"intent":"rename","target":"api","view":"locations","budget":{"max_tokens":256}}),json!({})).is_err());
}
#[test]
fn relation_budget_reaches_contracts_before_large_reference_fan_in() {
    let (_d, c, g) = fixture("dart");
    let mut snapshot = (*g.snapshot).clone();
    let r = snapshot.files.get_mut("api.dart").unwrap();
    r.edges.push(Edge {
        source: r.nodes[3].id.clone(),
        target: r.nodes[1].id.clone(),
        kind: "overrides".into(),
        file: "api.dart".into(),
        line: 4,
        offset: 44,
        confidence: "resolved".into(),
    });
    for i in 0..1000 {
        let mut edge = r.edges[1].clone();
        edge.offset = 100 + i;
        r.edges.push(edge);
    }
    let g = Graph::new(snapshot);
    let v=State::default().prepare(&g,&c,&json!({"intent":"rename","target":"api","view":"locations","budget":{"max_traversal":1010,"max_chars":100000}}),json!({})).unwrap();
    assert_eq!(v["evidence"]["exploration_limited"], false);
    assert_eq!(v["sections"]["contracts"]["discovered_total"], 1);
    assert_eq!(v["sections"]["usages"]["discovered_total"], 1003);
}
#[test]
fn explicit_explain_focus_selects_sections_and_lexical_matches_do_not_invent_edges() {
    let (_d, c, g) = fixture("ts");
    let mut s = State::default();
    let v=s.prepare(&g,&c,&json!({"intent":"explain_symbol","target":"api","options":{"focus":"dependencies"},"view":"locations"}),json!({})).unwrap();
    assert!(v["sections"].get("consumers").is_none());
    assert!(v["facts"]["optional_expansions"].is_array());
    let before = g.edges.len();
    let lexical = g
        .call(
            &c,
            "search_symbol",
            &json!({"query":"wire unchanged","mode":"lexical"}),
        )
        .unwrap();
    assert!(!lexical["rows"].as_array().unwrap().is_empty());
    assert_eq!(g.edges.len(), before);
    assert!(
        lexical["expansion"]["relations"]
            .as_array()
            .unwrap()
            .is_empty()
    );
    let expanded = g
        .call(
            &c,
            "search_symbol",
            &json!({"query":"api declaration","mode":"lexical","expand":"callers"}),
        )
        .unwrap();
    assert!(
        !expanded["expansion"]["relations"]
            .as_array()
            .unwrap()
            .is_empty()
    );
}

#[test]
fn destination_trace_excludes_large_reachable_side_branch() {
    let (_d, c, g) = fixture("dart");
    let mut snapshot = (*g.snapshot).clone();
    let r = snapshot.files.get_mut("api.dart").unwrap();
    r.edges.clear();
    let prototype = r.nodes[1].clone();
    for id in ["A", "B", "D", "C"]
        .into_iter()
        .map(str::to_owned)
        .chain((0..100).map(|i| format!("side{i}")))
    {
        let mut n = prototype.clone();
        n.id = id.clone();
        n.name = id.clone();
        n.qualified = id;
        r.nodes.push(n);
    }
    for (i, (source, target)) in [
        ("A".to_owned(), "B".to_owned()),
        ("B".to_owned(), "D".to_owned()),
        ("A".to_owned(), "C".to_owned()),
    ]
    .into_iter()
    .chain((0..100).map(|i| {
        (
            if i == 0 {
                "C".into()
            } else {
                format!("side{}", i - 1)
            },
            format!("side{i}"),
        )
    }))
    .enumerate()
    {
        r.edges.push(Edge {
            source,
            target,
            kind: "calls".into(),
            file: "api.dart".into(),
            line: 1,
            offset: i,
            confidence: "resolved".into(),
        });
    }
    let g = Graph::new(snapshot);
    let result=State::default().prepare(&g,&c,&json!({"intent":"trace_flow","target":"A","view":"locations","depth":10,"options":{"destination":"D"}}),json!({})).unwrap();
    assert_eq!(result["facts"]["destination_found"], true);
    let rows = result["evidence"]["rows"].as_array().unwrap();
    let symbols = result["symbols"]["rows"].as_array().unwrap();
    assert!(
        rows.iter()
            .any(|r| symbols[r[1].as_u64().unwrap() as usize][0] == "B"
                && symbols[r[2].as_u64().unwrap() as usize][0] == "D")
    );
    assert!(
        !symbols
            .iter()
            .any(|r| r[0] == "C" || r[0].as_str().unwrap().starts_with("side"))
    );
    assert!(
        !rows
            .iter()
            .any(|r| r[1] == "C" || r[2] == "C" || r.to_string().contains("side"))
    );
}

#[test]
fn edit_context_keeps_a_late_review_hunk_in_a_large_function() {
    let (d, c, g, _) = large_review(1);
    let before = format!(
        "function f0() {{\n{}return 0;\n}}\n",
        (0..300)
            .map(|i| format!("// line {i}\n"))
            .collect::<String>()
    );
    fs::write(d.path().join("sample.ts"), &before).unwrap();
    let mut snapshot = (*g.snapshot).clone();
    let record = snapshot.files.get_mut("sample.ts").unwrap();
    record.hash = hash(&before);
    for n in &mut record.nodes {
        n.line = 1;
        n.end = 303;
        n.offset = 0;
        n.length = before.len();
    }
    let g = Graph::new(snapshot);
    let mut state = State::default();
    let captured=state.prepare(&g,&c,&json!({"intent":"review_change","target":"sample.ts","options":{"capture_baseline":true,"capture_mode":"minimal"}}),json!({})).unwrap();
    let after = before.replace("return 0;", "return 1;");
    fs::write(d.path().join("sample.ts"), &after).unwrap();
    let g = edited_graph(&g, "sample.ts", &after);
    let response=state.prepare(&g,&c,&json!({"intent":"review_change","target":"sample.ts","view":"edit_context","options":{"baseline":captured["facts"]["baseline"]["handle"]}}),json!({})).unwrap();
    let windows = response["files"][0]["snippets"].as_array().unwrap();
    assert!(
        windows
            .iter()
            .any(|w| w["text"].as_str().unwrap().contains("return 1;"))
    );
    assert!(
        windows
            .iter()
            .all(|w| w["text"].as_str().unwrap().lines().count() < 10)
    );
}

#[test]
fn lexical_no_match_does_not_return_unanchored_unrelated_lines() {
    let (_d, c, g) = fixture("dart");
    let response = g
        .call(
            &c,
            "search_symbol",
            &json!({"query":"notPresentAnywhere","mode":"lexical"}),
        )
        .unwrap();
    assert!(response["rows"].as_array().unwrap().is_empty());
    assert_eq!(response["discovered_total"], 0);
}

#[test]
fn deleted_file_review_source_views_keep_historical_ids_without_current_windows() {
    let (d, c, g) = fixture("dart");
    let mut state = State::default();
    let capture=state.prepare(&g,&c,&json!({"intent":"review_change","target":"api.dart","options":{"capture_baseline":true,"capture_mode":"minimal"}}),json!({})).unwrap();
    fs::remove_file(d.path().join("api.dart")).unwrap();
    let after = Graph::new(Snapshot {
        generation: "deleted".into(),
        ..Default::default()
    });
    for view in ["edit_context", "full_evidence"] {
        let response=state.prepare(&after,&c,&json!({"intent":"review_change","target":"api.dart","options":{"baseline":capture["facts"]["baseline"]["handle"]},"view":view}),json!({})).unwrap();
        assert!(
            response["symbols"]["rows"]
                .as_array()
                .unwrap()
                .iter()
                .any(|r| r[0] == "api.dart::api#method" && r[5] == "before")
        );
        assert!(
            response["files"]
                .as_array()
                .unwrap()
                .iter()
                .all(|f| f["snippets"].as_array().unwrap().is_empty())
        );
    }
}
