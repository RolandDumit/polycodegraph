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

## Transport and boundaries

`mcp_test.dart` exercises a real stdio subprocess, initialization, tool schemas, validation, framing, cancellation and bounded errors. Config and graph tests verify path traversal/symlink rejection, ambiguity, stable pagination, snippet bounds and source freshness. Preserve these guarantees as providers are added.
