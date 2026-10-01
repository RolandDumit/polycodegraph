import 'dart:convert';
import 'dart:io';
import 'package:polycodegraph/polycodegraph.dart';
import 'package:path/path.dart' as p;
import 'package:test/test.dart';
import 'support.dart';

void main() {
  late Directory repo;
  late RepositoryIndexer indexer;
  setUp(() {
    repo = fixtureCopy();
    indexer = RepositoryIndexer(GraphConfig(root: repo.path));
  });
  tearDown(() => repo.deleteSync(recursive: true));
  test('warm disk cache avoids resolution and keeps generation', () async {
    final first = await indexer.refresh();
    final second = await RepositoryIndexer(indexer.config).refresh();
    expect(first.full, isTrue);
    expect(second.reindexed, isEmpty);
    expect(second.snapshot.generation, first.snapshot.generation);
  });
  test(
    'changed file and transitive importers refresh; unrelated file reuses cache',
    () async {
      final first = await indexer.refresh();
      final source = File(p.join(repo.path, 'lib/domain.dart'));
      source.writeAsStringSync(
        '// inserted comment\n${source.readAsStringSync()}',
      );
      expect(indexer.detectChanges()['changed'], ['lib/domain.dart']);
      final second = await indexer.refresh();
      expect(second.full, isFalse);
      expect(
        second.reindexed,
        containsAll(['lib/domain.dart', 'lib/model.dart', 'lib/use_case.dart']),
      );
      expect(second.reindexed, isNot(contains('lib/unused.dart')));
      expect(second.snapshot.generation, isNot(first.snapshot.generation));
      final old = GraphQuery(
        first.snapshot,
        indexer.config,
      ).resolve('MemoryRepository');
      final next = GraphQuery(
        second.snapshot,
        indexer.config,
      ).resolve('MemoryRepository');
      expect(next.id, old.id);
      expect(next.line, old.line + 1);
      expect(
        () => GraphQuery(
          first.snapshot,
          indexer.config,
        ).snippet(target: 'MemoryRepository'),
        throwsA(isA<QueryException>()),
      );
    },
  );
  test(
    'renaming, additions and deletions remove stale nodes and edges',
    () async {
      await indexer.refresh();
      final source = File(p.join(repo.path, 'lib/unused.dart'));
      source.writeAsStringSync('String renamed() => "value";\n');
      final second = await indexer.refresh();
      expect(
        GraphQuery(second.snapshot, indexer.config).search('unused')['total'],
        0,
      );
      File(
        p.join(repo.path, 'lib/added.dart'),
      ).writeAsStringSync('class Added {}');
      expect((await indexer.refresh()).full, isTrue);
      source.deleteSync();
      final finalReport = await indexer.refresh();
      expect(finalReport.deleted, ['lib/unused.dart']);
      expect(finalReport.snapshot.files, isNot(contains('lib/unused.dart')));
    },
  );
  test('semantic change rebinds calls in unchanged consumers', () async {
    await indexer.refresh();
    final source = File(p.join(repo.path, 'lib/domain.dart'));
    source.writeAsStringSync(
      source.readAsStringSync().replaceAll(
        'String fetch()',
        'String retrieve()',
      ),
    );
    final report = await indexer.refresh();
    final graph = GraphQuery(report.snapshot, indexer.config);
    expect(graph.search('fetch', file: 'lib/domain.dart')['total'], 0);
    final callers = graph.relations(
      'UserRepository.retrieve',
      direction: 'in',
      kinds: {'calls'},
    );
    expect(callers['total'], 0);
    expect(report.snapshot.files['lib/use_case.dart']!.diagnostics, isNotEmpty);
  });
  test('pubspec/options changes rebuild all; corrupt cache recovers', () async {
    await indexer.refresh();
    File(
      p.join(repo.path, 'analysis_options.yaml'),
    ).writeAsStringSync('analyzer:\n  errors:\n    unused_import: ignore\n');
    expect((await indexer.refresh()).reindexed, hasLength(4));
    File(
      p.join(repo.path, '.polycodegraph/index.json'),
    ).writeAsStringSync('{broken');
    expect((await indexer.refresh()).full, isTrue);
    final jsonFile = File(p.join(repo.path, '.polycodegraph/index.json'));
    final cache = jsonDecode(jsonFile.readAsStringSync()) as Map;
    cache['schema'] = 999;
    jsonFile.writeAsStringSync(jsonEncode(cache));
    expect((await indexer.refresh()).full, isTrue);
  });
  test('excluded generated dependency changes still invalidate index', () async {
    final config = GraphConfig(root: repo.path, exclude: ['**/model.dart']);
    final scoped = RepositoryIndexer(config);
    await scoped.refresh();
    File(p.join(repo.path, 'lib/model.dart')).writeAsStringSync(
      "part of 'domain.dart'; class User { User(this.name); final String name; String changed() => name; }",
    );
    final report = await scoped.refresh();
    expect(report.full, isTrue);
    expect(report.snapshot.files, isNot(contains('lib/model.dart')));
  });
  test('symlinks and oversized sources are skipped and reported', () async {
    final outside = File(p.join(repo.path, 'outside.txt'))
      ..writeAsStringSync('class Secret {}');
    Link(p.join(repo.path, 'lib/link.dart')).createSync(outside.path);
    File(p.join(repo.path, 'lib/huge.dart')).writeAsStringSync('x' * 2200000);
    final report = await indexer.refresh();
    expect(
      report.snapshot.skipped,
      containsAll(['lib/link.dart', 'lib/huge.dart']),
    );
  });
  test(
    'explicit graph includes remain analyzable when analysis_options excludes them',
    () async {
      File(
        p.join(repo.path, 'analysis_options.yaml'),
      ).writeAsStringSync('analyzer:\n  exclude:\n    - lib/unused.dart\n');
      final report = await indexer.refresh();
      expect(
        GraphQuery(report.snapshot, indexer.config).search('unused')['total'],
        1,
      );
    },
  );
  test('concurrent refresh calls serialize', () async {
    final reports = await Future.wait([
      indexer.refresh(),
      RepositoryIndexer(indexer.config).refresh(),
    ]);
    expect(reports.first.reindexed, hasLength(4));
    expect(reports.last.reindexed, isEmpty);
  });
}
