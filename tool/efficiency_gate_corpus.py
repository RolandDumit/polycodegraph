"""Controlled screening source tasks and independent static postimages.

Generated TypeScript is indexed and edited as text, never executed. Oracle data
must remain outside the solver workspace. This corpus supports static evidence
and edit checks, not application runtime correctness or independent holdout.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceTask:
    """One distinct source task with exact permitted postimages and findings."""

    name: str
    family: str
    profile: str
    target: str | None
    prompt: str
    sources: dict[str, str]
    expected: dict[str, str]
    findings: tuple[str, ...] = ()
    proposed_edit: dict | None = None


def noise(case: int, count: int = 12) -> dict[str, str]:
    """Keep ordinary search useful while supplying distinct unrelated declarations."""
    return {
        f"src/catalog/item_{i:02}.ts": (
            f"export interface Item{i} {{ id: number; label: string; }}\n"
            f"export function label{i}(item: Item{i}): string {{ return item.label; }}\n"
            f"export const revision{i} = {case + i};\n"
        )
        for i in range(count)
    }


def task(
    name: str,
    family: str,
    profile: str,
    target: str | None,
    prompt: str,
    sources: dict[str, str],
    expected: dict[str, str],
    **extra,
) -> SourceTask:
    """Add the same explicit static constraints to each condition's task prompt."""
    sources = {
        "tsconfig.json": json.dumps(
            {"compilerOptions": {"strict": True, "target": "ES2022"}, "include": ["src/**/*.ts"]}
        )
        + "\n",
        **sources,
    }
    expected = {**sources, **expected}
    return SourceTask(
        name,
        family,
        profile,
        target,
        prompt
        + (
            "\nUsa gli strumenti di lettura, ricerca e modifica limitata disponibili. "
            "Modifica soltanto i sorgenti necessari, preservando il resto del testo identico; "
            "niente riformattazione, test, compilazione, script o esecuzione. "
            "Se PolyCodeGraph è registrato, usa l'intent disponibile sul target indicato "
            "e controlla i fatti nelle fonti. Non inventare completezza del provider. "
            "Alla fine restituisci JSON con findings (nomi simbolici richiesti, altrimenti array vuoto) "
            "e limitations (limiti effettivi delle verifiche)."
        ),
        sources,
        expected,
        **extra,
    )


def build_tasks() -> list[SourceTask]:
    """Build two tasks per six families with no graph-derived answer keys."""
    result = []
    for i, (literal, replacement) in enumerate(
        (("invalid-id", "invalid-reference"), ("missing-user", "missing-account")), 1
    ):
        source = f"export const message = '{literal}';\nexport const protocolKey = '{literal}';\n"
        expected = source.replace(f"message = '{literal}'", f"message = '{replacement}'")
        result.append(
            task(
                f"local-{i}",
                "local_edit",
                "local",
                None,
                f"In src/messages.ts cambia soltanto il valore della costante message da {literal!r} a {replacement!r}; la chiave protocolKey deve restare invariata.",
                {**noise(i), "src/messages.ts": source},
                {"src/messages.ts": expected},
            )
        )

    for i, (klass, method, renamed, consumers) in enumerate(
        (("Courier", "send", "deliver", 18), ("Ledger", "commit", "persist", 24)), 1
    ):
        file = "src/service.ts"
        sources = {
            **noise(10 + i),
            file: f"export class {klass} {{\n  {method}(value: number): number {{ return value; }}\n}}\n",
        }
        expected = {file: sources[file].replace(f"  {method}(", f"  {renamed}(")}
        for n in range(consumers):
            name = f"src/consumers/c{n:02}.ts"
            sources[name] = (
                f"import {{ {klass} as Receiver }} from '../service';\n"
                f"export function forward{n}(receiver: Receiver): number {{\n"
                f"  return receiver.{method}({n}) + receiver.{method}({n + 1});\n}}\n"
            )
            expected[name] = sources[name].replace(f"receiver.{method}(", f"receiver.{renamed}(")
        sources["src/unrelated.ts"] = (
            f"export class Other {{ {method}(value: number) {{ return value + 1; }} }}\n"
            f"export const wireKey = '{method}';\nexport function other(value: Other) {{ return value.{method}(2); }}\n"
        )
        result.append(
            task(
                f"rename-{i}",
                "ambiguous_rename",
                "rename",
                f"{file}::{klass}.{method}#method",
                f"Rinomina soltanto il metodo {klass}.{method} in {renamed} e tutti i suoi riferimenti risolti di produzione. Mantieni Other.{method}, la sua chiamata e la chiave wireKey invariati. Target: {file}::{klass}.{method}#method.",
                sources,
                expected,
            )
        )

    for i, (method, argument, value) in enumerate((("fetch", "limit", 10), ("reserve", "priority", 3)), 1):
        file = "src/service.ts"
        sources = {
            **noise(20 + i),
            file: f"export class Service {{\n  {method}(id: number): number {{ return id; }}\n}}\n",
        }
        expected = {file: sources[file].replace("id: number)", f"id: number, {argument}: number)")}
        for n in range(15 + i * 3):
            name = f"src/forwarding/f{n:02}.ts"
            sources[name] = (
                "import { Service as Backend } from '../service';\n"
                f"export function forward{n}(backend: Backend, id: number): number {{ return backend.{method}(id); }}\n"
            )
            expected[name] = sources[name].replace(f".{method}(id)", f".{method}(id, {value})")
        sources["src/other.ts"] = (
            f"export function {method}(id: number): number {{ return id; }}\nexport const label = '{method}';\n"
        )
        result.append(
            task(
                f"signature-{i}",
                "public_signature",
                "change_signature",
                f"{file}::Service.{method}#method",
                f"Aggiungi al metodo Service.{method} il parametro obbligatorio finale {argument}: number. Tutti i suoi chiamanti devono passare il valore {value}; il corpo resta return id e l'omonima funzione libera non cambia. Target: {file}::Service.{method}#method.",
                sources,
                expected,
            )
        )

    for i, (limit, old, new, description) in enumerate(
        (
            (5, ">", ">=", "Il valore pari alla capacità deve essere respinto"),
            (0, "<", "<=", "Lo zero deve essere respinto insieme ai valori negativi"),
        ),
        1,
    ):
        leaf = f"export function allowed(value: number): boolean {{ return !(value {old} {limit}); }}\n"
        sources = {
            **noise(30 + i),
            "src/check.ts": leaf,
            "src/route.ts": "import { allowed } from './check';\nexport function route(value: number): string { return allowed(value) ? 'accepted' : 'rejected'; }\n",
            "src/entry.ts": "import { route } from './route';\nexport function submit(value: number): string { return route(value); }\n",
        }
        result.append(
            task(
                f"bug-{i}",
                "symptom_bug",
                "trace_flow",
                "src/entry.ts::submit#function",
                f"Sintomo: {description}. submit deve restituire rejected al valore {limit}, mantenendo invariati gli altri casi. Trova e correggi il confronto responsabile senza cambiare route o submit. Target: src/entry.ts::submit#function.",
                sources,
                {"src/check.ts": leaf.replace(f"value {old} {limit}", f"value {new} {limit}")},
            )
        )

    for i in (1, 2):
        leaf_a, leaf_b = ("encode", "reject") if i == 1 else ("cache", "refresh")
        sources = {
            **noise(40 + i),
            "src/entry.ts": "import { choose } from './branch';\nexport function dispatch(value: number): number { return choose(value); }\n",
            "src/branch.ts": f"import {{ {leaf_a}, {leaf_b} }} from './leaves';\nexport function choose(value: number): number {{ return value > 0 ? {leaf_a}(value) : {leaf_b}(value); }}\n",
            "src/leaves.ts": f"export function {leaf_a}(value: number): number {{ return value + 1; }}\nexport function {leaf_b}(value: number): number {{ return value - 1; }}\n",
            "src/unused.ts": "export function dispatch(value: string): string { return value; }\n",
        }
        result.append(
            task(
                f"flow-{i}",
                "branched_flow",
                "trace_flow",
                "src/entry.ts::dispatch#function",
                "Senza modificare file, elenca in findings tutti i simboli di funzione raggiungibili da src/entry.ts::dispatch#function, inclusa la funzione iniziale ed entrambi i rami. Usa i nomi non qualificati, senza ripetizioni; escludi gli omonimi scollegati.",
                sources,
                {},
                findings=("dispatch", "choose", leaf_a, leaf_b),
            )
        )

    for i in (1, 2):
        expression = "value > 0" if i == 1 else "value < 100"
        replacement = "value >= 0" if i == 1 else "value <= 100"
        contract = "strettamente positivi" if i == 1 else "strettamente inferiori a 100"
        head = f"export function accept(value: number): boolean {{ return {expression}; }}\n"
        long_file = head + "\n".join(f"export const retained{i}_{n} = {n};" for n in range(360)) + "\n"
        changed = head.rstrip("\n").replace(expression, replacement)
        sources = {**noise(50 + i), "src/large.ts": long_file}
        proposal = {"file": "src/large.ts", "old": head.rstrip("\n"), "new": changed, "count": 1}
        result.append(
            task(
                f"review-{i}",
                "large_file_review",
                "review_change",
                "src/large.ts",
                f"Review statica di src/large.ts: accept deve accettare soltanto valori {contract}. Prima della modifica, se il grafo è disponibile, cattura una baseline nativa su quel file. Applica con source_replace la proposta autorizzata: sostituisci nella funzione accept '{expression}' con '{replacement}' (una occorrenza). Poi verifica il delta, usando la stessa baseline se disponibile. Non correggere la proposta. In findings indica soltanto il simbolo che ora viola il contratto. Tutte le costanti restano identiche.",
                sources,
                {"src/large.ts": long_file.replace(head.rstrip("\n"), changed)},
                findings=("accept",),
                proposed_edit=proposal,
            )
        )
    return result


def hashes(sources: dict[str, str]) -> dict[str, str]:
    """Hash exact UTF-8 fixture bytes without token estimation."""
    return {name: hashlib.sha256(text.encode()).hexdigest() for name, text in sorted(sources.items())}


def write_corpus(destination: Path) -> list[dict]:
    """Create fresh snapshots and private oracle keys; refuse existing destinations."""
    destination.mkdir(parents=True, exist_ok=False)
    registered = []
    for item in build_tasks():
        root = destination / "snapshots" / item.name
        root.mkdir(parents=True)
        for name, text in item.sources.items():
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text, encoding="utf-8")
        registered.append(
            {
                "id": item.name,
                "class": item.family,
                "snapshot": item.name,
                "profile": item.profile,
                "target": item.target,
                "prompt": item.prompt,
                "source_hashes": hashes(item.sources),
                "expected_hashes": hashes(item.expected),
                "expected_findings": sorted(item.findings),
                "proposed_edit": item.proposed_edit,
            }
        )
    (destination / "tasks.private.json").write_text(
        json.dumps(registered, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return registered
