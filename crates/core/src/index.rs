use crate::{
    config::Config,
    filesystem::{self, IGNORED, Scan},
    model::{Snapshot, hash, language},
    providers,
    query::Graph,
    store::Store,
};
use anyhow::{Result, bail};
use fs2::FileExt;
use notify::{Event, RecommendedWatcher, RecursiveMode, Watcher};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicUsize, Ordering},
        mpsc::{Receiver, TryRecvError, sync_channel},
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
#[derive(Default, Debug)]
pub struct Metrics {
    pub scans: u64,
    pub extractions: u64,
    pub graph_builds: u64,
    pub scan_ms: f64,
    pub extraction_ms: f64,
    pub storage_ms: f64,
    pub query_ms: f64,
}
struct Changes {
    receiver: Receiver<notify::Result<Event>>,
    overflow: Arc<AtomicBool>,
    pending: Arc<AtomicUsize>,
    _watcher: RecommendedWatcher,
}
pub struct Indexer {
    pub config: Config,
    pub store: Store,
    pub graph: Option<Graph>,
    watcher: Option<Changes>,
    pub metrics: Metrics,
    last_scan: Instant,
    last_reconciled: Option<u64>,
    pub watcher_error: Option<String>,
    config_disk_hash: String,
    directory_stamps: BTreeMap<String, SystemTime>,
}
fn watch(c: &Config) -> Result<Changes> {
    let (tx, receiver) = sync_channel(4096);
    let overflow = Arc::new(AtomicBool::new(false));
    let full = overflow.clone();
    let pending = Arc::new(AtomicUsize::new(0));
    let count = pending.clone();
    let config = c.clone();
    let mut w = notify::recommended_watcher(move |event: notify::Result<Event>| {
        if let Ok(e) = &event {
            if matches!(e.kind, notify::EventKind::Access(_)) {
                return;
            }
            if !e.need_rescan() && !e.paths.iter().any(|p| relevant(&config, p)) {
                return;
            }
        }
        count.fetch_add(1, Ordering::Release);
        if tx.try_send(event).is_err() {
            count.fetch_sub(1, Ordering::AcqRel);
            full.store(true, Ordering::Release);
        }
    })?;
    w.watch(&c.root, RecursiveMode::Recursive)?;
    Ok(Changes {
        receiver,
        overflow,
        pending,
        _watcher: w,
    })
}
fn relevant(c: &Config, p: &std::path::Path) -> bool {
    if !p.starts_with(&c.root) {
        return false;
    }
    let rel = filesystem::relative(&c.root, p);
    if p.starts_with(c.root.join(&c.cache)) {
        return false;
    }
    for part in std::path::Path::new(&rel).components() {
        let s = part.as_os_str().to_string_lossy();
        if IGNORED.contains(&s.as_ref()) {
            return s == ".dart_tool" && rel.ends_with("package_config.json");
        }
    }
    true
}

impl Indexer {
    pub fn new(config: Config) -> Result<Self> {
        // Create excluded cache storage before watching; discovery/reads follow watcher startup.
        let store = Store::new(&config)?;
        let watcher = if config.watch {
            watch(&config)
        } else {
            Err(anyhow::anyhow!("disabled"))
        };
        let (watcher, watcher_error) = match watcher {
            Ok(w) => (Some(w), None),
            Err(e) => (None, config.watch.then(|| e.to_string())),
        };
        let mut metrics = Metrics::default();
        let old = match store.read() {
            Ok(v) => v,
            Err(e) => {
                eprintln!("cache rebuild: {e}");
                store.recover()?;
                None
            }
        };
        let graph = old
            .filter(|s| {
                s.root == config.root.to_string_lossy()
                    && s.fingerprint == config.fingerprint().unwrap_or_default()
            })
            .map(|s| {
                metrics.graph_builds += 1;
                Graph::new(s)
            });
        let config_disk_hash = config.disk_fingerprint()?;
        Ok(Self {
            config,
            store,
            graph,
            watcher,
            metrics,
            last_scan: Instant::now() - Duration::from_secs(86400),
            last_reconciled: None,
            watcher_error,
            config_disk_hash,
            directory_stamps: BTreeMap::new(),
        })
    }
    fn drain(&mut self) -> (BTreeSet<String>, bool) {
        let mut paths = BTreeSet::new();
        let mut full = false;
        if let Some(w) = &self.watcher {
            full = w.overflow.swap(false, Ordering::AcqRel);
            loop {
                match w.receiver.try_recv() {
                    Ok(Ok(e)) => {
                        w.pending.fetch_sub(1, Ordering::AcqRel);
                        if matches!(e.kind, notify::EventKind::Access(_)) {
                            continue;
                        }
                        if e.need_rescan() {
                            full = true
                        }
                        for p in e.paths {
                            if relevant(&self.config, &p) {
                                paths.insert(filesystem::relative(&self.config.root, &p));
                            }
                        }
                    }
                    Ok(Err(e)) => {
                        w.pending.fetch_sub(1, Ordering::AcqRel);
                        full = true;
                        self.watcher_error = Some(e.to_string());
                    }
                    Err(TryRecvError::Empty) => break,
                    Err(TryRecvError::Disconnected) => {
                        self.watcher_error = Some("watcher channel disconnected".into());
                        full = true;
                        break;
                    }
                }
            }
        }
        (paths, full)
    }
    pub fn freshness(&self) -> Value {
        json!({"mode":if self.watcher.is_some() && self.watcher_error.is_none(){"watcher"}else{"full_scan"},"watcher_healthy":self.watcher.is_some()&&self.watcher_error.is_none(),"watcher_error":self.watcher_error,"last_reconciled":self.last_reconciled,"pending_updates":self.watcher.as_ref().map_or(0, |w|w.pending.load(Ordering::Acquire) + usize::from(w.overflow.load(Ordering::Acquire)))})
    }
    fn scan(&mut self) -> Result<Scan> {
        let t = Instant::now();
        let mut scan = filesystem::scan(&self.config)?;
        scan.environment.insert(
            "provider_runtime".into(),
            providers::fingerprint(&self.config)?,
        );
        self.metrics.scans += 1;
        self.metrics.scan_ms += t.elapsed().as_secs_f64() * 1000.;
        Ok(scan)
    }
    pub fn detect_changes(&mut self) -> Result<Value> {
        let scan = self.scan()?;
        let saved = self.store.read()?;
        let old = saved.as_ref();
        let mut changed: Vec<_> = scan
            .hashes
            .iter()
            .filter(|(f, h)| {
                old.and_then(|o| o.files.get(*f))
                    .is_none_or(|r| &r.hash != *h)
            })
            .map(|(f, _)| f.clone())
            .collect();
        let mut deleted: Vec<_> = old
            .into_iter()
            .flat_map(|o| o.files.keys())
            .filter(|f| !scan.hashes.contains_key(*f))
            .cloned()
            .collect();
        changed.sort_by(|a, b| crate::model::compare_text(a, b));
        deleted.sort_by(|a, b| crate::model::compare_text(a, b));
        Ok(
            json!({"indexed":old.is_some(),"changed":changed,"deleted":deleted,"skipped":scan.skipped,"environment_changed":old.is_none_or(|o|o.environment!=hash(serde_json::to_vec(&scan.environment).unwrap_or_default()))}),
        )
    }
    pub async fn refresh(&mut self, explicit: bool, force: bool) -> Result<Value> {
        let (mut dirty, mut full) = self.drain();
        if !dirty.is_empty() {
            tokio::time::sleep(Duration::from_millis(self.config.watch_debounce_ms)).await;
            let (d, f) = self.drain();
            dirty.extend(d);
            full |= f;
        }
        let reconcile = explicit
            || force
            || full
            || self.watcher.is_none()
            || self.watcher_error.is_some()
            || self.graph.is_none()
            || self.last_scan.elapsed()
                >= Duration::from_secs(self.config.reconcile_interval_seconds);
        if !reconcile && dirty.is_empty() {
            return Ok(self.report(vec![], vec![], vec![], false));
        }
        let disk_hash = self.config.disk_fingerprint()?;
        if disk_hash != self.config_disk_hash {
            let updated = Config::load(&self.config.root, self.config.config_file.as_deref())?;
            self.store = Store::new(&updated)?;
            self.watcher = if updated.watch {
                match watch(&updated) {
                    Ok(w) => {
                        self.watcher_error = None;
                        Some(w)
                    }
                    Err(e) => {
                        self.watcher_error = Some(e.to_string());
                        None
                    }
                }
            } else {
                self.watcher_error = None;
                None
            };
            self.config = updated;
            self.config_disk_hash = disk_hash;
            full = true;
        }
        let lock_path = self
            .config
            .safe(&format!("{}/writer.lock", self.config.cache))?;
        let lock = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(lock_path)?;
        loop {
            match lock.try_lock_exclusive() {
                Ok(()) => break,
                Err(e)
                    if e.kind() == std::io::ErrorKind::WouldBlock
                        || e.raw_os_error() == fs2::lock_contended_error().raw_os_error() =>
                {
                    tokio::time::sleep(Duration::from_millis(10)).await
                }
                Err(e) => return Err(e.into()),
            }
        }
        let result = self.update(reconcile || full, force, dirty).await;
        let _ = FileExt::unlock(&lock);
        result
    }
    async fn update(
        &mut self,
        reconcile: bool,
        force: bool,
        mut dirty: BTreeSet<String>,
    ) -> Result<Value> {
        // Reload another process's committed generation only under the writer lock.
        let (saved, force) = match self.store.read() {
            Ok(saved) => (saved, force),
            Err(e) => {
                eprintln!("cache rebuild: {e:#}");
                self.store.recover()?;
                (None, true)
            }
        };
        if let Some(s) = saved
            && self
                .graph
                .as_ref()
                .is_none_or(|g| g.snapshot.generation != s.generation)
            && s.root == self.config.root.to_string_lossy()
            && s.fingerprint == self.config.fingerprint()?
        {
            self.graph = Some(Graph::new(s));
            self.metrics.graph_builds += 1;
        }
        for attempt in 0..3 {
            let old = self.graph.as_ref().map(|g| (*g.snapshot).clone());
            let mut scan = if reconcile || attempt > 0 || old.is_none() {
                self.scan()?
            } else {
                let o = old
                    .as_ref()
                    .ok_or_else(|| anyhow::anyhow!("missing snapshot"))?;
                let mut s = Scan {
                    hashes: o
                        .files
                        .iter()
                        .map(|(f, r)| (f.clone(), r.hash.clone()))
                        .collect(),
                    environment: BTreeMap::new(),
                    skipped: o.skipped.clone(),
                    scopes: o.scopes.clone(),
                    directory_stamps: self.directory_stamps.clone(),
                };
                for f in &dirty {
                    // FSEvents may deliver pre-scan directory notifications later.
                    // Directory timestamps only suppress duplicate hints; source freshness uses hashes.
                    let directory = if f.is_empty() {
                        self.config.root.clone()
                    } else {
                        self.config.root.join(f)
                    };
                    if self.directory_stamps.get(f).is_some_and(|stamp| {
                        fs::symlink_metadata(&directory)
                            .is_ok_and(|m| m.is_dir() && m.modified().ok().as_ref() == Some(stamp))
                    }) {
                        continue;
                    }
                    let path = match self.config.safe(f) {
                        Ok(path) => path,
                        Err(_) => {
                            s = self.scan()?;
                            break;
                        }
                    };
                    if path.is_dir()
                        || fs::symlink_metadata(&path).is_ok_and(|m| m.file_type().is_symlink())
                        || o.files.keys().any(|old| old.starts_with(&format!("{f}/")))
                        || filesystem::manifest(
                            path.file_name().and_then(|n| n.to_str()).unwrap_or(""),
                        )
                        || f.ends_with("package_config.json")
                    {
                        s = self.scan()?;
                        break;
                    }
                    if language(f) == "unknown" {
                        continue;
                    }
                    if path.is_file() {
                        let bytes = fs::read(&path)?;
                        let (inc, exc) = self.config.globs()?;
                        if bytes.len() <= self.config.max_file_bytes
                            && inc.is_match(f)
                            && !exc.is_match(f)
                        {
                            s.hashes.insert(f.clone(), hash(bytes));
                            s.scopes
                                .insert(f.clone(), filesystem::scope(&self.config, f));
                        } else {
                            s = self.scan()?;
                            break;
                        }
                    } else {
                        s.hashes.remove(f);
                        s.scopes.remove(f);
                    }
                }
                s
            };
            let environment = if scan.environment.is_empty() {
                old.as_ref()
                    .map(|o| o.environment.clone())
                    .unwrap_or_default()
            } else {
                hash(serde_json::to_vec(&scan.environment)?)
            };
            let changed: Vec<_> = scan
                .hashes
                .iter()
                .filter(|(f, h)| {
                    old.as_ref()
                        .and_then(|o| o.files.get(*f))
                        .is_none_or(|r| &r.hash != *h)
                })
                .map(|(f, _)| f.clone())
                .collect();
            let deleted: Vec<_> = old
                .as_ref()
                .into_iter()
                .flat_map(|o| o.files.keys())
                .filter(|f| !scan.hashes.contains_key(*f))
                .cloned()
                .collect();
            let inputs = if scan.environment.is_empty() {
                old.as_ref()
                    .map(|o| o.environment_inputs.clone())
                    .unwrap_or_default()
            } else {
                scan.environment.clone()
            };
            let mut env_languages = BTreeSet::new();
            if let Some(o) = &old {
                for key in o.environment_inputs.keys().chain(inputs.keys()) {
                    if o.environment_inputs.get(key) != inputs.get(key) {
                        env_languages.extend(filesystem::environment_languages(key));
                    }
                }
                if o.environment_inputs.is_empty() && o.environment != environment {
                    env_languages.insert("all");
                }
            }
            let is_full = force
                || old.is_none()
                || old.as_ref().is_some_and(|o| {
                    o.environment != environment
                        || o.fingerprint != self.config.fingerprint().unwrap_or_default()
                });
            let rebuild_all = force
                || old.is_none()
                || env_languages.contains("all")
                || old.as_ref().is_some_and(|o| {
                    o.fingerprint != self.config.fingerprint().unwrap_or_default()
                });
            let mut affected: BTreeSet<_> = if rebuild_all {
                scan.hashes.keys().cloned().collect()
            } else {
                changed.iter().chain(&deleted).cloned().collect()
            };
            affected.extend(
                scan.hashes
                    .keys()
                    .filter(|f| env_languages.contains(language(f)))
                    .cloned(),
            );
            if let Some(o) = &old {
                loop {
                    let before = affected.len();
                    let touched: BTreeSet<_> = affected
                        .iter()
                        .filter_map(|f| scan.scopes.get(f).or(o.scopes.get(f)))
                        .cloned()
                        .collect();
                    for (f, r) in &o.files {
                        if r.dependencies.iter().any(|d| affected.contains(d))
                            || scan.scopes.get(f).is_some_and(|s| touched.contains(s))
                        {
                            affected.insert(f.clone());
                        }
                    }
                    for (f, s) in &scan.scopes {
                        if touched.contains(s) {
                            affected.insert(f.clone());
                        }
                    }
                    if affected.iter().any(|f| language(f) == "objectivec") {
                        affected.extend(
                            scan.hashes
                                .keys()
                                .filter(|f| language(f) == "swift")
                                .cloned(),
                        );
                    }
                    if affected.len() == before {
                        break;
                    }
                }
            }
            affected.retain(|f| scan.hashes.contains_key(f));
            if affected.is_empty()
                && deleted.is_empty()
                && !is_full
                && old.as_ref().is_some_and(|o| o.skipped == scan.skipped)
            {
                self.directory_stamps = scan.directory_stamps;
                if reconcile {
                    self.last_scan = Instant::now();
                    self.last_reconciled =
                        Some(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs());
                }
                return Ok(self.report(changed, deleted, vec![], false));
            }
            let t = Instant::now();
            let extracted = providers::extract(&self.config, &scan.hashes, &affected).await?;
            self.metrics.extractions += extracted.len() as u64;
            self.metrics.extraction_ms += t.elapsed().as_secs_f64() * 1000.;
            let (mut events, overflow) = self.drain();
            let mut unstable = overflow || !events.is_empty();
            for (f, h) in &scan.hashes {
                if affected.iter().any(|a| {
                    language(a) == language(f)
                        || (["typescript", "javascript"].contains(&language(a))
                            && ["typescript", "javascript"].contains(&language(f)))
                }) && fs::read(self.config.safe(f)?).map(hash).ok().as_ref() != Some(h)
                {
                    unstable = true;
                    events.insert(f.clone());
                }
            }
            // Reconciliation also catches changes outside the emitted scope during extraction.
            if reconcile {
                let after = self.scan()?;
                if after.hashes != scan.hashes || after.environment != scan.environment {
                    unstable = true;
                }
                scan.directory_stamps = after.directory_stamps;
            }
            if !reconcile {
                let languages = affected.iter().map(|f| language(f)).collect();
                if !filesystem::context_unchanged(&self.config, &inputs, &languages)? {
                    unstable = true;
                }
            }
            if unstable {
                dirty.extend(events);
                continue;
            }
            if old.is_some()
                && extracted.values().any(|r| {
                    r.diagnostics
                        .iter()
                        .any(|d| d["code"] == "provider_unavailable")
                })
            {
                bail!("Provider failed during update; previous committed generation retained")
            }
            let mut files = old.map(|o| o.files).unwrap_or_default();
            for f in &deleted {
                files.remove(f);
            }
            files.extend(extracted);
            let skipped = std::mem::take(&mut scan.skipped);
            let generation=hash(serde_json::to_vec(&json!({"files":scan.hashes,"environment":environment,"config":self.config.fingerprint()?,"skipped":skipped}))?)[..20].to_string();
            let snapshot = Snapshot {
                root: self.config.root.to_string_lossy().into(),
                fingerprint: self.config.fingerprint()?,
                environment,
                environment_inputs: inputs,
                generation,
                files,
                skipped,
                scopes: scan.scopes,
            };
            let t = Instant::now();
            self.store.write_changed(&snapshot, &affected)?;
            self.metrics.storage_ms += t.elapsed().as_secs_f64() * 1000.;
            self.directory_stamps = scan.directory_stamps;
            self.graph = Some(Graph::new(snapshot));
            self.metrics.graph_builds += 1;
            if reconcile {
                self.last_scan = Instant::now();
                self.last_reconciled =
                    Some(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs());
            }
            return Ok(self.report(changed, deleted, affected.into_iter().collect(), is_full));
        }
        bail!("Repository changed repeatedly during indexing; retry when writes finish")
    }
    fn report(
        &self,
        mut changed: Vec<String>,
        mut deleted: Vec<String>,
        mut reindexed: Vec<String>,
        full: bool,
    ) -> Value {
        for rows in [&mut changed, &mut deleted, &mut reindexed] {
            rows.sort_by(|a, b| crate::model::compare_text(a, b));
        }
        let g = self.graph.as_ref();
        json!({"generation":g.map(|g|&g.snapshot.generation),"changed_total":changed.len(),"deleted_total":deleted.len(),"reindexed_total":reindexed.len(),"changed":changed,"deleted":deleted,"reindexed":reindexed,"full":full,"files":g.map_or(0,|g|g.snapshot.files.len()),"skipped":g.map_or(vec![],|g|g.snapshot.skipped.clone()),"skipped_total":g.map_or(0,|g|g.snapshot.skipped.len())})
    }
    pub async fn call(&mut self, name: &str, args: &Value) -> Result<Value> {
        if name == "detect_changes" {
            let mut v = self.detect_changes()?;
            cap(&mut v, &self.config);
            return Ok(v);
        }
        let mut report = self
            .refresh(name == "index_repository", args["force"] == true)
            .await?;
        cap(&mut report, &self.config);
        if name == "index_repository" {
            return Ok(report);
        }
        let graph = self
            .graph
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("No index"))?;
        if name == "status" {
            let mut v = graph.architecture(&self.config, 5);
            v["index"] = report;
            v["provider_health"] = providers::doctor(&self.config);
            v["freshness"] = self.freshness();
            v["metrics"] = json!({"scans":self.metrics.scans,"extractions":self.metrics.extractions,"graph_builds":self.metrics.graph_builds,"scan_ms":self.metrics.scan_ms,"extraction_ms":self.metrics.extraction_ms,"storage_ms":self.metrics.storage_ms,"query_ms":self.metrics.query_ms});
            return Ok(v);
        }
        let t = Instant::now();
        let r = graph.call(&self.config, name, args);
        self.metrics.query_ms += t.elapsed().as_secs_f64() * 1000.;
        r
    }
}
fn cap(v: &mut Value, c: &Config) {
    for key in ["changed", "deleted", "reindexed", "skipped"] {
        if let Some(a) = v[key].as_array() {
            let n = a.len();
            let page: Vec<_> = a.iter().take(c.max_results).cloned().collect();
            v[format!("{key}_total")] = json!(n);
            v[key] = json!(page);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn duplicate_directory_notifications_reuse_index() {
        let d = tempfile::tempdir().unwrap();
        let mut c = Config::load(d.path(), None).unwrap();
        fs::create_dir_all(d.path().join("assets")).unwrap();
        c.providers_path = Some(d.path().join("assets").to_string_lossy().into());
        let mut i = Indexer::new(c).unwrap();
        i.refresh(true, false).await.unwrap();
        let scans = i.metrics.scans;
        i.update(false, false, BTreeSet::from(["".into(), "assets".into()]))
            .await
            .unwrap();
        assert_eq!(i.metrics.scans, scans);
        fs::create_dir_all(d.path().join("assets/new-directory")).unwrap();
        i.update(false, false, BTreeSet::from(["assets".into()]))
            .await
            .unwrap();
        assert!(
            i.metrics.scans > scans,
            "actual directory changes must be reconciled"
        );
    }
    #[tokio::test]
    async fn overflow_forces_reconciliation() {
        let d = tempfile::tempdir().unwrap();
        let mut c = Config::load(d.path(), None).unwrap();
        let assets = d.path().join("assets");
        fs::create_dir_all(&assets).unwrap();
        c.providers_path = Some(assets.to_string_lossy().into());
        let mut i = Indexer::new(c).unwrap();
        i.refresh(true, false).await.unwrap();
        let before = i.metrics.scans;
        i.watcher
            .as_ref()
            .unwrap()
            .overflow
            .store(true, Ordering::Release);
        i.refresh(false, false).await.unwrap();
        assert!(i.metrics.scans > before);
    }
    #[tokio::test]
    async fn periodic_reconciliation_recovers_missed_events() {
        let d = tempfile::tempdir().unwrap();
        let mut c = Config::load(d.path(), None).unwrap();
        let assets = d.path().join("assets");
        fs::create_dir_all(&assets).unwrap();
        c.providers_path = Some(assets.to_string_lossy().into());
        let mut i = Indexer::new(c).unwrap();
        i.refresh(true, false).await.unwrap();
        i.last_scan = Instant::now() - Duration::from_secs(31);
        let before = i.metrics.scans;
        i.refresh(false, false).await.unwrap();
        assert!(i.metrics.scans > before);
    }
}
