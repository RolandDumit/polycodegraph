# Fixture contracts

Tests query compact graph rows using stable IDs. Fixtures are copied to temporary directories before mutations.

## Dart

- `LoadUserUseCase.call` calls the static interface `UserRepository.fetch`; `decoy` calls only `Unrelated.fetch`.
- `MemoryRepository`, `ChildRepository`, and `AliasRepository` implement/extend the repository contract; members override the contract transitively.
- `domain.dart` and its `model.dart` part retain both directions of part dependencies; imports and exports in `use_case.dart` resolve to local files.
- Impact of `UserRepository.fetch` reaches `run` and `use_case.dart`, but not `unused.dart`. Changing `MemoryRepository.fetch` reaches interface callers via its dispatch contract.
- A warm refresh retains generation and reuses every record. Editing a dependency refreshes consumers while reusing `unused.dart`; a semantic rename removes stale calls from unchanged consumers.
- Package aliases, generic substitutions, getters/setters, unary/binary operators and extension-type constructors resolve to distinct real declarations.

## Flutter

The package-backed fixture must classify `HomeScreen` as Widget/Screen, `UserCubit`, `userRepositoryProvider`, `homeRoute`, `User` as Freezed, and typed GetIt registrations. Domain changes affect the screen. Missing package configuration is an explicit skip in ordinary tests and an error in `tool/check.dart --flutter`.

## Other languages

`test/fixtures/polyglot/` supplies TypeScript and JavaScript imports, a Java interface with implementing and overloaded methods, and a Go interface with implicit implementation. Integration tests require real compiler adapters, check calls/references/implementations/dependencies and impact, reject unrelated same-name targets, and mutate source to check cache refresh. TypeScript fixtures share a constructor across two tsconfig scopes; Go receiver methods live in a separate file from their type. Missing runtimes are skips only in the optional local suite; `tool/check.dart --providers` requires full coverage.

## Python and Rust

`test/fixtures/semantic/` is copied into the mixed-language fixture and exercised independently. Python `load`/`load_async` resolve to the typed repository contract; alias-based construction/concrete calls resolve to `MemoryRepository`. Constructors, assigned instance fields, property/async tags and explicit override relationships are indexed. An unknown callback creates no call target and increases unresolved coverage. The indexed `json.py` writes a marker if executed; the marker must remain absent.

Rust `load` targets the declared trait method, concrete calls target its impl, and unrelated same-name methods stay disconnected. Trait implementations, modules, structs, enum variants, type aliases, constants and fields are extracted. Local Cargo path dependency aliases resolve across crate boundaries. Cargo's build file, custom rustc wrapper and nonexistent toolchain override must not execute or affect indexing. A root rust-project model discards runnable/proc-macro executable fields.

Renaming contract methods must remove stale calls from unchanged consumers in both languages. Warm caches avoid work; Python/Rust manifests and project-model edits invalidate bindings. Unicode identifiers, percent-escaped filenames, astral characters and CRLF preserve source snippets and resolved calls. Missing runtimes produce file nodes with explicit diagnostics. `--providers` requires these tests; compiled MCP smoke tests cover all seven languages on each CI operating system.

## Transport and boundaries

`mcp_test.dart` exercises a real stdio subprocess, initialization, tool schemas, validation, framing, cancellation and bounded errors. Config and graph tests verify path traversal/symlink rejection, ambiguity, stable pagination, snippet bounds and source freshness. Preserve these guarantees as providers are added.
