import 'dart:convert';
import 'dart:io';
import 'package:polycodegraph/polycodegraph.dart';
import 'package:path/path.dart' as p;
import 'package:test/test.dart';
import 'support.dart';

void main() {
  test(
    'package aliases, generic substitution, accessors, operators and extension type constructors resolve',
    () async {
      final repo = fixtureCopy();
      addTearDown(() => repo.deleteSync(recursive: true));
      Directory(p.join(repo.path, '.dart_tool')).createSync();
      File(
        p.join(repo.path, '.dart_tool/package_config.json'),
      ).writeAsStringSync(
        jsonEncode({
          'configVersion': 2,
          'packages': [
            {
              'name': 'graph_fixture',
              'rootUri': '../',
              'packageUri': 'lib/',
              'languageVersion': '3.11',
            },
          ],
        }),
      );
      File(p.join(repo.path, 'lib/shared.dart')).writeAsStringSync('''
class Box<T> {
  Box(this.value);
  T value;
  T read() => value;
  T get current => value;
  set current(T next) { value = next; }
}
class Vec {
  Vec(this.value);
  final int value;
  Vec operator +(Vec other) => Vec(value + other.value);
  Vec operator -(Vec other) => Vec(value - other.value);
  Vec operator -() => Vec(-value);
}
extension type UserId(int value) {}
''');
      File(p.join(repo.path, 'lib/consumer.dart')).writeAsStringSync('''
import 'package:graph_fixture/shared.dart' as shared;
int consume(shared.Box<int> box) {
  box.current = box.read();
  final combined = shared.Vec(box.current) + shared.Vec(1);
  final negative = -combined;
  final difference = combined - negative;
  final id = shared.UserId(difference.value);
  return id.value;
}
''');
      final indexer = RepositoryIndexer(GraphConfig(root: repo.path));
      final graph = GraphQuery(
        (await indexer.refresh()).snapshot,
        indexer.config,
      );
      expect(
        graph.snapshot.files.values
            .expand((r) => r.diagnostics)
            .where((d) => d['severity'] == 'error'),
        isEmpty,
      );
      final calls =
          graph.relations('consume', direction: 'out', kinds: {'calls'})['rows']
              as List;
      final ids = calls.map((r) => r[0]);
      expect(
        ids,
        containsAll([
          graph.resolve('Box.read').id,
          'lib/shared.dart::Box.current#getter',
          'lib/shared.dart::Box.current#setter',
          graph.resolve('Vec.+').id,
          'lib/shared.dart::Vec.-#method',
          'lib/shared.dart::Vec.unary-#method',
          'lib/shared.dart::UserId.new#constructor',
        ]),
      );
      expect(
        graph.resolve('lib/shared.dart::UserId.new#constructor').synthetic,
        isFalse,
      );
      expect(graph.search('value', file: 'lib/shared.dart')['total'], 3);
      final deps =
          graph.relations(
                'lib/consumer.dart',
                direction: 'out',
                kinds: {'imports'},
              )['rows']
              as List;
      expect(deps.map((r) => r[0]), ['lib/shared.dart::file']);
      final shared = File(p.join(repo.path, 'lib/shared.dart'));
      shared.writeAsStringSync(
        shared.readAsStringSync().replaceAll('T read()', 'T renamed()'),
      );
      final updated = await indexer.refresh();
      expect(updated.reindexed, contains('lib/consumer.dart'));
      expect(
        GraphQuery(
          updated.snapshot,
          indexer.config,
        ).search('Box.read')['total'],
        0,
      );
    },
  );
  test('conditional imports track inactive local alternatives', () async {
    final repo = fixtureCopy();
    addTearDown(() => repo.deleteSync(recursive: true));
    for (final name in ['fallback', 'native']) {
      File(
        p.join(repo.path, 'lib/$name.dart'),
      ).writeAsStringSync('String platform() => "$name";');
    }
    File(p.join(repo.path, 'lib/platform.dart')).writeAsStringSync(
      "import 'fallback.dart' if (dart.library.io) 'native.dart'; String platformName() => platform();",
    );
    final indexer = RepositoryIndexer(GraphConfig(root: repo.path));
    final report = await indexer.refresh();
    expect(
      report.snapshot.files['lib/platform.dart']!.dependencies,
      containsAll(['lib/fallback.dart', 'lib/native.dart']),
    );
    File(
      p.join(repo.path, 'lib/fallback.dart'),
    ).writeAsStringSync('String platform() => "changed";');
    expect((await indexer.refresh()).reindexed, contains('lib/platform.dart'));
  });
}
