use anyhow::Result;
use polycodegraph_core::{
    config::Config,
    model::{Edge, FileRecord, Node, Snapshot, hash},
    query::Graph,
    store::Store,
};
use serde_json::json;
use std::{
    collections::BTreeMap,
    fs,
    time::{Duration, Instant},
};
fn main() -> Result<()> {
    let root = std::env::args()
        .nth(1)
        .ok_or_else(|| anyhow::anyhow!("benchmark root required"))?;
    let c = Config::load(std::path::Path::new(&root), None)?;
    let source = fs::read(c.root.join("bench.dart"))?;
    let nodes: Vec<_> = (0..100000)
        .map(|i| Node {
            id: format!("bench.dart::f{i}#function"),
            name: format!("f{i}"),
            qualified: format!("f{i}"),
            kind: "function".into(),
            file: "bench.dart".into(),
            line: 1,
            end: 1,
            offset: 0,
            length: 1,
            parent: None,
            tags: vec![],
            synthetic: false,
        })
        .collect();
    let edges: Vec<_> = (0..500000)
        .map(|i| Edge {
            source: nodes[i % 100000].id.clone(),
            target: nodes[(i + 1) % 100000].id.clone(),
            kind: "calls".into(),
            file: "bench.dart".into(),
            line: 1,
            offset: i,
            confidence: "resolved".into(),
        })
        .collect();
    let s = Snapshot {
        generation: "benchmark".into(),
        root: c.root.to_string_lossy().into(),
        files: BTreeMap::from([(
            "bench.dart".into(),
            FileRecord {
                file: "bench.dart".into(),
                hash: hash(&source),
                nodes,
                edges,
                dependencies: vec![],
                diagnostics: vec![],
                unresolved_calls: 0,
                intent: Default::default(),
            },
        )]),
        ..Default::default()
    };
    if std::env::args().any(|a| a == "--storage") {
        let store = Store::new(&c)?;
        let t = Instant::now();
        store.write(&s)?;
        let write_ms = t.elapsed().as_secs_f64() * 1000.;
        let t = Instant::now();
        let loaded = store.read()?.expect("stored snapshot");
        let read_ms = t.elapsed().as_secs_f64() * 1000.;
        std::hint::black_box(loaded);
        println!(
            "{}",
            json!({"engine":"rust-sqlite","symbols":100000,"edges":500000,"write_ms":write_ms,"read_ms":read_ms,"bytes":store.path.metadata()?.len(),"workload":"separate cold persistence; no providers or queries"})
        );
        return Ok(());
    }
    let build = Instant::now();
    let g = Graph::new(s);
    let build_ms = build.elapsed().as_secs_f64() * 1000.;
    let args = json!({"target":"bench.dart::f50#function","limit":20});
    let start = Instant::now();
    let mut reconciled = Instant::now() - Duration::from_secs(31);
    let mut samples = vec![];
    let mut scans = 0;
    while start.elapsed() < Duration::from_secs(31) {
        let t = Instant::now();
        if reconciled.elapsed() >= Duration::from_secs(30) {
            std::hint::black_box(hash(fs::read(c.root.join("bench.dart"))?));
            reconciled = Instant::now();
            scans += 1;
        }
        std::hint::black_box(g.call(&c, "callers", &args)?);
        samples.push(t.elapsed().as_secs_f64() * 1000.);
        std::thread::sleep(Duration::from_millis(100));
    }
    samples.sort_by(f64::total_cmp);
    println!(
        "{}",
        json!({"engine":"rust","symbols":100000,"edges":500000,"build_ms":build_ms,"samples":samples.len(),"median_ms":samples[samples.len()/2],"p95_ms":samples[samples.len()*95/100],"mean_ms":samples.iter().sum::<f64>()/samples.len() as f64,"max_ms":samples.last(),"reconciliations":scans,"source_bytes":source.len(),"workload":"in-memory graph query including periodic SHA-256 reconciliation; excludes provider analysis and database startup"})
    );
    Ok(())
}
