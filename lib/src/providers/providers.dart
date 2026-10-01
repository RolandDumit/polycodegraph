import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;
import '../config.dart';
import '../platform/executables.dart';
import '../graph/model.dart';

/// Compiler adapters exchange repository-scoped FileRecords over JSON stdin/stdout.
class ExternalProviders {
  final GraphConfig config;
  ExternalProviders(this.config);

  String get assets {
    if (config.providersPath != null) return config.providersPath!;
    final script = Platform.script.scheme == 'file'
        ? File.fromUri(Platform.script).parent.path
        : p.dirname(Platform.resolvedExecutable);
    final candidates = [
      p.join(script, '..', 'providers'),
      p.join(script, 'providers'),
    ];
    for (final candidate in candidates) {
      if (Directory(candidate).existsSync()) return p.normalize(candidate);
    }
    return p.normalize(candidates.first);
  }

  String? _executable(String name) =>
      resolveNativeExecutable(name, directory: config.root);

  String get fingerprint {
    final state = <String, String>{
      for (final key in [
        'GOFLAGS',
        'GOOS',
        'GOARCH',
        'CGO_ENABLED',
        'GOWORK',
        'GOTOOLCHAIN',
      ])
        key: Platform.environment[key] ?? '',
    };
    for (final entry in config.javaClasspath) {
      final type = FileSystemEntity.typeSync(entry, followLinks: false);
      final files = type == FileSystemEntityType.file
          ? [File(entry)]
          : type == FileSystemEntityType.directory
          ? Directory(entry)
                .listSync(recursive: true, followLinks: false)
                .whereType<File>()
                .where(
                  (f) => f.path.endsWith('.class') || f.path.endsWith('.jar'),
                )
                .toList()
          : <File>[];
      files.sort((a, b) => a.path.compareTo(b.path));
      state['classpath:$entry'] = files.isEmpty
          ? 'missing_or_empty'
          : sha256
                .convert(
                  utf8.encode(
                    jsonEncode({
                      for (final file in files)
                        file.path: sha256
                            .convert(file.readAsBytesSync())
                            .toString(),
                    }),
                  ),
                )
                .toString();
    }
    for (final name in [
      'typescript/index.cjs',
      'typescript/package-lock.json',
      'typescript/node_modules/typescript/package.json',
      'java/Graph.java',
      'go/main.go',
      'go/go.mod',
      'go/go.sum',
    ]) {
      final file = File(p.join(assets, name));
      state[name] = file.existsSync()
          ? sha256.convert(file.readAsBytesSync()).toString()
          : 'missing';
    }
    for (final name in [
      config.nodePath,
      config.javaPath,
      config.goPath,
      p.join(assets, 'go', Platform.isWindows ? 'graph.exe' : 'graph'),
    ]) {
      final path = _executable(name);
      final stat = path == null ? null : File(path).statSync();
      state[name] =
          '$path:${stat?.size}:${stat?.modified.toUtc().toIso8601String()}';
    }
    return sha256.convert(utf8.encode(jsonEncode(state))).toString();
  }

  Map<String, dynamic> doctor() => {
    'providers_path': assets,
    'dart': {'available': true, 'engine': 'Dart Analyzer 13.3.0'},
    'typescript_javascript': {
      'available':
          _executable(config.nodePath) != null &&
          File(
            p.join(assets, 'typescript/node_modules/typescript/package.json'),
          ).existsSync(),
      'engine': 'TypeScript compiler API',
      'runtime': config.nodePath,
    },
    'java': {
      'available':
          _executable(config.javaPath) != null &&
          File(p.join(assets, 'java/Graph.java')).existsSync(),
      'engine': 'javac Trees',
      'runtime': config.javaPath,
    },
    'go': {
      'available':
          _executable(
                p.join(
                  assets,
                  'go',
                  Platform.isWindows ? 'graph.exe' : 'graph',
                ),
              ) !=
              null &&
          _executable(config.goPath) != null,
      'engine': 'go/packages + go/types',
      'runtime': config.goPath,
    },
  };

  Future<Map<String, FileRecord>> extract(Map<String, String> hashes) async {
    final records = <String, FileRecord>{};
    for (final language in ['typescript', 'java', 'go']) {
      final files =
          hashes.keys
              .where(
                (f) => language == 'typescript'
                    ? {'typescript', 'javascript'}.contains(languageFor(f))
                    : languageFor(f) == language,
              )
              .toList()
            ..sort();
      if (files.isEmpty) continue;
      final command = switch (language) {
        'typescript' => [
          config.nodePath,
          p.join(assets, 'typescript/index.cjs'),
        ],
        'java' => [
          config.javaPath,
          '--source',
          '17',
          p.join(assets, 'java/Graph.java'),
        ],
        _ => [p.join(assets, 'go', Platform.isWindows ? 'graph.exe' : 'graph')],
      };
      try {
        final output = await _run(
          command,
          jsonEncode({
            'root': config.root,
            'files': [
              for (final f in files) {'file': f, 'hash': hashes[f]},
            ],
            'options': {'classpath': config.javaClasspath},
          }),
        );
        final decoded = jsonDecode(output);
        if (decoded is! List) {
          throw FormatException('Provider response must be an array');
        }
        final batch = <String, FileRecord>{};
        for (final value in decoded) {
          final record = FileRecord.fromJson(
            Map<String, dynamic>.from(value as Map),
          );
          if (!files.contains(record.file) ||
              batch.containsKey(record.file) ||
              record.hash != hashes[record.file]) {
            throw FormatException('Provider returned unexpected or stale file');
          }
          final ids = <String>{};
          for (final node in record.nodes) {
            if (!ids.add(node.id) ||
                node.offset < 0 ||
                node.length < 0 ||
                node.file != record.file ||
                !node.id.startsWith('${record.file}::') ||
                node.line < 1 ||
                node.endLine < node.line) {
              throw FormatException('Invalid provider symbol location');
            }
          }
          record.nodes.sort((a, b) => a.id.compareTo(b.id));
          record.edges.sort((a, b) => a.key.compareTo(b.key));
          record.diagnostics.sort(
            (a, b) => jsonEncode(a).compareTo(jsonEncode(b)),
          );
          batch[record.file] = record;
        }
        if (batch.length != files.length) {
          throw FormatException('Provider omitted indexed files');
        }
        records.addAll(batch);
      } catch (error) {
        for (final file in files) {
          final text = File(config.safePath(file)).readAsStringSync();
          records[file] = FileRecord(
            file: file,
            hash: hashes[file]!,
            nodes: [
              GraphNode(
                id: '$file::file',
                name: file,
                kind: 'file',
                file: file,
                qualifiedName: file,
                line: 1,
                endLine: text.split('\n').length,
                offset: 0,
                length: text.length,
              ),
            ],
            edges: [],
            dependencies: [],
            diagnostics: [
              {
                'severity': 'error',
                'code': 'provider_unavailable',
                'message': '$language provider: $error'.substring(
                  0,
                  ('$language provider: $error').length.clamp(0, 2000),
                ),
                'line': 1,
              },
            ],
            unresolvedCalls: 0,
          );
        }
      }
    }
    return records;
  }

  Future<String> _run(List<String> command, String request) async {
    final executable = _executable(command.first);
    if (executable == null) {
      throw StateError('Native executable not found: ${command.first}');
    }
    final environment = Map<String, String>.of(Platform.environment);
    final searchPath = executableSearchPath(environment);
    environment.removeWhere(
      (key, _) =>
          Platform.isWindows ? key.toUpperCase() == 'PATH' : key == 'PATH',
    );
    final go = _executable(config.goPath);
    environment['PATH'] = go == null
        ? searchPath
        : '${p.dirname(go)}${Platform.isWindows ? ';' : ':'}$searchPath';
    final child = await Process.start(
      executable,
      command.skip(1).toList(),
      workingDirectory: config.root,
      runInShell: false,
      environment: environment,
      includeParentEnvironment: false,
    );
    final output = BytesBuilder(copy: false),
        errors = BytesBuilder(copy: false);
    bool oversized = false, timedOut = false;
    final stdoutDone = child.stdout.listen((bytes) {
      if (output.length + bytes.length > 64 * 1024 * 1024) {
        oversized = true;
        child.kill();
      } else {
        output.add(bytes);
      }
    }).asFuture<void>();
    final stderrDone = child.stderr.listen((bytes) {
      if (errors.length < 8192) {
        errors.add(bytes.take(8192 - errors.length).toList());
      }
    }).asFuture<void>();
    final timer = Timer(Duration(seconds: config.providerTimeoutSeconds), () {
      timedOut = true;
      child.kill();
    });
    try {
      child.stdin.write(request);
      await child.stdin.close();
      final code = await child.exitCode;
      await Future.wait([stdoutDone, stderrDone]);
      if (timedOut) {
        throw StateError('Timed out after ${config.providerTimeoutSeconds}s');
      }
      if (oversized) throw StateError('Response exceeds 64 MiB');
      if (code != 0) {
        throw StateError(
          'Exit $code: ${utf8.decode(errors.takeBytes(), allowMalformed: true)}',
        );
      }
      return utf8.decode(output.takeBytes());
    } finally {
      timer.cancel();
    }
  }
}
