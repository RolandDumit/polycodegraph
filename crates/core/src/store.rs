use crate::{config::Config, model::Snapshot};
use anyhow::{Context, Result};
use rusqlite::{Connection, params};
use std::{collections::BTreeMap, fs, path::PathBuf};
pub struct Store {
    pub path: PathBuf,
}
impl Store {
    pub fn new(c: &Config) -> Result<Self> {
        let dir = c.safe(&c.cache)?;
        fs::create_dir_all(&dir)?;
        let path = c.safe(&format!("{}/index.sqlite", c.cache))?;
        Ok(Self { path })
    }
    fn open(&self) -> Result<Connection> {
        for ending in ["", "-wal", "-shm"] {
            let path = PathBuf::from(format!("{}{ending}", self.path.display()));
            if fs::symlink_metadata(path).is_ok_and(|m| m.file_type().is_symlink()) {
                anyhow::bail!("symlink cache files are not allowed")
            }
        }
        let db = Connection::open(&self.path)?;
        db.busy_timeout(std::time::Duration::from_secs(120))?;
        db.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,hash TEXT NOT NULL,record TEXT NOT NULL); CREATE TABLE IF NOT EXISTS scopes(file TEXT PRIMARY KEY,scope TEXT NOT NULL); CREATE TABLE IF NOT EXISTS symbols(id TEXT PRIMARY KEY,file TEXT,name TEXT,qualified TEXT,kind TEXT,record TEXT); CREATE TABLE IF NOT EXISTS edges(key TEXT PRIMARY KEY,source TEXT,target TEXT,kind TEXT,file TEXT,record TEXT); CREATE INDEX IF NOT EXISTS edge_source ON edges(source,kind); CREATE INDEX IF NOT EXISTS edge_target ON edges(target,kind); CREATE INDEX IF NOT EXISTS edge_file ON edges(file); CREATE INDEX IF NOT EXISTS symbol_name ON symbols(name); CREATE INDEX IF NOT EXISTS symbol_file ON symbols(file); CREATE INDEX IF NOT EXISTS symbol_qualified ON symbols(qualified); CREATE TABLE IF NOT EXISTS dependencies(file TEXT,target TEXT,PRIMARY KEY(file,target)); CREATE INDEX IF NOT EXISTS dependency_target ON dependencies(target); CREATE TABLE IF NOT EXISTS diagnostics(file TEXT,ordinal INTEGER,record TEXT,PRIMARY KEY(file,ordinal));")?;
        Ok(db)
    }
    pub fn revision(&self) -> Result<Option<String>> {
        if !self.path.exists() {
            return Ok(None);
        }
        let db = self.open()?;
        let schema: Option<String> = db
            .query_row("SELECT value FROM metadata WHERE key='schema'", [], |r| {
                r.get(0)
            })
            .optional()?;
        if schema.as_deref().is_some_and(|s| !["3", "4"].contains(&s)) {
            anyhow::bail!("incompatible cache schema");
        }
        Ok(db
            .query_row("SELECT value FROM metadata WHERE key='revision'", [], |r| {
                r.get(0)
            })
            .optional()?)
    }
    pub fn read(&self) -> Result<Option<Snapshot>> {
        Ok(self.read_versioned()?.0)
    }
    pub fn read_versioned(&self) -> Result<(Option<Snapshot>, Option<String>)> {
        if !self.path.exists() {
            return Ok((None, None));
        }
        let mut connection = self.open()?;
        let db = connection.transaction()?;
        let schema: Option<String> = db
            .query_row("SELECT value FROM metadata WHERE key='schema'", [], |r| {
                r.get(0)
            })
            .optional()?;
        if schema.as_deref().is_some_and(|s| !["3", "4"].contains(&s)) {
            anyhow::bail!("incompatible cache schema")
        }
        let meta: Option<String> = db
            .query_row("SELECT value FROM metadata WHERE key='snapshot'", [], |r| {
                r.get(0)
            })
            .optional()?;
        let Some(meta) = meta else {
            return Ok((None, None));
        };
        let mut s: Snapshot = serde_json::from_str(&meta)?;
        let mut st = db.prepare("SELECT path,record FROM files ORDER BY path")?;
        s.files = st
            .query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)))?
            .map(|v| {
                let (k, v) = v?;
                Ok((k, serde_json::from_str(&v)?))
            })
            .collect::<Result<BTreeMap<_, _>>>()?;
        let revision = db
            .query_row("SELECT value FROM metadata WHERE key='revision'", [], |r| {
                r.get(0)
            })
            .optional()?;
        Ok((Some(s), revision))
    }
    pub fn recover(&self) -> Result<()> {
        let suffix = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        for ending in ["", "-wal", "-shm"] {
            let p = PathBuf::from(format!("{}{ending}", self.path.display()));
            if p.exists() {
                fs::rename(
                    &p,
                    PathBuf::from(format!("{}.corrupt-{suffix}{ending}", self.path.display())),
                )?;
            }
        }
        Ok(())
    }
    pub fn write(&self, s: &Snapshot) -> Result<()> {
        self.write_changed(s, &s.files.keys().cloned().collect())
    }
    pub fn write_changed(
        &self,
        s: &Snapshot,
        changed: &std::collections::BTreeSet<String>,
    ) -> Result<()> {
        self.write_changed_revision(s, changed).map(|_| ())
    }
    pub fn write_changed_revision(
        &self,
        s: &Snapshot,
        changed: &std::collections::BTreeSet<String>,
    ) -> Result<String> {
        let mut db = self.open()?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let old: BTreeMap<String, String> = {
            let mut st = tx.prepare("SELECT path,hash FROM files")?;
            st.query_map([], |r| Ok((r.get(0)?, r.get(1)?)))?
                .collect::<rusqlite::Result<_>>()?
        };
        for (file, h) in &old {
            if s.files.get(file).is_none_or(|r| &r.hash != h) {
                for table in ["symbols", "edges", "dependencies", "diagnostics"] {
                    tx.execute(&format!("DELETE FROM {table} WHERE file=?1"), [file])?;
                }
                tx.execute("DELETE FROM files WHERE path=?1", [file])?;
            }
        }
        for (file, r) in &s.files {
            if !changed.contains(file) {
                continue;
            }
            // Reindexed records may change even when their source hash stays fixed.
            let serialized = serde_json::to_string(r)?;
            let same: Option<String> = tx
                .query_row("SELECT record FROM files WHERE path=?1", [file], |x| {
                    x.get(0)
                })
                .optional()?;
            if same.as_deref() == Some(serialized.as_str()) {
                continue;
            }
            for table in ["symbols", "edges", "dependencies", "diagnostics"] {
                tx.execute(&format!("DELETE FROM {table} WHERE file=?1"), [file])?;
            }
            tx.execute(
                "INSERT OR REPLACE INTO files VALUES(?1,?2,?3)",
                params![file, r.hash, serialized],
            )?;
            for n in &r.nodes {
                tx.prepare_cached("INSERT OR REPLACE INTO symbols VALUES(?1,?2,?3,?4,?5,?6)")?
                    .execute(params![
                        n.id,
                        n.file,
                        n.name,
                        n.qualified,
                        n.kind,
                        serde_json::to_string(n)?
                    ])?;
            }
            for e in &r.edges {
                tx.prepare_cached("INSERT OR REPLACE INTO edges VALUES(?1,?2,?3,?4,?5,?6)")?
                    .execute(params![
                        e.key(),
                        e.source,
                        e.target,
                        e.kind,
                        file,
                        serde_json::to_string(e)?
                    ])?;
            }
            for d in &r.dependencies {
                tx.prepare_cached("INSERT OR IGNORE INTO dependencies VALUES(?1,?2)")?
                    .execute(params![file, d])?;
            }
            for (i, d) in r.diagnostics.iter().enumerate() {
                tx.prepare_cached("INSERT INTO diagnostics VALUES(?1,?2,?3)")?
                    .execute(params![file, i as i64, serde_json::to_string(d)?])?;
            }
        }
        tx.execute("DELETE FROM symbols WHERE kind='external' AND NOT EXISTS (SELECT 1 FROM edges WHERE edges.source=symbols.id OR edges.target=symbols.id)",[])?;
        tx.execute("DELETE FROM scopes", [])?;
        for (f, scope) in &s.scopes {
            tx.execute("INSERT INTO scopes VALUES(?1,?2)", params![f, scope])?;
        }
        let meta = Snapshot {
            root: s.root.clone(),
            fingerprint: s.fingerprint.clone(),
            environment: s.environment.clone(),
            environment_inputs: s.environment_inputs.clone(),
            generation: s.generation.clone(),
            scopes: s.scopes.clone(),
            skipped: s.skipped.clone(),
            files: BTreeMap::new(),
        };
        tx.execute(
            "INSERT OR REPLACE INTO metadata VALUES('snapshot',?1)",
            [serde_json::to_string(&meta)?],
        )?;
        tx.execute("INSERT OR REPLACE INTO metadata VALUES('schema','4')", [])?;
        let mut nonce = [0u8; 32];
        getrandom::fill(&mut nonce).map_err(|e| anyhow::anyhow!("storage revision: {e}"))?;
        let revision = crate::model::hash(nonce);
        tx.execute(
            "INSERT OR REPLACE INTO metadata VALUES('revision',?1)",
            [&revision],
        )?;
        tx.commit().context("publishing index transaction")?;
        Ok(revision)
    }
}
use rusqlite::OptionalExtension;
