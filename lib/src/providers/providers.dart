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

  String get pythonExecutable {
    if (config.pythonPath != null) return config.pythonPath!;
    final local = p.join(
      assets,
      'semantic',
      '.venv',
      Platform.isWindows ? 'Scripts/python.exe' : 'bin/python',
    );
    return File(local).existsSync()
        ? local
        : Platform.isWindows
        ? 'python'
        : 'python3';
  }

  String get rustAnalyzerExecutable {
    if (config.rustAnalyzerPath != 'rust-analyzer') {
      return config.rustAnalyzerPath;
    }
    final local = p.join(
      assets,
      'semantic',
      '.tools',
      Platform.isWindows ? 'rust-analyzer.exe' : 'rust-analyzer',
    );
    return File(local).existsSync() ? local : config.rustAnalyzerPath;
  }

  Map<String, dynamic> get semanticSetup {
    final file = File(p.join(assets, 'semantic', '.installed.json'));
    try {
      return file.existsSync()
          ? Map<String, dynamic>.from(
              jsonDecode(file.readAsStringSync()) as Map,
            )
          : {};
    } on FormatException {
      return {};
    } on TypeError {
      return {};
    }
  }

  String get fingerprint {
    final state = <String, String>{
      for (final key in [
        'GOFLAGS',
        'GOOS',
        'GOARCH',
        'CGO_ENABLED',
        'GOWORK',
        'GOTOOLCHAIN',
        'SDKROOT',
        'DEVELOPER_DIR',
        'TOOLCHAINS',
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
      'semantic/index.py',
      'semantic/requirements.lock',
      'semantic/requirements-mobile.lock',
      'semantic/setup_mobile.py',
      'kotlin/GraphPlugin.kt',
      'kotlin/.tools/installed.json',
      'kotlin/.tools/graph-plugin.jar',
      'semantic/polycodegraph_adapters/mobile_common.py',
      'semantic/polycodegraph_adapters/swift_graph.py',
      'semantic/polycodegraph_adapters/objc_graph.py',
      'semantic/polycodegraph_adapters/kotlin_graph.py',
      'semantic/.installed.json',
      'semantic/setup_rust_analyzer.py',
      'semantic/polycodegraph_adapters/__init__.py',
      'semantic/polycodegraph_adapters/model.py',
      'semantic/polycodegraph_adapters/lsp.py',
      'semantic/polycodegraph_adapters/python_graph.py',
      'semantic/polycodegraph_adapters/rust_graph.py',
      'semantic/polycodegraph_adapters/rust_project.py',
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
      pythonExecutable,
      rustAnalyzerExecutable,
      config.swiftcPath,
      if (config.libclangPath != null) config.libclangPath!,
      p.join(assets, 'go', Platform.isWindows ? 'graph.exe' : 'graph'),
    ]) {
      final path = _executable(name);
      final stat = path == null ? null : File(path).statSync();
      state[name] =
          '$path:${stat?.size}:${stat?.modified.toUtc().toIso8601String()}';
    }
    for (final name in [
      p.join(assets, 'kotlin/.tools/kotlinc/lib/kotlin-compiler.jar'),
      if (config.libclangPath != null) config.libclangPath!,
    ]) {
      final stat = File(name).statSync();
      state[name] =
          '${stat.type}:${stat.size}:${stat.modified.toUtc().toIso8601String()}';
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
    'python': {
      'available':
          _executable(pythonExecutable) != null &&
          File(p.join(assets, 'semantic/index.py')).existsSync() &&
          (config.pythonPath != null || semanticSetup['jedi'] != null),
      'engine': 'Python AST + Jedi 0.20.0',
      'runtime': pythonExecutable,
    },
    'swift': {
      'available':
          _executable(pythonExecutable) != null &&
          _executable(config.swiftcPath) != null,
      'engine': 'Swift 6.2+ semantic JSON AST',
      'runtime': config.swiftcPath,
    },
    'objectivec': {
      'available':
          _executable(pythonExecutable) != null &&
          (config.libclangPath != null
              ? File(config.libclangPath!).existsSync()
              : semanticSetup['libclang'] != null),
      'engine': 'libclang canonical cursors',
      'runtime': config.libclangPath ?? 'adapter libclang',
    },
    'kotlin': {
      'available':
          _executable(pythonExecutable) != null &&
          _executable(config.javaPath) != null &&
          File(p.join(assets, 'kotlin/.tools/graph-plugin.jar')).existsSync(),
      'engine': 'Kotlin K2 2.3.10 resolved IR',
      'runtime': config.javaPath,
    },
    'rust': {
      'available':
          _executable(pythonExecutable) != null &&
          _executable(rustAnalyzerExecutable) != null &&
          File(p.join(assets, 'semantic/index.py')).existsSync(),
      'engine': 'rust-analyzer LSP + HIR',
      'runtime': rustAnalyzerExecutable,
      'build_scripts': false,
      'proc_macros': false,
    },
  };

  Future<Map<String, FileRecord>> extract(Map<String, String> hashes) async {
    final records = <String, FileRecord>{};
    for (final language in [
      'typescript',
      'java',
      'go',
      'python',
      'rust',
      'swift',
      'objectivec',
      'kotlin',
    ]) {
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
        'go' => [
          p.join(assets, 'go', Platform.isWindows ? 'graph.exe' : 'graph'),
        ],
        _ => [
          pythonExecutable,
          '-I',
          '-X',
          'utf8',
          p.join(assets, 'semantic/index.py'),
          '--$language',
        ],
      };
      try {
        final output = await _run(
          command,
          jsonEncode({
            'root': config.root,
            'files': [
              for (final f in files) {'file': f, 'hash': hashes[f]},
            ],
            'options': {
              'classpath': config.javaClasspath,
              'python_search_paths': config.pythonSearchPaths,
              'rust_analyzer_path':
                  _executable(rustAnalyzerExecutable) ??
                  config.rustAnalyzerPath,
              'rust_cfg': config.rustCfg,
              'rust_sysroot_src': config.rustSysrootSrc,
              'swiftc_path':
                  _executable(config.swiftcPath) ?? config.swiftcPath,
              'java_path': _executable(config.javaPath) ?? config.javaPath,
              'libclang_path': config.libclangPath,
              'mobile_project_path': config.mobileProjectPath,
              'adapter_directory': p.join(assets, 'semantic'),
              'timeout': config.providerTimeoutSeconds,
              'max_file_bytes': config.maxFileBytes,
            },
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
