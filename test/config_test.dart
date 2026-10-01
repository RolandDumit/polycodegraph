import 'dart:io';
import 'package:dart_codegraph/dart_codegraph.dart';
import 'package:path/path.dart' as p;
import 'package:test/test.dart';

void main() {
  late Directory root;
  setUp(() => root = Directory.systemTemp.createTempSync('graph-config-'));
  tearDown(() => root.deleteSync(recursive: true));
  test('YAML and JSON validate types and unknown keys', () {
    final file = File(p.join(root.path, 'dart-codegraph.yaml'));
    file.writeAsStringSync(
      'flutter: false\ninclude: ["lib/**.dart"]\nmax_results: 7\n',
    );
    final config = GraphConfig.load(root.path);
    expect(config.flutter, isFalse);
    expect(config.maxResults, 7);
    file.writeAsStringSync('flutter: "false"');
    expect(() => GraphConfig.load(root.path), throwsFormatException);
    file.writeAsStringSync('unknown: 1');
    expect(() => GraphConfig.load(root.path), throwsFormatException);
    file.deleteSync();
    File(
      p.join(root.path, 'dart-codegraph.json'),
    ).writeAsStringSync('{"max_snippet_chars":100}');
    expect(GraphConfig.load(root.path).maxSnippetChars, 100);
  });
  test('paths cannot escape repository or follow symlinks', () {
    final config = GraphConfig(root: root.path);
    expect(() => config.safePath('../outside'), throwsFormatException);
    expect(() => config.safePath('/etc/passwd'), throwsFormatException);
    expect(
      () => GraphConfig(root: root.path, cache: '../outside'),
      throwsFormatException,
    );
    Link(p.join(root.path, 'linked')).createSync('/tmp');
    expect(() => config.safePath('linked/secret'), throwsFormatException);
    expect(
      () => GraphConfig(root: root.path, cache: 'linked/cache').cachePath,
      throwsFormatException,
    );
  });
}
