"""Client-boundary instrumentation for external executors; wire != model prompt.

Call observe_wire for MCP transport; call inject only at the actual prompt insertion
point, and record external reads/compaction explicitly. Raw text never enters the
published summary. This module neither calls a model nor guesses client behavior.
"""
from __future__ import annotations
import hashlib
import json


def compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def source_key(root_id: str, file_hash: str, start: int, end: int, text: str) -> str:
    return hashlib.sha256(compact([root_id, file_hash, start, end, hashlib.sha256(text.encode()).hexdigest()]).encode()).hexdigest()


class ContextLedger:
    def __init__(self) -> None:
        self.epoch = 0
        self.retained: set[str] = set()
        self.seen: set[str] = set()
        self.new_chars = self.repeated_chars = self.rehydrated_chars = 0
        self.external_reads = self.compactions = 0
        self.unidentified_chars = 0

    def compaction(self) -> None:
        self.epoch += 1
        self.retained.clear()
        self.compactions += 1

    def window(self, key: str, text: str, external: bool = False) -> None:
        if key in self.retained:
            self.repeated_chars += len(text)
        elif key in self.seen:
            self.rehydrated_chars += len(text)
        else:
            self.new_chars += len(text)
        self.retained.add(key)
        self.seen.add(key)
        if external:
            self.external_reads += 1

    def external(self, root_id: str, file_hash: str, start: int, end: int, text: str) -> None:
        # External read identity is content/range only; it is not semantic evidence.
        key = source_key(root_id, file_hash, start, end, text)
        self.window(key, text, external=True)


class Observer:
    def __init__(self, source_identity=None) -> None:
        # Optional callback(file) -> (root_id, current_file_hash) for older servers.
        # The executor must obtain these identities without inferring model retention.
        self.source_identity = source_identity
        self.ledger = ContextLedger()
        self.schema_hash = None
        self.instructions_hash = None
        self.mcp_calls = self.pages = self.expansions = 0
        self.model_requests = self.errors = self.retries = 0
        self.wire_bytes = self.injected_bytes = self.injected_chars = 0
        self.representations: set[str] = set()
        self.wire_duplicate_objects = 0
        self.context_inventory_verified = True

    def load_schema(self, actual_prompt_schema: str) -> None:
        self.schema_hash = hashlib.sha256(actual_prompt_schema.encode()).hexdigest()

    def load_instructions(self, actual_instructions: str) -> None:
        self.instructions_hash = hashlib.sha256(actual_instructions.encode()).hexdigest()

    def observe_wire(self, result: dict) -> None:
        self.mcp_calls += 1
        self.wire_bytes += len(compact(result).encode())
        if result.get('isError'):
            self.errors += 1
        if 'structuredContent' in result and result.get('content'):
            try:
                if json.loads(result['content'][0]['text']) == result['structuredContent']:
                    self.wire_duplicate_objects += 1
            except (ValueError, KeyError, IndexError):
                pass

    def _window(self, file: str, window: dict, root_id=None, file_hash=None) -> None:
        if 'text' not in window:
            return
        if self.source_identity and (not root_id or not file_hash):
            root_id, file_hash = self.source_identity(file)
        if root_id and file_hash and 'start_line' in window and 'end_line' in window:
            key = source_key(root_id, file_hash, window['start_line'], window['end_line'], window['text'])
        elif window.get('window_id'):
            key = window['window_id']
        else:
            self.ledger.unidentified_chars += len(window['text'])
            return
        self.ledger.window(key, window['text'])

    def _source(self, value: dict) -> None:
        for file in value.get('files', []):
            for window in file.get('snippets', []):
                self._window(file['file'], window, value.get('context', {}).get('root_id'), file.get('source_hash'))
        # Primitive snippet and inspect_change(include_snippet) are source too.
        if 'file' in value and 'text' in value:
            self._window(value['file'], value, value.get('root_id'), value.get('source_hash'))
        if isinstance(value.get('snippet'), dict):
            self._source(value['snippet'])

    def inject(self, result: dict, representation: str, transformed: str | None = None,
               prompt_windows: list[dict] | None = None) -> str:
        values = []
        if representation == 'text':
            text = result['content'][0]['text']
            try:
                values.append(json.loads(text))
            except ValueError:
                self.ledger.unidentified_chars += len(text)
                self.context_inventory_verified = False
        elif representation == 'structured':
            text = compact(result['structuredContent'])
            values.append(result['structuredContent'])
        elif representation == 'both':
            text = compact(dict(content=result['content'], structuredContent=result['structuredContent']))
            values.append(result['structuredContent'])
            for block in result['content']:
                if block.get('type') == 'text':
                    try:
                        values.append(json.loads(block['text']))
                    except ValueError:
                        self.ledger.unidentified_chars += len(block['text'])
                        self.context_inventory_verified = False
        elif representation == 'transformed' and transformed is not None:
            text = transformed
            # Only the executor at insertion can declare transformed source windows.
            # An explicit empty inventory means no source, not automatic retention.
            if prompt_windows is None:
                self.ledger.unidentified_chars += len(text)
                self.context_inventory_verified = False
            else:
                for window in prompt_windows:
                    self._window(window['file'], window, window.get('root_id'), window.get('source_hash'))
        else:
            raise ValueError('actual client response representation must be explicit')
        self.representations.add(representation)
        self.injected_bytes += len(text.encode())
        self.injected_chars += len(text)
        if any(isinstance(value, dict) and value.get('intent') for value in values):
            self.pages += 1
        for value in values:
            if isinstance(value, dict):
                self._source(value)
        return text

    def summary(self) -> dict:
        return dict(actual_schema_sha256=self.schema_hash,
                    loaded_graph_instructions_sha256=self.instructions_hash,
                    response_representation=sorted(self.representations),
                    model_requests=self.model_requests, mcp_calls=self.mcp_calls,
                    external_reads=self.ledger.external_reads,
                    new_context_chars=self.ledger.new_chars,
                    repeated_context_chars=self.ledger.repeated_chars,
                    rehydrated_context_chars=self.ledger.rehydrated_chars,
                    pages=self.pages, expansions=self.expansions, compactions=self.ledger.compactions,
                    errors=self.errors, retries=self.retries,
                    wire_bytes=self.wire_bytes, injected_bytes=self.injected_bytes,
                    injected_chars=self.injected_chars, wire_duplicate_objects=self.wire_duplicate_objects,
                    unidentified_context_chars=self.ledger.unidentified_chars,
                    context_identity_complete=self.ledger.unidentified_chars == 0 and self.context_inventory_verified,
                    measurement_scope='exact retained windows at explicit client prompt insertion and retained-window observations; characters are not model usage')
