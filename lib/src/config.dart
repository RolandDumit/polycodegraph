import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:glob/glob.dart';
import 'package:path/path.dart' as p;
import 'package:yaml/yaml.dart';

/// Repository-scoped configuration. No server tool can switch the root.
class GraphConfig {
  final String root;
  final List<String> include;
  final List<String> exclude;
  final String cache;
  final bool flutter;
  final String? sdkPath;
  final int maxResults;
  final int maxSnippetLines;
  final int maxSnippetChars;
  final int maxFileBytes;
  GraphConfig({
    required String root,
    this.include = const ['**/*.dart'],
    this.exclude = const [
      '**/.git/**',
      '**/.dart_tool/**',
      '**/build/**',
      '**/.dart-codegraph/**',
    ],
    this.cache = '.dart-codegraph',
    this.flutter = true,
    this.sdkPath,
    this.maxResults = 200,
    this.maxSnippetLines = 120,
    this.maxSnippetChars = 16000,
    this.maxFileBytes = 2097152,
  }) : root = Directory(
         p.normalize(p.absolute(root)),
       ).resolveSymbolicLinksSync() {
    if (p.isAbsolute(cache) ||
        cache == '.' ||
        cache == '' ||
        !p.isWithin(this.root, p.normalize(p.join(this.root, cache)))) {
      throw FormatException('cache must be a directory inside the repository');
    }
    for (final value in [
      maxResults,
      maxSnippetLines,
      maxSnippetChars,
      maxFileBytes,
    ]) {
      if (value < 1) throw FormatException('limits must be positive');
    }
    for (final pattern in [...include, ...exclude]) {
      Glob(pattern);
    }
  }
  static GraphConfig load(String root, {String? configPath}) {
    final base = p.normalize(p.absolute(root));
    File? file;
    if (configPath != null) {
      file = File(
        p.isAbsolute(configPath) ? configPath : p.join(base, configPath),
      );
      if (!file.existsSync()) {
        throw FormatException('Config file not found: ${file.path}');
      }
    } else {
      for (final name in [
        'dart-codegraph.yaml',
        'dart-codegraph.yml',
        'dart-codegraph.json',
      ]) {
        final candidate = File(p.join(base, name));
        if (candidate.existsSync()) {
          file = candidate;
          break;
        }
      }
    }
    if (file == null) return GraphConfig(root: base);
    final raw = file.path.endsWith('.json')
        ? jsonDecode(file.readAsStringSync())
        : loadYaml(file.readAsStringSync());
    if (raw is! Map) throw FormatException('Configuration must be an object');
    const keys = {
      'include',
      'exclude',
      'cache',
      'flutter',
      'sdk_path',
      'max_results',
      'max_snippet_lines',
      'max_snippet_chars',
      'max_file_bytes',
    };
    for (final key in raw.keys) {
      if (!keys.contains(key)) {
        throw FormatException('Unknown config key: $key');
      }
    }
    List<String> strings(String key, List<String> fallback) {
      final value = raw[key];
      if (value == null) return fallback;
      if (value is! List || value.any((v) => v is! String)) {
        throw FormatException('$key must be a list of strings');
      }
      return value.cast<String>();
    }

    int number(String key, int fallback) {
      final value = raw[key];
      if (value == null) return fallback;
      if (value is! int) throw FormatException('$key must be an integer');
      return value;
    }

    if (raw['flutter'] != null && raw['flutter'] is! bool) {
      throw FormatException('flutter must be boolean');
    }
    for (final key in ['cache', 'sdk_path']) {
      if (raw[key] != null && raw[key] is! String) {
        throw FormatException('$key must be a string');
      }
    }
    return GraphConfig(
      root: base,
      include: strings('include', ['**/*.dart']),
      exclude: strings('exclude', [
        '**/.git/**',
        '**/.dart_tool/**',
        '**/build/**',
        '**/.dart-codegraph/**',
      ]),
      cache: raw['cache'] as String? ?? '.dart-codegraph',
      flutter: raw['flutter'] as bool? ?? true,
      sdkPath: raw['sdk_path'] == null
          ? null
          : p.normalize(p.join(base, raw['sdk_path'] as String)),
      maxResults: number('max_results', 200),
      maxSnippetLines: number('max_snippet_lines', 120),
      maxSnippetChars: number('max_snippet_chars', 16000),
      maxFileBytes: number('max_file_bytes', 2097152),
    );
  }

  String get cachePath => safePath(cache, allowDirectory: true);
  String relative(String path) =>
      p.relative(path, from: root).replaceAll('\\', '/');
  String safePath(String relative, {bool allowDirectory = false}) {
    if (p.isAbsolute(relative)) {
      throw FormatException('Use a repository-relative path');
    }
    final candidate = p.normalize(p.join(root, relative));
    if (!p.isWithin(root, candidate)) {
      throw FormatException('Path escapes repository');
    }
    // Reject symlinks at every level, including cache paths and snippet files.
    var cursor = candidate;
    while (cursor != root) {
      if (FileSystemEntity.typeSync(cursor, followLinks: false) ==
          FileSystemEntityType.link) {
        throw FormatException('Symlink paths are not supported');
      }
      cursor = p.dirname(cursor);
    }
    if (!allowDirectory &&
        FileSystemEntity.typeSync(candidate) ==
            FileSystemEntityType.directory) {
      throw FormatException('Expected a file');
    }
    return candidate;
  }

  String get fingerprint => sha256
      .convert(
        utf8.encode(
          jsonEncode({
            'include': include,
            'exclude': exclude,
            'flutter': flutter,
            'sdk': sdkPath,
            'cache': cache,
            'maxFileBytes': maxFileBytes,
            'analyzer': '13.3.0',
            'runtime': Platform.version,
            'executable': Platform.resolvedExecutable,
          }),
        ),
      )
      .toString();
}
