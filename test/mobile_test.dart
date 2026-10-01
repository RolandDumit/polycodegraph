import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as p;
import 'package:polycodegraph/polycodegraph.dart';
import 'package:test/test.dart';
import 'support.dart';

void main() {
  final providers = Directory('providers').absolute.path;
  GraphConfig config(String root) => GraphConfig(
    root: root,
    providersPath: providers,
    javaPath: Platform.environment['JAVA'] ?? 'java',
    swiftcPath: Platform.environment['SWIFTC'] ?? 'swiftc',
  );
  final health = ExternalProviders(config('.')).doctor();
  final available = [
    'swift',
    'kotlin',
    'objectivec',
  ].every((key) => (health[key] as Map)['available'] == true);
  if (Platform.environment['POLYCODEGRAPH_REQUIRE_MOBILE'] == '1' &&
      !available) {
    throw StateError('Required mobile providers unavailable: $health');
  }
  group(
    'mobile semantic providers',
    () {
      late Directory repo;
      late RepositoryIndexer indexer;
      late GraphQuery graph;
      setUp(() async {
        repo = Directory.systemTemp.createTempSync(
          'polycodegraph mobile spaces % ',
        );
        copyTree(Directory('test/fixtures/mobile'), repo);
        indexer = RepositoryIndexer(config(repo.path));
        graph = GraphQuery((await indexer.refresh()).snapshot, indexer.config);
      });
      tearDown(() => repo.deleteSync(recursive: true));
      GraphNode find(
        String name,
        String language, {
        String? file,
        String? kind,
      }) => graph.nodes.values.singleWhere(
        (node) =>
            node.name == name &&
            languageFor(node.file) == language &&
            (file == null || node.file == file) &&
            (kind == null || node.kind == kind),
      );
      Set<String> callees(String target) =>
          (graph.relations(target, direction: 'out', kinds: {'calls'})['rows']
                  as List)
              .map((row) => row[0] as String)
              .toSet();
      test('symbols, calls and decoys use compiler identities', () {
        final errors = graph.snapshot.files.values
            .expand((f) => f.diagnostics)
            .where((d) => d['severity'] == 'error')
            .toList();
        expect(errors, isEmpty, reason: '$errors');
        expect(File(p.join(repo.path, 'SWIFTPM_RAN')).existsSync(), isFalse);
        expect(File(p.join(repo.path, 'GRADLE_RAN')).existsSync(), isFalse);
        for (final language in ['swift', 'kotlin', 'objectivec']) {
          final extension = language == 'swift'
              ? 'swift'
              : language == 'kotlin'
              ? 'kt'
              : 'm';
          final load = find('load', language, file: '$language/Use.$extension');
          final calls = callees(load.id);
          expect(calls.length, 1, reason: '$language: $calls');
          final contract = graph.nodes[calls.single]!;
          expect(
            contract.parent,
            find('Repository', language, kind: 'interface').id,
          );
          expect(calls.any((id) => id.contains('Unrelated')), isFalse);
          expect(
            graph.snippet(target: load.id)['text'],
            contains(
              language == 'objectivec'
                  ? '[repository fetch]'
                  : 'repository.fetch()',
            ),
          );
        }
        expect(
          graph.search(
            'overloaded',
            language: 'kotlin',
            kind: 'method',
          )['total'],
          2,
        );
        expect(
          graph.search(
            'loadAsync',
            language: 'kotlin',
            tag: 'suspend',
          )['total'],
          1,
        );
        expect(
          graph.search('Record', language: 'kotlin', tag: 'data')['total'],
          1,
        );
        expect(
          graph.search('State', language: 'swift', kind: 'enum')['total'],
          1,
        );
        expect(
          graph.search('Label', language: 'swift', kind: 'typedef')['total'],
          1,
        );
        expect(
          graph.snapshot.files['kotlin/Use.kt']!.unresolvedCalls,
          greaterThan(0),
        );
        expect(
          graph.snapshot.files['swift/Use.swift']!.unresolvedCalls,
          greaterThan(0),
        );
        final inherited = find('inherited', 'kotlin');
        final child = graph.nodes.values.singleWhere(
          (n) =>
              n.file == 'swift/Domain.swift' &&
              n.qualifiedName == 'ChildRepository.fetch()',
        );
        expect(
          graph.relations(
            child.id,
            direction: 'out',
            kinds: {'overrides'},
          )['total'],
          1,
        );
        final cpp = find('objcPlusCpp', 'objectivec');
        expect(callees(cpp.id).length, 2);
        expect(
          callees(cpp.id).any((id) => id.contains('detail.Counter.add(int)')),
          isTrue,
        );
        expect(
          callees(inherited.id).single,
          contains('MemoryRepository.fetch'),
        );
      });
      test(
        'implementations, references, dependencies and impact cross files',
        () {
          for (final language in ['swift', 'kotlin', 'objectivec']) {
            final contract = find('Repository', language, kind: 'interface');
            expect(graph.implementations(contract.id)['total'], greaterThan(0));
            expect(
              graph.relations(contract.id, direction: 'both')['total'],
              greaterThan(0),
            );
            final suffix = language == 'swift'
                ? 'swift'
                : language == 'kotlin'
                ? 'kt'
                : 'm';
            final load = find('load', language, file: '$language/Use.$suffix');
            expect(
              graph.dependencies('$language/Use.$suffix')['total'],
              greaterThan(0),
            );
            final impact = graph.affected(contract.id, depth: 6);
            expect(
              (impact['rows'] as List).any((row) => row[0] == load.id),
              isTrue,
              reason: '$language: $impact',
            );
          }
        },
      );
      test(
        'leading comments preserve symbol identities and warm caches reuse records',
        () async {
          final before = graph.nodes.keys.toSet();
          final warm = await indexer.refresh();
          expect(warm.reindexed, isEmpty);
          for (final source in [
            'swift/Domain.swift',
            'kotlin/Domain.kt',
            'objectivec/Domain.h',
          ]) {
            final file = File(p.join(repo.path, source));
            file.writeAsStringSync(
              '// leading comment\n${file.readAsStringSync()}',
            );
          }
          final report = await indexer.refresh();
          expect(
            report.reindexed,
            containsAll([
              'swift/Use.swift',
              'kotlin/Use.kt',
              'objectivec/Use.m',
            ]),
          );
          graph = GraphQuery(report.snapshot, indexer.config);
          expect(graph.nodes.keys.toSet(), before);
        },
      );
      test(
        'contract renames invalidate unchanged consumers without guessed bindings',
        () async {
          for (final source in [
            'swift/Domain.swift',
            'kotlin/Domain.kt',
            'objectivec/Domain.h',
          ]) {
            final file = File(p.join(repo.path, source));
            file.writeAsStringSync(
              file.readAsStringSync().replaceAll('fetch', 'fetchRenamed'),
            );
          }
          final report = await indexer.refresh();
          graph = GraphQuery(report.snapshot, indexer.config);
          for (final language in ['swift', 'kotlin', 'objectivec']) {
            final suffix = language == 'swift'
                ? 'swift'
                : language == 'kotlin'
                ? 'kt'
                : 'm';
            final record = report.snapshot.files['$language/Use.$suffix']!;
            expect(
              record.edges.where(
                (e) =>
                    e.kind == 'calls' &&
                    e.target.contains('Repository.') &&
                    e.target.contains('fetch'),
              ),
              isEmpty,
            );
            expect(report.reindexed, contains('$language/Use.$suffix'));
            expect(
              record.diagnostics.any((d) => d['severity'] == 'error'),
              isTrue,
            );
          }
        },
      );
      test('UTF-8 UTF-16 and CRLF preserve calls and snippets', () async {
        for (final file
            in repo
                .listSync(recursive: true)
                .whereType<File>()
                .where(
                  (f) => [
                    '.swift',
                    '.kt',
                    '.h',
                    '.m',
                  ].contains(p.extension(f.path)),
                )) {
          file.writeAsStringSync(
            '// emoji 🦀 café\r\n${file.readAsStringSync().replaceAll('\n', '\r\n')}',
          );
        }
        graph = GraphQuery((await indexer.refresh()).snapshot, indexer.config);
        for (final language in ['swift', 'kotlin', 'objectivec']) {
          final suffix = language == 'swift'
              ? 'swift'
              : language == 'kotlin'
              ? 'kt'
              : 'm';
          final load = find('load', language, file: '$language/Use.$suffix');
          expect(callees(load.id).length, 1);
          expect(graph.snippet(target: load.id)['text'], contains('fetch'));
        }
      });
      test(
        'read-only module model invalidates bindings and rejects executable fields',
        () async {
          final model = File(p.join(repo.path, 'polycodegraph.mobile.json'));
          model.writeAsStringSync(
            jsonEncode({
              for (final lang in ['swift', 'kotlin', 'objectivec'])
                lang: [
                  {
                    'name': 'Fixture',
                    'files': ['$lang/*'],
                  },
                ],
            }),
          );
          final updated = await indexer.refresh();
          expect(updated.reindexed, contains('swift/Use.swift'));
          model.writeAsStringSync(
            jsonEncode({
              'kotlin': [
                {
                  'name': 'Fixture',
                  'files': ['kotlin/*'],
                  'compiler_plugins': ['untrusted.jar'],
                },
              ],
            }),
          );
          final rejected = await indexer.refresh();
          expect(
            rejected.snapshot.files['kotlin/Use.kt']!.diagnostics.any(
              (d) => d['code'] == 'provider_unavailable',
            ),
            isTrue,
          );
        },
      );
    },
    timeout: const Timeout(Duration(minutes: 3)),
    skip: available
        ? false
        : 'Prepare mobile providers with --swift --kotlin --objectivec',
  );
  test(
    'missing mobile runtimes retain file nodes with explicit coverage errors',
    () async {
      final repo = Directory.systemTemp.createTempSync(
        'polycodegraph missing mobile ',
      );
      addTearDown(() => repo.deleteSync(recursive: true));
      File(p.join(repo.path, 'Demo.swift')).writeAsStringSync('class Demo {}');
      File(p.join(repo.path, 'Demo.kt')).writeAsStringSync('class Demo');
      File(
        p.join(repo.path, 'Demo.m'),
      ).writeAsStringSync('@interface Demo @end');
      final report = await RepositoryIndexer(
        GraphConfig(
          root: repo.path,
          providersPath: providers,
          pythonPath: p.join(repo.path, 'missing-python'),
        ),
      ).refresh();
      expect(report.snapshot.files.length, 3);
      for (final file in report.snapshot.files.values) {
        expect(file.nodes.single.kind, 'file');
        expect(file.diagnostics.single['code'], 'provider_unavailable');
      }
    },
  );
}
