import 'dart:io';
import 'package:path/path.dart' as p;
import 'package:polycodegraph/polycodegraph.dart';
import 'package:test/test.dart';
import 'support.dart';

List<String> targetIds(Map<String, dynamic> result) =>
    (result['rows'] as List).map((row) => row[0] as String).toList();

void main() {
  final providers = Directory('providers').absolute.path;
  final options = GraphConfig(
    root: '.',
    providersPath: providers,
    pythonPath: Platform.environment['PYTHON_PROVIDER'],
    rustAnalyzerPath: Platform.environment['RUST_ANALYZER'] ?? 'rust-analyzer',
  );
  final adapter = ExternalProviders(options);
  final health = adapter.doctor();
  final available =
      [
        'python',
        'rust',
      ].every((key) => (health[key] as Map)['available'] == true) &&
      adapter.semanticSetup['jedi'] != null &&
      adapter.semanticSetup['rust_analyzer'] != null;
  if (Platform.environment['POLYCODEGRAPH_REQUIRE_PROVIDERS'] == '1' &&
      !available) {
    throw StateError('Required Python/Rust providers unavailable: $health');
  }

  group(
    'Python and Rust semantic graph',
    () {
      late Directory repo;
      late RepositoryIndexer indexer;
      late GraphQuery graph;
      setUp(() async {
        repo = Directory.systemTemp.createTempSync(
          'polycodegraph semantic spaces ',
        );
        copyTree(Directory('test/fixtures/semantic'), repo);
        indexer = RepositoryIndexer(
          GraphConfig(
            root: repo.path,
            providersPath: providers,
            pythonPath: options.pythonPath,
            rustAnalyzerPath: options.rustAnalyzerPath,
          ),
        );
        graph = GraphQuery((await indexer.refresh()).snapshot, indexer.config);
      });
      tearDown(() => repo.deleteSync(recursive: true));

      test(
        'symbols, typed calls and same-name decoys use semantic targets',
        () {
          expect(
            (graph.architecture()['languages'] as Map).keys,
            containsAll(['python', 'rust']),
          );
          final errors = graph.snapshot.files.values
              .expand((file) => file.diagnostics)
              .where((diagnostic) => diagnostic['severity'] == 'error')
              .toList();
          expect(errors, isEmpty, reason: '$errors');
          expect(
            graph.search(
              '__init__',
              language: 'python',
              kind: 'constructor',
            )['total'],
            1,
          );
          expect(
            graph.search('prefix', language: 'python', kind: 'field')['total'],
            1,
          );
          expect(
            graph.search('label', language: 'python', tag: 'property')['total'],
            1,
          );
          expect(
            graph.search(
              'load_async',
              language: 'python',
              tag: 'async',
            )['total'],
            1,
          );
          expect(
            graph.search(
              'Identifier',
              language: 'rust',
              kind: 'typedef',
            )['total'],
            1,
          );
          expect(
            graph.search('LoadState', language: 'rust', kind: 'enum')['total'],
            1,
          );
          for (final language in ['python', 'rust']) {
            final file = language == 'python'
                ? 'python/use.py'
                : 'rust/src/use_case.rs';
            final domain = language == 'python'
                ? 'python/domain.py'
                : 'rust/src/domain.rs';
            final calls = targetIds(
              graph.relations(
                '$file::load#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            );
            expect(calls, contains('$domain::Repository.fetch#method'));
            expect(calls.any((id) => id.contains('Unrelated')), isFalse);
            final implementations = targetIds(
              graph.implementations('$domain::Repository.fetch#method'),
            );
            expect(
              implementations.any(
                (id) => id.contains('MemoryRepository') && id.contains('fetch'),
              ),
              isTrue,
            );
            expect(
              implementations.any((id) => id.contains('Unrelated')),
              isFalse,
            );
            expect(targetIds(graph.dependencies(file)), contains(domain));
            final affected = targetIds(
              graph.affected('$domain::Repository.fetch#method'),
            );
            expect(affected, contains('$file::load#function'));
            expect(
              affected.any((id) => id.contains('Unrelated.fetch')),
              isFalse,
            );
          }
          expect(
            File(p.join(repo.path, 'PYTHON_SOURCE_RAN')).existsSync(),
            isFalse,
          );
          expect(
            File(p.join(repo.path, 'rust/BUILD_SCRIPT_RAN')).existsSync(),
            isFalse,
          );
        },
      );

      test('dynamic Python calls remain explicit and never invent targets', () {
        expect(
          graph.snapshot.files['python/use.py']!.unresolvedCalls,
          greaterThanOrEqualTo(1),
        );
        expect(
          targetIds(
            graph.relations(
              'python/use.py::dynamic#function',
              direction: 'out',
              kinds: {'calls'},
            ),
          ),
          isEmpty,
        );
        expect(
          graph.snapshot.files['python/use.py']!.diagnostics.map(
            (d) => d['code'],
          ),
          contains('unresolved_calls'),
        );
      });

      test(
        'signature changes rebind unedited Python and Rust consumers',
        () async {
          for (final language in ['python', 'rust']) {
            final declaration = language == 'python'
                ? 'python/domain.py'
                : 'rust/src/domain.rs';
            final consumer = language == 'python'
                ? 'python/use.py'
                : 'rust/src/use_case.rs';
            final file = File(p.join(repo.path, declaration));
            final before = file.readAsStringSync();
            file.writeAsStringSync(
              before.replaceFirst(
                language == 'python' ? 'def fetch(' : 'fn fetch(',
                language == 'python' ? 'def read(' : 'fn read(',
              ),
            );
            final report = await indexer.refresh();
            expect(report.reindexed, contains(consumer));
            final refreshed = GraphQuery(report.snapshot, indexer.config);
            expect(
              targetIds(
                refreshed.relations(
                  '$consumer::load#function',
                  direction: 'out',
                  kinds: {'calls'},
                ),
              ),
              isEmpty,
            );
            expect(
              refreshed.nodes,
              isNot(contains('$declaration::Repository.fetch#method')),
            );
            expect(report.snapshot.files[consumer]!.diagnostics, isNotEmpty);
            file.writeAsStringSync(before);
            await indexer.refresh();
          }
        },
      );

      test(
        'warm cache and manifest/config edits invalidate project bindings',
        () async {
          final warm = await indexer.refresh();
          expect(warm.reindexed, isEmpty);
          for (final name in [
            'rust/Cargo.toml',
            'pyproject.toml',
            'rust-project.json',
          ]) {
            final manifest = File(p.join(repo.path, name));
            if (name == 'rust/Cargo.toml') {
              manifest.writeAsStringSync(
                '${manifest.readAsStringSync()}\n[features]\ndefault = []\n',
              );
            } else if (name == 'pyproject.toml') {
              manifest.writeAsStringSync(
                '[project]\nname="semantic-fixture"\nversion="1.0.0"\n',
              );
            } else {
              // Project contents are intentionally invalid: fallback must replace
              // stale bindings with an explicit provider diagnostic.
              manifest.writeAsStringSync('{"crates":[]}');
            }
            final report = await indexer.refresh();
            expect(report.full, isTrue, reason: name);
          }
          expect(
            indexer.snapshot!.files['rust/src/domain.rs']!.diagnostics,
            isNotEmpty,
          );
        },
      );

      test(
        'Unicode, escaped file URIs and CRLF retain snippets and call targets',
        () async {
          File(p.join(repo.path, 'python/unicodé % file.py')).writeAsStringSync(
            '# astral 🌍\r\ndef résumé() -> str:\r\n    return "ok"\r\n\r\ndef invoke() -> str:\r\n    return résumé()\r\n',
          );
          File(
            p.join(repo.path, 'rust/src/unicodé % file.rs'),
          ).writeAsStringSync(
            '#![no_std]\r\n// astral 🌍\r\npub fn résumé() -> u32 { 1 }\r\npub fn invoke() -> u32 { résumé() }\r\n',
          );
          // Explicit non-Cargo model also verifies that executable fields from a
          // rust-project.json cannot enable code execution.
          File(p.join(repo.path, 'rust-project.json')).writeAsStringSync('''
{"crates":[{"root_module":"rust/src/lib.rs","edition":"2021","deps":[]},
{"root_module":"rust/src/unicodé % file.rs","edition":"2021","deps":[],"proc_macro_dylib_path":"should-never-load"}],
"runnables":[{"program":"should-never-run"}]}
''');
          final report = await indexer.refresh();
          final refreshed = GraphQuery(report.snapshot, indexer.config);
          for (final language in ['python', 'rust']) {
            final file = language == 'python'
                ? 'python/unicodé % file.py'
                : 'rust/src/unicodé % file.rs';
            final target = '$file::résumé#function';
            expect(
              targetIds(
                refreshed.relations(
                  '$file::invoke#function',
                  direction: 'out',
                  kinds: {'calls'},
                ),
              ),
              contains(target),
            );
            expect(
              refreshed.snippet(target: target)['text'],
              contains('résumé'),
            );
          }
        },
      );

      test(
        'Cargo default features select the resolved active declaration',
        () async {
          final manifest = File(p.join(repo.path, 'rust/Cargo.toml'));
          manifest.writeAsStringSync(
            '${manifest.readAsStringSync()}\n[features]\ndefault = []\n',
          );
          final source = File(p.join(repo.path, 'rust/src/lib.rs'));
          source.writeAsStringSync(
            '${source.readAsStringSync()}\n'
            r'''
#[cfg(feature = "default")]
pub fn selected() -> u32 { 1 }
#[cfg(not(feature = "default"))]
pub fn selected() -> u32 { 2 }
pub fn choose() -> u32 { selected() }
''',
          );
          final report = await indexer.refresh();
          final refreshed = GraphQuery(report.snapshot, indexer.config);
          expect(
            targetIds(
              refreshed.relations(
                'rust/src/lib.rs::choose#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            contains('rust/src/lib.rs::selected#function'),
          );
        },
      );

      test('local Cargo path dependencies resolve across crate boundaries', () async {
        final dependency = Directory(p.join(repo.path, 'rust/dependency/src'))
          ..createSync(recursive: true);
        File(p.join(dependency.parent.path, 'Cargo.toml')).writeAsStringSync(
          '[package]\nname="domain_dependency"\nversion="0.1.0"\nedition="2021"\n',
        );
        File(
          p.join(dependency.path, 'lib.rs'),
        ).writeAsStringSync('pub fn shared() -> u32 { 7 }\n');
        final manifest = File(p.join(repo.path, 'rust/Cargo.toml'));
        manifest.writeAsStringSync(
          '${manifest.readAsStringSync()}\n[dependencies]\nrenamed = { package="domain_dependency", path="dependency" }\n',
        );
        final root = File(p.join(repo.path, 'rust/src/lib.rs'));
        root.writeAsStringSync(
          '${root.readAsStringSync()}\npub fn external_load() -> u32 { renamed::shared() }\n',
        );
        final report = await indexer.refresh();
        final refreshed = GraphQuery(report.snapshot, indexer.config);
        expect(
          targetIds(
            refreshed.relations(
              'rust/src/lib.rs::external_load#function',
              direction: 'out',
              kinds: {'calls'},
            ),
          ),
          contains('rust/dependency/src/lib.rs::shared#function'),
        );
        expect(
          targetIds(refreshed.dependencies('rust/src/lib.rs')),
          contains('rust/dependency/src/lib.rs'),
        );
      });
    },
    skip: available
        ? false
        : 'Prepare Python/Rust with dart run tool/setup_providers.dart --python --rust',
    timeout: const Timeout(Duration(minutes: 3)),
  );

  test(
    'missing Python/Rust runtimes preserve files with coverage errors',
    () async {
      final root = Directory.systemTemp.createTempSync(
        'polycodegraph missing semantic ',
      );
      addTearDown(() => root.deleteSync(recursive: true));
      File(
        p.join(root.path, 'app.py'),
      ).writeAsStringSync('def load(): return 1\n');
      File(
        p.join(root.path, 'app.rs'),
      ).writeAsStringSync('pub fn load() -> u32 { 1 }\n');
      final report = await RepositoryIndexer(
        GraphConfig(
          root: root.path,
          providersPath: providers,
          pythonPath: p.join(root.path, 'missing-python'),
          rustAnalyzerPath: p.join(root.path, 'missing-rust-analyzer'),
        ),
      ).refresh();
      for (final file in report.snapshot.files.values) {
        expect(file.nodes.single.kind, 'file');
        expect(file.diagnostics.single['code'], 'provider_unavailable');
      }
    },
  );
}
