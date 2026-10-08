"""Untuned static confirmation tasks, separate from the screening templates.

These authored cases are indexed and edited only as text. They are a narrow
TypeScript holdout, not a random sample of repositories or runtime validation.
Keep the answer keys outside the solver workspace and freeze before model use.
"""

from __future__ import annotations

import json
from pathlib import Path

from efficiency_gate_corpus import SourceTask, hashes, task


def build_tasks() -> list[SourceTask]:
    """Two independently authored source structures per six task families."""
    result = []

    sources = {"src/settings.ts": "export const settings = { title: 'Scuola', wire: 'Scuola' };\nexport const label = 'Scuola';\n"}
    result.append(task("holdout-local-object", "local", "local", None,
        "In src/settings.ts cambia solo settings.title da Scuola a Nido. settings.wire e label restano identici.",
        sources, {"src/settings.ts": sources["src/settings.ts"].replace("title: 'Scuola'", "title: 'Nido'")}))
    sources = {"src/options.ts": "export const options = ['read', 'write', 'read'];\nexport const wire = 'write';\n"}
    result.append(task("holdout-local-array", "local", "local", None,
        "In src/options.ts sostituisci solo il secondo elemento di options, write, con edit. Conserva gli altri elementi e wire.",
        sources, {"src/options.ts": sources["src/options.ts"].replace("['read', 'write', 'read']", "['read', 'edit', 'read']")}))

    sources = {
        "src/normalize.ts": "export function normalize(value: string): string { return value.trim(); }\n",
        "src/api.ts": "export { normalize } from './normalize';\n",
        "src/request.ts": "import { normalize as clean } from './api';\nexport function request(value: string): string { return clean(value); }\n",
        "src/direct.ts": "import { normalize } from './normalize';\nexport function direct(value: string): string { return normalize(value); }\n",
        "src/unrelated.ts": "export function normalize(value: number): number { return value; }\nexport const wire = 'normalize';\n",
    }
    expected = {name: text.replace("normalize", "canonicalize") for name, text in sources.items() if name != "src/unrelated.ts"}
    result.append(task("holdout-rename-reexport", "ambiguous_rename", "rename", "src/normalize.ts::normalize#function",
        "Rinomina la funzione esportata di src/normalize.ts da normalize a canonicalize, aggiornando re-export e import risolti. Mantieni l'alias locale clean, l'omonimo di unrelated.ts e la stringa wire.", sources, expected))
    sources = {
        "src/queue.ts": "export class Queue {\n  static open(id: number): number { return id; }\n  close(id: number): number { return id; }\n}\n",
        "src/batch.ts": "import { Queue as Work } from './queue';\nexport function batch(): number { return Work.open(1) + Work.open(2); }\n",
        "src/other.ts": "export class Door { static open(id: number): number { return id + 1; } }\nexport const wire = 'open';\nexport function unrelated(): number { return Door.open(3); }\n",
    }
    result.append(task("holdout-rename-static", "ambiguous_rename", "rename", "src/queue.ts::Queue.open#method",
        "Rinomina solo Queue.open in begin e aggiorna le due chiamate tramite alias Work. Conserva Queue.close, Door.open, unrelated e wire.", sources,
        {"src/queue.ts": sources["src/queue.ts"].replace("static open(", "static begin("), "src/batch.ts": sources["src/batch.ts"].replace("Work.open(", "Work.begin(")}))

    sources = {
        "src/format.ts": "export function format(id: number, label: string): string { return label + id; }\n",
        "src/pair.ts": "import { format as render } from './format';\nexport function pair(id: number): string { return render(id, 'a') + render(id + 1, 'b'); }\n",
        "src/wrapper.ts": "import { format } from './format';\nexport function wrapper(id: number): string { return format(id, 'fixed'); }\n",
        "src/other.ts": "export function format(id: string): string { return id; }\n",
    }
    result.append(task("holdout-signature-arguments", "public_signature", "change_signature", "src/format.ts::format#function",
        "Aggiungi a format in src/format.ts il parametro finale obbligatorio enabled: boolean. Ogni chiamante risolto deve passare true, preservando ordine e valori degli argomenti esistenti, il corpo e l'omonimo.", sources,
        {"src/format.ts": sources["src/format.ts"].replace("label: string)", "label: string, enabled: boolean)"),
         "src/pair.ts": sources["src/pair.ts"].replace("render(id, 'a')", "render(id, 'a', true)").replace("render(id + 1, 'b')", "render(id + 1, 'b', true)"),
         "src/wrapper.ts": sources["src/wrapper.ts"].replace("format(id, 'fixed')", "format(id, 'fixed', true)")}))
    sources = {
        "src/store.ts": "export class Store {\n  save(id: number): number { return id; }\n}\n",
        "src/adapter.ts": "import { Store } from './store';\nexport function adapt(store: Store, id: number): number { return store.save(id); }\n",
        "src/job.ts": "import { Store } from './store';\nimport { adapt } from './adapter';\nexport function job(store: Store): number { return adapt(store, 2) + store.save(3); }\n",
        "src/legacy.ts": "export class Legacy { save(id: number): number { return id * 2; } }\n",
    }
    result.append(task("holdout-signature-forwarding", "public_signature", "change_signature", "src/store.ts::Store.save#method",
        "Aggiungi a Store.save il parametro finale obbligatorio mode: string. Le chiamate dirette in adapt e job passano 'safe'. La firma di adapt, la sua chiamata in job, Legacy e il corpo di save restano identici.", sources,
        {"src/store.ts": sources["src/store.ts"].replace("save(id: number)", "save(id: number, mode: string)"),
         "src/adapter.ts": sources["src/adapter.ts"].replace("store.save(id)", "store.save(id, 'safe')"),
         "src/job.ts": sources["src/job.ts"].replace("store.save(3)", "store.save(3, 'safe')")}))

    sources = {
        "src/range.ts": "// Both endpoints are included; values outside the interval are rejected.\nexport function inside(value: number, min: number, max: number): boolean { return value >= min || value <= max; }\n",
        "src/checkin.ts": "import { inside } from './range';\nexport function checkin(age: number): string { return inside(age, 3, 6) ? 'yes' : 'no'; }\n",
    }
    result.append(task("holdout-bug-conjunction", "symptom_bug", "trace_flow", "src/checkin.ts::checkin#function",
        "checkin accetta anche età 2 e 7; deve accettare solo l'intervallo inclusivo da 3 a 6. Correggi l'operatore booleano responsabile, conservando confronti, commento e checkin.", sources,
        {"src/range.ts": sources["src/range.ts"].replace("min || value", "min && value")}))
    sources = {
        "src/fees.ts": "export function fee(base: number, units: number): number { return base + units + 2; }\n",
        "src/quote.ts": "import { fee } from './fees';\nexport function quote(units: number): number { return fee(5, units); }\n",
        "src/preview.ts": "import { quote } from './quote';\nexport function preview(): number { return quote(3); }\n",
        "src/other.ts": "export const display = 'base + units + 2';\n",
    }
    result.append(task("holdout-bug-arithmetic", "symptom_bug", "trace_flow", "src/preview.ts::preview#function",
        "preview deve costare 11: quota base 5 e 2 per ciascuna delle 3 unità. Correggi solo fee perché calcoli base + units * 2, conservando quote, preview e display.", sources,
        {"src/fees.ts": sources["src/fees.ts"].replace("base + units + 2", "base + units * 2")}))

    sources = {
        "src/entry.ts": "import { left, right } from './branches';\nexport function run(value: number): number { return left(value) + right(value); }\n",
        "src/branches.ts": "import { leaf } from './leaf';\nexport function left(value: number): number { return leaf(value); }\nexport function right(value: number): number { return leaf(value + 1); }\n",
        "src/leaf.ts": "export function leaf(value: number): number { return value * 2; }\n",
        "src/disconnected.ts": "export function run(value: string): string { return value; }\n",
    }
    result.append(task("holdout-flow-diamond", "branched_flow", "trace_flow", "src/entry.ts::run#function",
        "Senza modifiche, elenca in findings tutte le funzioni raggiungibili da src/entry.ts::run#function inclusa run. Ogni nome non qualificato una sola volta; escludi l'omonimo scollegato.", sources, {}, findings=("run", "left", "right", "leaf")))
    sources = {
        "src/start.ts": "import { descend } from './walk';\nexport function start(value: number): number { return descend(value); }\n",
        "src/walk.ts": "import { stop } from './stop';\nexport function descend(value: number): number { return value > 0 ? descend(value - 1) : stop(value); }\n",
        "src/stop.ts": "export function stop(value: number): number { return value; }\nexport function unused(value: number): number { return value + 9; }\n",
    }
    result.append(task("holdout-flow-recursion", "branched_flow", "trace_flow", "src/start.ts::start#function",
        "Senza modifiche, elenca in findings le funzioni raggiungibili da start, inclusa start; la ricorsione non duplica descend. Usa nomi non qualificati ed escludi unused.", sources, {}, findings=("start", "descend", "stop")))

    sources = {
        "src/review.ts": "export function bounded(value: number): boolean { return value >= 0 && value <= 10; }\nexport function untouched(value: number): number { return value + 1; }\n",
        "src/unrelated.ts": "export const wire = 'value <= 10';\n",
    }
    proposal = {"file": "src/review.ts", "old": "value <= 10", "new": "value < 10", "count": 1}
    result.append(task("holdout-review-endpoint", "large_file_review", "review_change", "src/review.ts",
        "Review statica: bounded deve includere gli estremi 0 e 10. Cattura baseline nativa su src/review.ts se disponibile; applica la proposta autorizzata sostituendo una volta value <= 10 con value < 10 in quel file. Verifica il delta con la stessa baseline; non correggerlo. In findings indica solo bounded. Conserva untouched e wire.", sources,
        {"src/review.ts": sources["src/review.ts"].replace(proposal["old"], proposal["new"])}, findings=("bounded",), proposed_edit=proposal))
    sources = {"src/layout.ts": "export function first(value: number): number { return value + 1; }\nexport function second(value: number): number { return value - 1; }\n"}
    proposal = {"file": "src/layout.ts", "old": sources["src/layout.ts"].rstrip("\n"),
                "new": "export function second(value: number): number { return value - 1; }\nexport function first(value: number): number { return value + 1; }", "count": 1}
    result.append(task("holdout-review-relocation", "large_file_review", "review_change", "src/layout.ts",
        "Review statica: prima di intervenire cattura baseline nativa sul file se disponibile. Scambia l'ordine delle due dichiarazioni intere in src/layout.ts, portando second prima di first; nessun'altra differenza di byte. Verifica poi il delta con la stessa baseline. I contratti e i corpi sono identici: findings deve essere vuoto.", sources,
        {"src/layout.ts": proposal["new"] + "\n"}, proposed_edit=proposal))
    return result


def write_corpus(destination: Path) -> list[dict]:
    """Create fresh snapshots with private expected hashes outside their roots."""
    destination.mkdir(parents=True, exist_ok=False)
    registered = []
    for item in build_tasks():
        root = destination / "snapshots" / item.name
        for name, text in item.sources.items():
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text, encoding="utf-8")
        registered.append({"id": item.name, "class": item.family, "snapshot": item.name,
            "profile": item.profile, "target": item.target, "prompt": item.prompt,
            "source_hashes": hashes(item.sources), "expected_hashes": hashes(item.expected),
            "expected_findings": sorted(item.findings), "proposed_edit": item.proposed_edit})
    (destination / "tasks.private.json").write_text(json.dumps(registered, ensure_ascii=False, indent=2), encoding="utf-8")
    return registered
