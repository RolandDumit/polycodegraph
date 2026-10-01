import 'dart:io';
import 'package:polycodegraph/polycodegraph.dart';
import 'package:path/path.dart' as p;
import 'package:test/test.dart';

void main() {
  late Directory root;
  setUp(() => root = Directory.systemTemp.createTempSync('graph-config-'));
  tearDown(() => root.deleteSync(recursive: true));
  test('YAML and JSON validate types and unknown keys', () {
    final file = File(p.join(root.path, 'polycodegraph.yaml'));
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
      p.join(root.path, 'polycodegraph.json'),
    ).writeAsStringSync('{"max_snippet_chars":100}');
    expect(GraphConfig.load(root.path).maxSnippetChars, 100);
  });
  test('semantic runtime paths and list options validate consistently', () {
    final file = File(p.join(root.path, 'polycodegraph.json'));
    file.writeAsStringSync(
      r'''{"python_path":"tools/python","rust_analyzer_path":"tools/rust-analyzer.exe","python_search_paths":["src"],"rust_cfg":["feature=\"offline\""],"rust_sysroot_src":"sdk/library","swiftc_path":"tools/swiftc","libclang_path":"tools/libclang.so","mobile_project_path":"models/mobile.json"}''',
    );
    final config = GraphConfig.load(root.path);
    expect(config.pythonPath, p.join(root.path, 'tools', 'python'));
    expect(
      config.rustAnalyzerPath,
      p.join(root.path, 'tools', 'rust-analyzer.exe'),
    );
    expect(config.pythonSearchPaths, [p.join(root.path, 'src')]);
    expect(config.rustCfg, ['feature="offline"']);
    expect(config.rustSysrootSrc, p.join(root.path, 'sdk', 'library'));
    expect(config.swiftcPath, p.join(root.path, 'tools', 'swiftc'));
    expect(config.libclangPath, p.join(root.path, 'tools', 'libclang.so'));
    expect(config.mobileProjectPath, 'models/mobile.json');
    for (final invalid in [
      '{"python_path":42}',
      '{"rust_analyzer_path":false}',
      '{"python_search_paths":[1]}',
      '{"rust_cfg":"offline"}',
      '{"rust_sysroot_src":[]}',
      '{"swiftc_path":42}',
      '{"libclang_path":false}',
      '{"mobile_project_path":"../outside.json"}',
    ]) {
      file.writeAsStringSync(invalid);
      expect(() => GraphConfig.load(root.path), throwsFormatException);
    }
  });
  test(
    'mobile models in excluded asset directories still invalidate cache',
    () async {
      File(p.join(root.path, 'main.dart')).writeAsStringSync('class Demo {}');
      final hidden = Directory(p.join(root.path, '.tools'))..createSync();
      final model = File(p.join(hidden.path, 'mobile.json'))
        ..writeAsStringSync('{}');
      final config = GraphConfig(
        root: root.path,
        mobileProjectPath: '.tools/mobile.json',
      );
      final indexer = RepositoryIndexer(config);
      final first = await indexer.refresh();
      expect((await indexer.refresh()).reindexed, isEmpty);
      model.writeAsStringSync('{ }');
      final second = await indexer.refresh();
      expect(second.snapshot.generation, isNot(first.snapshot.generation));
      expect(second.reindexed, ['main.dart']);
    },
  );
  test('paths cannot escape repository or follow symlinks', () {
    final config = GraphConfig(root: root.path);
    expect(() => config.safePath('../outside'), throwsFormatException);
    expect(
      () => config.safePath(p.join(root.path, 'absolute.txt')),
      throwsFormatException,
    );
    expect(
      () => GraphConfig(root: root.path, cache: '../outside'),
      throwsFormatException,
    );
    final outside = Directory.systemTemp.createTempSync('graph-outside-');
    addTearDown(() => outside.deleteSync(recursive: true));
    Link(p.join(root.path, 'linked')).createSync(outside.path);
    expect(() => config.safePath('linked/secret'), throwsFormatException);
    expect(
      () => GraphConfig(root: root.path, cache: 'linked/cache').cachePath,
      throwsFormatException,
    );
  });
}
