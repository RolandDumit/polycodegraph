use polycodegraph_core::{
    config::Config,
    intents::State,
    model::{Edge, FileRecord, Node, Snapshot, hash},
    query::Graph,
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs};

fn graph(text: &str, generation: &str) -> Graph {
    let file = "sample.ts";
    let node = |name: &str, kind: &str, line: usize| Node {
        id: format!("{file}::{name}#{kind}"),
        name: name.into(),
        kind: kind.into(),
        file: file.into(),
        line,
        end: text.lines().count(),
        qualified: name.into(),
        offset: 0,
        length: 0,
        parent: None,
        tags: vec![],
        synthetic: false,
    };
    let mut edges = vec![];
    let mut offset = 0;
    for (line, text) in text.split_inclusive('\n').enumerate() {
        if text.trim_start().starts_with("target(") {
            for (column, _) in text.match_indices("target(") {
                edges.push(Edge {
                    source: "sample.ts::caller#function".into(),
                    target: "sample.ts::target#function".into(),
                    kind: "calls".into(),
                    file: file.into(),
                    line: line + 1,
                    offset: offset + text[..column].encode_utf16().count(),
                    confidence: "resolved".into(),
                });
            }
        }
        offset += text.encode_utf16().count();
    }
    Graph::new(Snapshot {
        generation: generation.into(),
        files: BTreeMap::from([(
            file.into(),
            FileRecord {
                file: file.into(),
                hash: hash(text),
                nodes: vec![
                    node("file", "file", 1),
                    node("caller", "function", 1),
                    node("target", "function", 1),
                ],
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

fn review(before: &str, after: &str) -> Value {
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    fs::write(d.path().join("sample.ts"), before).unwrap();
    let mut s = State::default();
    let baseline = s.prepare(&graph(before, "before"), &c,
        &json!({"intent":"review_change","target":"sample.ts","options":{"capture_baseline":true,"capture_mode":"minimal"}}), json!({})).unwrap();
    fs::write(d.path().join("sample.ts"), after).unwrap();
    s.prepare(&graph(after, "after"), &c, &json!({"intent":"review_change","target":"sample.ts","view":"locations",
        "options":{"baseline":baseline["facts"]["baseline"]["handle"]},"budget":{"max_items":200,"max_chars":100000}}), json!({})).unwrap()
}

#[test]
fn review_repositions_one_hundred_sites_without_semantic_delta() {
    let text = format!(
        "function caller() {{\r\n{} }}\r\nfunction target(x: number) {{}}\r\n",
        (0..100)
            .map(|i| format!("  target({i});\r\n"))
            .collect::<String>()
    );
    let page = review(&text, &format!("// 🦀 unchanged sites below\r\n\r\n{text}"));
    assert!(
        page["sections"].get("removed_relations").is_none(),
        "{page}"
    );
    assert!(page["sections"].get("added_relations").is_none(), "{page}");
    assert_eq!(page["sections"]["source_changes"]["total"], 1);
}

#[test]
fn unchanged_same_line_sites_keep_distinct_offsets() {
    let text = "function caller() {\n  target(1); target(2);\n}\nfunction target(x: number) {}\n";
    let page = review(text, &format!("// prefix\n{text}"));
    assert!(
        page["sections"].get("removed_relations").is_none(),
        "{page}"
    );
    assert!(page["sections"].get("added_relations").is_none(), "{page}");
}

#[test]
fn deleted_duplicate_preserves_cardinality_and_mapping_uncertainty() {
    let distinct = review(
        "begin\n  target(1); target(2);\nend\n",
        "begin\n  target(2);\nend\n",
    );
    assert_eq!(distinct["sections"]["removed_relations"]["total"], 1);
    assert!(distinct["sections"].get("added_relations").is_none());
    let identical = review(
        "begin\n  target(1); target(1);\nend\n",
        "begin\n  target(1);\nend\n",
    );
    assert_eq!(
        identical["facts"]["relation_changes"][0]["removed_multiplicity"],
        1
    );
    assert_eq!(
        identical["facts"]["relation_changes"][0]["uncertain_mapping"],
        2
    );
    assert_eq!(identical["sections"]["removed_relations"]["total"], 2);
    assert_eq!(identical["sections"]["added_relations"]["total"], 1);
}

#[test]
fn multiple_insertions_and_deletions_preserve_unique_unchanged_sites() {
    let page = review(
        "begin\n  target(1);\n// deleted\n  target(2);\n  target(3);\nend\n",
        "// new\nbegin\n  target(1);\n  target(2);\n// between\n  target(3);\nend\n",
    );
    assert!(page["sections"].get("removed_relations").is_none());
    assert!(page["sections"].get("added_relations").is_none());
    assert_eq!(page["facts"]["relation_changes"][0]["relocated"], 3);
}

#[test]
fn strict_capture_rejects_typos_excluded_files_and_changed_scope() {
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    let text = "function caller() {\n  target(1);\n}\n";
    fs::write(d.path().join("sample.ts"), text).unwrap();
    fs::write(d.path().join("excluded.ts"), text).unwrap();
    let g = graph(text, "before");
    let mut s = State::default();
    for (file, expected) in [
        ("wrong/sample.ts", "root-relative candidates"),
        ("excluded.ts", "outside the indexed scope"),
        ("../sample.ts", "traversal"),
    ] {
        let error = s.prepare(&g,&c,&json!({"target":file,"intent":"review_change","options":{"capture_baseline":true,"strict_scope":true}}),json!({})).unwrap_err();
        assert!(error.to_string().contains(expected), "{error}");
    }
    let capture = s.prepare(&g,&c,&json!({"target":"sample.ts","intent":"review_change","options":{"capture_baseline":true,"strict_scope":true,"capture_mode":"minimal"}}),json!({})).unwrap();
    assert_eq!(capture["facts"]["baseline"]["existing_files_captured"], 1);
    assert_eq!(capture["facts"]["baseline"]["new_files_admitted"], 0);
    assert!(s.prepare(&g,&c,&json!({"target":"new.ts","intent":"review_change","options":{"baseline":capture["facts"]["baseline"]["handle"],"strict_scope":true}}),json!({})).unwrap_err().to_string().contains("file scope"));
    assert!(s.prepare(&g,&c,&json!({"target":"sample.ts","intent":"review_change","options":{"baseline":capture["facts"]["baseline"]["handle"]}}),json!({})).unwrap_err().to_string().contains("strict_scope"));
}

#[test]
fn strict_future_creation_is_explicit_and_legacy_remains_available() {
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    let g = graph("", "before");
    let mut s = State::default();
    assert!(s.prepare(&g,&c,&json!({"intent":"review_change","target":"future.ts","format":"lean","options":{"capture_baseline":true}}),json!({})).is_err());
    let capture = s.prepare(&g,&c,&json!({"intent":"review_change","target":"future.ts","format":"lean","options":{"capture_baseline":true,"capture_mode":"minimal","new_files":["future.ts"]}}),json!({})).unwrap();
    assert_eq!(capture["facts"]["baseline"]["existing_files_captured"], 0);
    assert_eq!(capture["facts"]["baseline"]["new_files_admitted"], 1);
    assert!(s.prepare(&g,&c,&json!({"intent":"review_change","target":"legacy.ts","options":{"capture_baseline":true,"capture_mode":"minimal"}}),json!({})).is_ok());
}

fn inventory(page: &Value, lean: bool) -> Vec<Value> {
    let mut sites = if lean {
        page["records"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|r| {
                r["sites"].as_array().unwrap().iter().map(|s| {
                    json!([
                        r["source"],
                        r["target"],
                        r["relation"],
                        r["file"],
                        s[0],
                        s[1],
                        r["confidence"],
                        r["phase"]
                    ])
                })
            })
            .collect::<Vec<_>>()
    } else {
        page["evidence"]["rows"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| {
                json!([
                    page["symbols"]["rows"][r[1].as_u64().unwrap() as usize][0],
                    page["symbols"]["rows"][r[2].as_u64().unwrap() as usize][0],
                    r[3],
                    page["files"][r[4].as_u64().unwrap() as usize]["file"],
                    r[5],
                    r[6],
                    r[7],
                    r[10]
                ])
            })
            .collect()
    };
    sites.sort_by_key(Value::to_string);
    sites
}

#[test]
fn lean_preserves_sites_and_limits_and_is_self_contained() {
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    let text =
        "function caller() {\r\n  target(1); target(2);\r\n}\r\nfunction target(x: number) {}\r\n";
    fs::write(d.path().join("sample.ts"), text).unwrap();
    let g = graph(text, "before");
    let mut s = State::default();
    let audit = s
        .prepare(
            &g,
            &c,
            &json!({"target":"target","intent":"rename","view":"edit_context"}),
            json!({}),
        )
        .unwrap();
    let request =
        json!({"target":"target","intent":"rename","view":"edit_context","format":"lean"});
    let lean = s.prepare(&g, &c, &request, json!({})).unwrap();
    assert_eq!(inventory(&audit, false), inventory(&lean, true));
    for limit in audit["limits"].as_array().unwrap() {
        assert!(lean["limits"].as_array().unwrap().contains(limit));
    }
    assert!(lean.to_string().len() < audit.to_string().len());
    assert!(lean.get("context").is_none());
    assert!(!lean.to_string().contains("window_id"));
    assert_eq!(lean["sources"][0]["source_hash"], hash(text));
    assert_eq!(
        lean["sources"][0]["windows"][0]["text"],
        audit["files"][0]["snippets"][0]["text"]
    );
    assert_eq!(
        lean["completion"]["required_inventory"]["state"],
        "complete"
    );
    assert_eq!(lean["completion"]["verification"]["compiler"], "not_run");
    assert_eq!(
        s.prepare(&g, &c, &request, json!({})).unwrap()["sources"],
        lean["sources"]
    );
    let mut acknowledged = request;
    acknowledged["context"] = json!({});
    assert!(s.prepare(&g, &c, &acknowledged, json!({})).is_err());
}

#[test]
fn optional_tests_and_compatibility_do_not_make_signature_inventory_incomplete() {
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    let text = "function caller() {\n  target(1);\n}\nfunction target(x: number) {}\n";
    fs::write(d.path().join("sample.ts"), text).unwrap();
    let mut snapshot = (*graph(text, "before").snapshot).clone();
    let caller = snapshot.files["sample.ts"].nodes[1].clone();
    let mut outer = caller.clone();
    outer.id = "sample.ts::outer#function".into();
    outer.name = "outer".into();
    let file = snapshot.files.get_mut("sample.ts").unwrap();
    file.nodes.push(outer.clone());
    let mut e = file.edges[0].clone();
    e.source = outer.id;
    e.target = caller.id;
    file.edges.push(e);
    let g = Graph::new(snapshot);
    let mut s = State::default();
    let lean = s.prepare(&g,&c,&json!({"target":"target","intent":"change_signature","format":"lean","depth":1,"options":{"return_type":"number","include_tests":true}}),json!({})).unwrap();
    assert_eq!(
        lean["completion"]["required_inventory"]["state"],
        "complete"
    );
    assert_eq!(lean["completion"]["next_required_action"], "edit");
    assert_eq!(lean["completion"]["optional_context"], "limited");
    assert!(
        lean["facts"]["compatibility"]
            .as_str()
            .unwrap()
            .contains("conditional")
    );
    let incomplete = s.prepare(&g,&c,&json!({"target":"target","intent":"change_signature","format":"lean","budget":{"max_items":1}}),json!({})).unwrap();
    assert_eq!(
        incomplete["completion"]["required_inventory"]["state"],
        "incomplete"
    );
    assert_eq!(
        incomplete["completion"]["next_required_action"],
        "retrieve_required"
    );
    let mut snapshot = (*g.snapshot).clone();
    snapshot.files.get_mut("sample.ts").unwrap().diagnostics.push(json!({"code":"provider_failed","severity":"error","line":1,"message":"failed semantic analysis"}));
    let failed = s
        .prepare(
            &Graph::new(snapshot),
            &c,
            &json!({"target":"target","intent":"rename","format":"lean"}),
            json!({}),
        )
        .unwrap();
    assert_eq!(
        failed["completion"]["required_inventory"]["provider_incomplete"],
        true
    );
    assert_eq!(failed["completion"]["next_required_action"], "report_limit");
    assert_eq!(failed["diagnostics"]["counts"]["error"], 1);
}

#[test]
fn review_semantic_destination_and_confidence_changes_are_never_erased() {
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    let text = "function caller() {\n  target(1);\n}\n";
    fs::write(d.path().join("sample.ts"), text).unwrap();
    for confidence_change in [false, true] {
        let before = graph(text, "before");
        let mut s = State::default();
        let capture = s.prepare(&before, &c, &json!({"target":"sample.ts","intent":"review_change","options":{"capture_baseline":true,"capture_mode":"minimal"}}), json!({})).unwrap();
        let mut snapshot = (*before.snapshot).clone();
        let edge = &mut snapshot.files.get_mut("sample.ts").unwrap().edges[0];
        if confidence_change {
            edge.confidence = "candidate".into();
        } else {
            edge.target = "sample.ts::other#function".into();
        }
        snapshot.generation = "after".into();
        let page = s.prepare(&Graph::new(snapshot), &c, &json!({"target":"sample.ts","intent":"review_change","view":"locations","options":{"baseline":capture["facts"]["baseline"]["handle"]}}), json!({})).unwrap();
        assert_eq!(page["sections"]["removed_relations"]["total"], 1);
        assert_eq!(page["sections"]["added_relations"]["total"], 1);
    }
}

#[test]
fn review_full_evidence_retains_before_and_after_positions() {
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    let text = "begin\n  target(1); target(2);\nend\n";
    fs::write(d.path().join("sample.ts"), text).unwrap();
    let mut s = State::default();
    let capture = s.prepare(&graph(text, "before"), &c, &json!({"intent":"review_change","target":"sample.ts","format":"lean","options":{"capture_baseline":true,"capture_mode":"minimal"}}), json!({})).unwrap();
    assert_eq!(capture["completion"]["next_required_action"], "edit");
    let after = format!("// unicode 🦀\n{text}");
    fs::write(d.path().join("sample.ts"), &after).unwrap();
    let mut current = (*graph(&after, "after").snapshot).clone();
    for node in &mut current.files.get_mut("sample.ts").unwrap().nodes {
        if node.kind != "file" {
            node.line += 1;
        }
    }
    let page = s.prepare(&Graph::new(current), &c, &json!({"intent":"review_change","target":"sample.ts","format":"lean","view":"full_evidence","options":{"baseline":capture["facts"]["baseline"]["handle"]}}), json!({})).unwrap();
    let details = page["details"].as_object().unwrap();
    let relocated: Vec<_> = details
        .values()
        .filter(|v| v["classification"] == "relocated")
        .collect();
    assert_eq!(relocated.len(), 2);
    for detail in relocated {
        assert_eq!(detail["before"]["line"], 2);
        assert_eq!(detail["after"]["line"], 3);
        assert!(
            detail["after"]["offset"].as_u64().unwrap()
                > detail["before"]["offset"].as_u64().unwrap()
        );
    }
    assert!(
        page["records"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|r| r["sections"]
                .as_array()
                .unwrap()
                .iter()
                .any(|v| v == "relocated_relations"))
            .all(|r| r["required"] == false)
    );
}

#[test]
fn same_id_signature_change_and_exhausted_diff_remain_visible() {
    let page = review(
        "function target(x: number) {}\n",
        "function target(x: string) {}\n",
    );
    assert_eq!(page["sections"]["source_changes"]["total"], 1);
    assert!(page["sections"]["file_context"]["total"].as_u64().unwrap() > 0);
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    let text = "begin\n  target(1);\nend\n";
    fs::write(d.path().join("sample.ts"), text).unwrap();
    let mut s = State::default();
    let capture = s.prepare(&graph(text, "before"), &c, &json!({"intent":"review_change","target":"sample.ts","format":"lean","options":{"capture_baseline":true,"capture_mode":"minimal"}}), json!({})).unwrap();
    let after = format!("// prefix\n{text}");
    fs::write(d.path().join("sample.ts"), &after).unwrap();
    let page = s.prepare(&graph(&after, "after"), &c, &json!({"intent":"review_change","target":"sample.ts","format":"lean","options":{"baseline":capture["facts"]["baseline"]["handle"]},"budget":{"max_traversal":1}}), json!({})).unwrap();
    assert_eq!(
        page["completion"]["required_inventory"]["state"],
        "incomplete"
    );
    assert!(page["limits"].to_string().contains("budget"));
}

#[test]
fn strict_capture_lists_ambiguous_candidates_without_guessing() {
    let d = tempfile::tempdir().unwrap();
    let c = Config::load(d.path(), None).unwrap();
    let mut snapshot = Snapshot::default();
    for path in ["one/sample.ts", "two/sample.ts"] {
        fs::create_dir_all(d.path().join(path).parent().unwrap()).unwrap();
        fs::write(d.path().join(path), "").unwrap();
        snapshot.files.insert(
            path.into(),
            FileRecord {
                file: path.into(),
                hash: hash(""),
                nodes: vec![],
                edges: vec![],
                dependencies: vec![],
                diagnostics: vec![],
                unresolved_calls: 0,
                intent: Default::default(),
            },
        );
    }
    let mut s = State::default();
    let error = s.prepare(&Graph::new(snapshot), &c, &json!({"intent":"review_change","target":"sample.ts","format":"lean","options":{"capture_baseline":true}}), json!({})).unwrap_err().to_string();
    assert!(
        error.contains("one/sample.ts") && error.contains("two/sample.ts"),
        "{error}"
    );
    assert!(s.prepare(&graph("", "g"), &c, &json!({"intent":"review_change","target":"future.ts","format":"lean","options":{"capture_baseline":true,"new_files":["future.ts","future.ts"]}}), json!({})).is_err());
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(d.path().join("one/sample.ts"), d.path().join("link.ts"))
            .unwrap();
        let error = s.prepare(&graph("", "g"), &c, &json!({"intent":"review_change","target":"link.ts","format":"lean","options":{"capture_baseline":true,"new_files":["link.ts"]}}), json!({})).unwrap_err().to_string();
        assert!(
            error.contains("Symlink") || error.contains("symlink"),
            "{error}"
        );
    }
}
