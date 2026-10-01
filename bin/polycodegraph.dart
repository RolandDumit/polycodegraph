import 'dart:convert';
import 'dart:io';
import 'package:args/args.dart';
import 'package:polycodegraph/polycodegraph.dart';
import 'package:path/path.dart' as p;

Future<void> main(List<String> args) async {
  final parser = ArgParser()
    ..addOption('root', defaultsTo: '.', help: 'Repository root')
    ..addOption('config', help: 'YAML or JSON config path')
    ..addFlag('force', negatable: false, help: 'Rebuild all files')
    ..addFlag('help', abbr: 'h', negatable: false)
    ..addFlag('version', negatable: false);
  try {
    final options = parser.parse(args);
    if (options['version'] == true) {
      stdout.writeln('polycodegraph 0.4.0');
      return;
    }
    if (options['help'] == true || options.rest.isEmpty) {
      stdout.writeln(
        'polycodegraph <init|index|serve|status|doctor> [options]\n${parser.usage}',
      );
      return;
    }
    if (options.rest.length != 1 ||
        !{
          'init',
          'index',
          'serve',
          'status',
          'doctor',
        }.contains(options.rest.single)) {
      throw FormatException('Expected init, index, serve, status, or doctor');
    }
    final command = options.rest.single;
    final config = GraphConfig.load(
      options['root'] as String,
      configPath: options['config'] as String?,
    );
    if (command == 'doctor') {
      stdout.writeln(jsonEncode(ExternalProviders(config).doctor()));
      return;
    }
    if (command == 'init') {
      final file = File(config.safePath('polycodegraph.yaml'));
      if (file.existsSync() ||
          [
            'polycodegraph.yml',
            'polycodegraph.json',
          ].any((n) => File(p.join(config.root, n)).existsSync())) {
        throw FormatException('Configuration already exists');
      }
      await file.writeAsString(
        '''# Repository-relative globs; generated Dart sources are included by default.
include:
  - "**/*.dart"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.mjs"
  - "**/*.cjs"
  - "**/*.java"
  - "**/*.go"
  - "**/*.py"
  - "**/*.pyi"
  - "**/*.rs"
  - "**/*.swift"
  - "**/*.kt"
  - "**/*.h"
  - "**/*.m"
  - "**/*.mm"
exclude:
  - "**/.git/**"
  - "**/.dart_tool/**"
  - "**/build/**"
  - "**/.polycodegraph/**"
cache: .polycodegraph
flutter: true
max_results: 200
max_snippet_lines: 120
max_snippet_chars: 16000
max_file_bytes: 2097152
# sdk_path: /absolute/path/to/flutter/bin/cache/dart-sdk
''',
      );
      stdout.writeln(jsonEncode({'created': 'polycodegraph.yaml'}));
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
    stderr.writeln('polycodegraph: ${e.message}');
    exitCode = 64;
  } on FileSystemException catch (e) {
    stderr.writeln('polycodegraph: ${e.message} (${e.path})');
    exitCode = 74;
  } catch (e, stack) {
    stderr.writeln('polycodegraph: $e\n$stack');
    exitCode = 1;
  }
}
