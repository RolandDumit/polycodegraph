use crate::{config::Config, index::Indexer};
use anyhow::{Result, bail};
use serde_json::{Value, json};
use std::{
    collections::HashSet,
    sync::{Arc, Mutex},
};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt},
    sync::mpsc,
};
pub fn tools(c: &Config) -> Vec<Value> {
    let mut tools: Vec<Value> =
        serde_json::from_str(include_str!("tools.json")).expect("embedded schemas are valid");
    for t in &mut tools {
        if !t["inputSchema"]["properties"]["limit"].is_null() {
            t["inputSchema"]["properties"]["limit"]["maximum"] = json!(c.max_results);
        }
    }
    tools
}
pub fn validate(spec: &Value, a: &Value) -> Result<()> {
    let obj = a
        .as_object()
        .ok_or_else(|| anyhow::anyhow!("Arguments must be an object"))?;
    for key in spec["inputSchema"]["required"]
        .as_array()
        .into_iter()
        .flatten()
    {
        let key = key.as_str().unwrap_or("");
        if !obj.contains_key(key) {
            bail!("Missing argument: {key}")
        }
    }
    for (key, value) in obj {
        let s = &spec["inputSchema"]["properties"][key];
        if s.is_null() {
            bail!("Unknown argument: {key}")
        }
        if value.is_u64() && value.as_i64().is_none() {
            bail!("{key} is out of range");
        }
        let valid = match s["type"].as_str() {
            Some("string") => value.is_string(),
            Some("integer") => value.is_i64() || value.is_u64(),
            Some("boolean") => value.is_boolean(),
            Some("array") => value.as_array().is_some_and(|a| {
                a.len() <= 32
                    && a.iter()
                        .all(|v| v.as_str().is_some_and(|s| s.encode_utf16().count() <= 128))
            }),
            _ => false,
        };
        if !valid {
            bail!("Invalid type for {key}")
        }
        if let Some(n) = value.as_i64()
            && (s["minimum"].as_i64().is_some_and(|min| n < min)
                || s["maximum"].as_i64().is_some_and(|max| n > max))
        {
            bail!("{key} is out of range")
        }
        if let Some(v) = value.as_str()
            && (v.encode_utf16().count() > 4096
                || s["minLength"]
                    .as_u64()
                    .is_some_and(|n| v.encode_utf16().count() < (n as usize)))
        {
            bail!("Invalid length for {key}")
        }
        if s["enum"].as_array().is_some_and(|e| !e.contains(value)) {
            bail!("Invalid value for {key}")
        }
    }
    Ok(())
}
fn error(id: Value, code: i64, message: &str) -> Value {
    json!({"jsonrpc":"2.0","id":id,"error":{"code":code,"message":message}})
}
struct Session {
    initialized: bool,
    ready: bool,
}
impl Session {
    async fn handle(&mut self, index: &mut Indexer, v: Value) -> Option<Value> {
        let id = v["id"].clone();
        let Some(obj) = v.as_object() else {
            return Some(error(Value::Null, -32600, "Invalid Request"));
        };
        if v["jsonrpc"] != "2.0"
            || !v["method"].is_string()
            || (obj.contains_key("id") && !id.is_null() && !id.is_string() && !id.is_i64())
        {
            return Some(error(Value::Null, -32600, "Invalid Request"));
        }
        let method = v["method"].as_str().unwrap_or("");
        if !obj.contains_key("id") {
            if method == "notifications/initialized" && self.initialized {
                self.ready = true
            }
            return None;
        }
        let empty = json!({});
        let params = if v["params"].is_null() {
            &empty
        } else {
            &v["params"]
        };
        if !params.is_object() {
            return Some(error(id, -32602, "Params must be an object"));
        }
        let result = match method {
            "initialize" => {
                if self.initialized {
                    return Some(error(id, -32600, "Already initialized"));
                }
                if !params["protocolVersion"].is_string()
                    || !params["capabilities"].is_object()
                    || !params["clientInfo"].is_object()
                {
                    return Some(error(
                        id,
                        -32602,
                        "protocolVersion, capabilities and clientInfo are required",
                    ));
                }
                self.initialized = true;
                let requested = params["protocolVersion"].as_str().unwrap_or("");
                let version = if ["2025-11-25", "2025-06-18", "2025-03-26"].contains(&requested) {
                    requested
                } else {
                    "2025-11-25"
                };
                json!({"protocolVersion":version,"capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"polycodegraph","version":"0.5.0"},"instructions":"Check status freshness and coverage, find stable ids with search_symbol, then inspect_change. Static dispatch is incomplete; run compiler checks and tests."})
            }
            "ping" => json!({}),
            "tools/list" | "tools/call" => {
                if !self.ready {
                    return Some(error(
                        id,
                        -32000,
                        "Initialize and send notifications/initialized first",
                    ));
                }
                let specs = tools(&index.config);
                if method == "tools/list" {
                    if params.as_object().is_some_and(|p| !p.is_empty()) {
                        return Some(error(
                            id,
                            -32602,
                            "tools/list has no cursor; all tools fit on one page",
                        ));
                    }
                    json!({"tools":specs})
                } else {
                    let Some(name) = params["name"].as_str() else {
                        return Some(error(id, -32602, "Invalid tool call"));
                    };
                    let Some(spec) = specs.iter().find(|s| s["name"] == name) else {
                        return Some(error(id, -32602, &format!("Unknown tool: {name}")));
                    };
                    let a = if params["arguments"].is_null() {
                        json!({})
                    } else {
                        params["arguments"].clone()
                    };
                    if !a.is_object() {
                        return Some(error(id, -32602, "Invalid tool call"));
                    }
                    let result = match validate(spec, &a) {
                        Ok(()) => index.call(name, &a).await,
                        Err(e) => Err(e),
                    };
                    match result {
                        Ok(data) => {
                            json!({"content":[{"type":"text","text":data.to_string()}],"structuredContent":data,"isError":false})
                        }
                        Err(e) => {
                            json!({"content":[{"type":"text","text":json!({"error":e.to_string()}).to_string()}],"isError":true})
                        }
                    }
                }
            }
            _ => return Some(error(id, -32601, "Method not found")),
        };
        Some(json!({"jsonrpc":"2.0","id":id,"result":result}))
    }
}
#[derive(Default)]
struct Flight {
    active: HashSet<String>,
    cancelled: HashSet<String>,
}
async fn send<W: AsyncWrite + Unpin>(sink: &Arc<tokio::sync::Mutex<W>>, v: &Value) -> Result<()> {
    let mut line = serde_json::to_vec(v)?;
    line.push(b'\n');
    let mut sink = sink.lock().await;
    sink.write_all(&line).await?;
    sink.flush().await?;
    Ok(())
}
pub async fn serve<R: AsyncRead + Unpin, W: AsyncWrite + Unpin + Send + 'static>(
    mut input: R,
    output: W,
    mut index: Indexer,
) -> Result<()> {
    let (tx, mut rx) = mpsc::channel::<Value>(64);
    let sink = Arc::new(tokio::sync::Mutex::new(output));
    let flight = Arc::new(Mutex::new(Flight::default()));
    let worker_sink = sink.clone();
    let worker_flight = flight.clone();
    let worker = tokio::spawn(async move {
        let mut session = Session {
            initialized: false,
            ready: false,
        };
        let mut period = std::time::Duration::from_secs(index.config.reconcile_interval_seconds);
        let mut ticker = tokio::time::interval(period);
        ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        ticker.tick().await;
        loop {
            tokio::select! {
                message = rx.recv() => {
                    let Some(message) = message else { break };
                    let key = message.get("id").map(Value::to_string);
                    let skip = key.as_ref().is_some_and(|k| worker_flight.lock().expect("flight mutex").cancelled.contains(k));
                    if !skip {
                        let response = session.handle(&mut index, message).await;
                        let cancelled = key.as_ref().is_some_and(|k| worker_flight.lock().expect("flight mutex").cancelled.contains(k));
                        if let Some(response) = response && !cancelled { send(&worker_sink, &response).await?; }
                    }
                    if let Some(k) = key {
                        let mut state = worker_flight.lock().expect("flight mutex");
                        state.active.remove(&k);
                        state.cancelled.remove(&k);
                    }
                }
                _ = ticker.tick() => {
                    if index.graph.is_some() && let Err(e) = index.refresh(true, false).await { eprintln!("reconciliation: {e:#}"); }
                }
            }
            let next = std::time::Duration::from_secs(index.config.reconcile_interval_seconds);
            if next != period {
                period = next;
                ticker = tokio::time::interval_at(tokio::time::Instant::now() + period, period);
                ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            }
        }
        Ok::<_, anyhow::Error>(())
    });
    let mut chunk = [0; 32768];
    let mut line = Vec::new();
    let mut overflow = false;
    loop {
        let size = input.read(&mut chunk).await?;
        if size == 0 {
            break;
        }
        for &b in &chunk[..size] {
            if b != b'\n' {
                if line.len() < 1048576 && !overflow {
                    line.push(b)
                } else {
                    overflow = true;
                    line.clear()
                }
                continue;
            }
            let message = if overflow {
                None
            } else {
                serde_json::from_slice::<Value>(&line).ok()
            };
            line.clear();
            overflow = false;
            let Some(message) = message else {
                send(
                    &sink,
                    &error(Value::Null, -32700, "Parse error or oversized message"),
                )
                .await?;
                continue;
            };
            if message["method"] == "notifications/cancelled" {
                let k = message["params"]["requestId"].to_string();
                let mut state = flight.lock().expect("flight mutex");
                if state.active.contains(&k) {
                    state.cancelled.insert(k);
                }
                continue;
            }
            let key = message.get("id").map(Value::to_string);
            let at_limit = flight.lock().expect("flight mutex").active.len() >= 64;
            if at_limit && key.is_some() {
                send(
                    &sink,
                    &error(message["id"].clone(), -32000, "Server queue full"),
                )
                .await?;
                continue;
            }
            let duplicate = if let Some(k) = &key {
                !flight
                    .lock()
                    .expect("flight mutex")
                    .active
                    .insert(k.clone())
            } else {
                false
            };
            if duplicate {
                send(
                    &sink,
                    &error(
                        message["id"].clone(),
                        -32600,
                        "Request id already in flight",
                    ),
                )
                .await?;
                continue;
            }
            match tx.try_send(message) {
                Ok(()) => {}
                Err(e) => {
                    let v = e.into_inner();
                    if let Some(k) = key {
                        flight.lock().expect("flight mutex").active.remove(&k);
                        send(&sink, &error(v["id"].clone(), -32000, "Server queue full")).await?;
                    }
                }
            }
        }
    }
    if !line.is_empty() || overflow {
        send(
            &sink,
            &error(Value::Null, -32700, "Parse error or oversized message"),
        )
        .await?;
    }
    drop(tx);
    worker.await??;
    Ok(())
}
