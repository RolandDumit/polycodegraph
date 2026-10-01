import 'dart:io';
import 'package:polycodegraph/polycodegraph.dart';
import 'package:test/test.dart';
import 'support.dart';

List<List<dynamic>> rows(Map<String, dynamic> response) =>
    (response['rows'] as List).cast<List<dynamic>>();
void main() {
  late Directory repo;
  late RepositoryIndexer indexer;
  late GraphQuery graph;
  setUpAll(() async {
    repo = fixtureCopy();
    indexer = RepositoryIndexer(GraphConfig(root: repo.path));
    final report = await indexer.refresh();
    graph = GraphQuery(report.snapshot, indexer.config);
  });
  tearDownAll(() => repo.deleteSync(recursive: true));
  test('all required declarations and stable IDs including parts', () {
    final kinds = graph.nodes.values.map((n) => n.kind).toSet();
    expect(
      kinds,
      containsAll([
        'file',
        'class',
        'mixin',
        'enum',
        'extension',
        'typedef',
        'function',
        'method',
        'field',
        'constructor',
        'getter',
      ]),
    );
    expect(graph.resolve('User').file, 'lib/model.dart');
    expect(
      graph.resolve('MemoryRepository').id,
      'lib/domain.dart::MemoryRepository#class',
    );
    expect(graph.resolve('Unrelated.new').synthetic, isTrue);
    expect(graph.snapshot.files.values.expand((f) => f.diagnostics), isEmpty);
  });
  test(
    'calls distinguish interface dispatch, same names, getter and constructor',
    () {
      final callers = rows(
        graph.relations(
          'UserRepository.fetch',
          direction: 'in',
          kinds: {'calls'},
        ),
      );
      expect(
        callers.map((r) => r[0]),
        contains(graph.resolve('LoadUserUseCase.call').id),
      );
      expect(
        callers.map((r) => r[0]),
        isNot(contains(graph.resolve('decoy').id)),
      );
      final decoy = rows(
        graph.relations('decoy', direction: 'out', kinds: {'calls'}),
      ).map((r) => r[0]);
      expect(decoy, contains(graph.resolve('Unrelated.fetch').id));
      expect(decoy, isNot(contains(graph.resolve('UserRepository.fetch').id)));
      final run = rows(
        graph.relations('run', direction: 'out', kinds: {'calls'}),
      ).map((r) => r[0]);
      expect(
        run,
        containsAll([
          graph.resolve('UserLabel.label').id,
          graph.resolve('LoadUserUseCase.call').id,
        ]),
      );
      expect(
        rows(
          graph.relations('User.guest', direction: 'out', kinds: {'calls'}),
        ).single[0],
        graph.resolve('User.new').id,
      );
      expect(
        graph.snapshot.files['lib/use_case.dart']!.unresolvedCalls,
        greaterThan(0),
      );
    },
  );
  test('inheritance, implementations and method overrides are transitive', () {
    expect(
      rows(graph.implementations('UserRepository')).map((r) => r[2]),
      containsAll(['MemoryRepository', 'ChildRepository', 'AliasRepository']),
    );
    expect(
      rows(graph.implementations('UserRepository.fetch')).map((r) => r[0]),
      containsAll([
        graph.resolve('MemoryRepository.fetch').id,
        graph.resolve('ChildRepository.fetch').id,
      ]),
    );
    expect(
      rows(
        graph.relations('MemoryRepository', direction: 'out', kinds: {'with'}),
      ).single[0],
      graph.resolve('Logging').id,
    );
  });
  test('import export part and dependencies retained', () {
    expect(
      rows(
        graph.relations(
          'lib/use_case.dart',
          direction: 'out',
          kinds: {'imports', 'exports'},
        ),
      ).map((r) => r[6]),
      containsAll(['imports', 'exports']),
    );
    expect(
      rows(
        graph.relations('lib/domain.dart', direction: 'out', kinds: {'part'}),
      ).single[0],
      'lib/model.dart::file',
    );
    expect(
      rows(
        graph.relations('lib/model.dart', direction: 'out', kinds: {'part_of'}),
      ).single[0],
      'lib/domain.dart::file',
    );
    expect(
      rows(graph.dependencies('run')).map((r) => r[0]),
      containsAll(['lib/domain.dart', 'lib/model.dart']),
    );
  });
  test('references and conservative impact have reasons and depth limits', () {
    expect(
      rows(graph.relations('User', direction: 'in', kinds: {'references'})),
      isNotEmpty,
    );
    final affected = graph.affected('UserRepository.fetch', depth: 12);
    expect(rows(affected).map((r) => r[0]), contains(graph.resolve('run').id));
    expect(affected['affected_files'], contains('lib/use_case.dart'));
    expect(affected['affected_files'], isNot(contains('lib/unused.dart')));
    expect(graph.affected('UserRepository', depth: 1)['depth_limited'], isTrue);
    expect(
      rows(
        graph.affected('MemoryRepository.fetch', depth: 12),
      ).map((r) => r[0]),
      contains(graph.resolve('LoadUserUseCase.call').id),
    );
  });
  test('search ranking, ambiguity, tags and pagination are deterministic', () {
    final result = graph.search('fetch', limit: 2);
    expect(rows(result), hasLength(2));
    expect(result['next_offset'], 2);
    expect(graph.search('fetch', offset: 2)['rows'], isNotEmpty);
    expect(() => graph.resolve('fetch'), throwsA(isA<QueryException>()));
    expect(rows(graph.search('', tag: 'UseCase')).single[2], 'LoadUserUseCase');
    expect(graph.search('no such symbol')['total'], 0);
  });
  test('snippet bounds and source validation', () {
    final limited = GraphQuery(
      graph.snapshot,
      GraphConfig(root: repo.path, maxSnippetLines: 2, maxSnippetChars: 60),
    );
    final snippet = limited.snippet(target: 'MemoryRepository', context: 0);
    expect(snippet['truncated'], isTrue);
    expect((snippet['text'] as String).length, lessThanOrEqualTo(60));
    expect(
      () => graph.snippet(file: '../secret'),
      throwsA(isA<QueryException>()),
    );
    expect(
      () => graph.snippet(file: 'lib/domain.dart', startLine: 0),
      throwsA(isA<QueryException>()),
    );
  });
  test('architecture surfaces health without source', () {
    final architecture = graph.architecture(limit: 2);
    expect(architecture['files'], 4);
    expect(architecture['unresolved_calls'], greaterThan(0));
    expect(architecture['tags'], contains('Repository'));
    expect(architecture['diagnostics'], isEmpty);
    expect((architecture['hubs'] as Map)['rows'], hasLength(2));
  });
}
