import 'dart:convert';
import 'dart:io';
import 'package:args/args.dart';
import 'package:dart_codegraph/dart_codegraph.dart';
import 'package:path/path.dart' as p;

Future<void> main(List<String> args) async {
  final parser = ArgParser()
    ..addOption('root', defaultsTo: '.', help: 'Dart/Flutter repository root')
    ..addOption('config', help: 'YAML or JSON config path')
    ..addFlag('force', negatable: false, help: 'Rebuild all files')
    ..addFlag('help', abbr: 'h', negatable: false)
    ..addFlag('version', negatable: false);
  try {
    final options = parser.parse(args);
    if (options['version'] == true) {
      stdout.writeln('dart-codegraph 0.1.0');
      return;
    }
    if (options['help'] == true || options.rest.isEmpty) {
      stdout.writeln(
        'dart-codegraph <init|index|serve|status> [options]\n${parser.usage}',
      );
      return;
    }
    if (options.rest.length != 1 ||
        !{'init', 'index', 'serve', 'status'}.contains(options.rest.single)) {
      throw FormatException('Expected init, index, serve, or status');
    }
    final command = options.rest.single;
    final config = GraphConfig.load(
      options['root'] as String,
      configPath: options['config'] as String?,
    );
    if (command == 'init') {
      final file = File(config.safePath('dart-codegraph.yaml'));
      if (file.existsSync() ||
          [
            'dart-codegraph.yml',
            'dart-codegraph.json',
          ].any((n) => File(p.join(config.root, n)).existsSync())) {
        throw FormatException('Configuration already exists');
      }
      await file.writeAsString(
        '''# Repository-relative globs; generated Dart sources are included by default.
include:
  - "**/*.dart"
exclude:
  - "**/.git/**"
  - "**/.dart_tool/**"
  - "**/build/**"
  - "**/.dart-codegraph/**"
cache: .dart-codegraph
flutter: true
max_results: 200
max_snippet_lines: 120
max_snippet_chars: 16000
max_file_bytes: 2097152
# sdk_path: /absolute/path/to/flutter/bin/cache/dart-sdk
''',
      );
      stdout.writeln(jsonEncode({'created': 'dart-codegraph.yaml'}));
      return;
    }
    final indexer = RepositoryIndexer(config);
    if (command == 'serve') {
      // Lazy indexing lets MCP initialize immediately on large repositories.
      await McpServer(indexer).serve();
      return;
    }
    if (command == 'index') {
      stdout.writeln(
        jsonEncode(
          (await indexer.refresh(force: options['force'] as bool)).toJson(),
        ),
      );
      return;
    }
    final current = indexer.load();
    stdout.writeln(
      jsonEncode({
        'indexed': current != null,
        'changes': indexer.detectChanges(),
        if (current != null)
          ...GraphQuery(current, config).architecture(limit: 5),
      }),
    );
  } on FormatException catch (e) {
    stderr.writeln('dart-codegraph: ${e.message}');
    exitCode = 64;
  } on FileSystemException catch (e) {
    stderr.writeln('dart-codegraph: ${e.message} (${e.path})');
    exitCode = 74;
  } catch (e, stack) {
    stderr.writeln('dart-codegraph: $e\n$stack');
    exitCode = 1;
  }
}
