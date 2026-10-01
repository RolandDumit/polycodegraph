import 'dart:convert';
import 'dart:io';
import 'package:analyzer/dart/analysis/analysis_context_collection.dart';
import 'package:analyzer/dart/analysis/results.dart';
import 'package:path/path.dart' as p;
import 'package:polycodegraph_dart_provider/src/analysis/extractor.dart';
import 'package:polycodegraph_dart_provider/src/config.dart';
import 'package:test/test.dart';

void main() {
  test(
    'generic substitution, accessors and operators retain semantic identities',
    () async {
      final root = Directory.systemTemp.createTempSync(
        'Analyzer alias spaces ',
      );
      addTearDown(() => root.deleteSync(recursive: true));
      Directory(p.join(root.path, 'lib')).createSync();
      Directory(p.join(root.path, '.dart_tool')).createSync();
      File(
        p.join(root.path, '.dart_tool/package_config.json'),
      ).writeAsStringSync(
        jsonEncode({
          'configVersion': 2,
          'packages': [
            {
              'name': 'fixture',
              'rootUri': '../',
              'packageUri': 'lib/',
              'languageVersion': '3.11',
            },
          ],
        }),
      );
      File(p.join(root.path, 'lib/shared.dart')).writeAsStringSync('''
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
      File(p.join(root.path, 'lib/consumer.dart')).writeAsStringSync('''
import 'package:fixture/shared.dart' as shared;
int consume(shared.Box<int> box) {
  box.current = box.read();
  final combined = shared.Vec(box.current) + shared.Vec(1);
  final negative = -combined;
  final difference = combined - negative;
  final id = shared.UserId(difference.value);
  return id.value;
}
''');
      final config = GraphConfig(root: root.path);
      final contexts = AnalysisContextCollection(includedPaths: [config.root]);
      try {
        final path = config.safePath('lib/consumer.dart');
        final unit =
            await contexts.contextFor(path).currentSession.getResolvedUnit(path)
                as ResolvedUnitResult;
        final record = extract(unit, config, 'hash');
        expect(
          record.diagnostics.where((d) => d['severity'] == 'error'),
          isEmpty,
        );
        expect(
          record.edges.where((e) => e.kind == 'calls').map((e) => e.target),
          containsAll([
            'lib/shared.dart::Box.read#method',
            'lib/shared.dart::Box.current#getter',
            'lib/shared.dart::Box.current#setter',
            'lib/shared.dart::Vec.+#method',
            'lib/shared.dart::Vec.-#method',
            'lib/shared.dart::Vec.unary-#method',
            'lib/shared.dart::UserId.new#constructor',
          ]),
        );
        expect(record.dependencies, contains('lib/shared.dart'));
      } finally {
        await contexts.dispose();
      }
    },
  );
  test('conditional imports retain inactive local dependencies', () async {
    final root = Directory.systemTemp.createTempSync('Analyzer conditionals ');
    addTearDown(() => root.deleteSync(recursive: true));
    for (final name in ['fallback', 'native']) {
      File(
        p.join(root.path, '$name.dart'),
      ).writeAsStringSync('String platform() => "$name";');
    }
    File(p.join(root.path, 'platform.dart')).writeAsStringSync(
      "import 'fallback.dart' if (dart.library.io) 'native.dart'; String platformName() => platform();",
    );
    final config = GraphConfig(root: root.path);
    final contexts = AnalysisContextCollection(includedPaths: [config.root]);
    try {
      final path = config.safePath('platform.dart');
      final unit =
          await contexts.contextFor(path).currentSession.getResolvedUnit(path)
              as ResolvedUnitResult;
      expect(
        extract(unit, config, 'hash').dependencies,
        containsAll(['fallback.dart', 'native.dart']),
      );
    } finally {
      await contexts.dispose();
    }
  });
}
