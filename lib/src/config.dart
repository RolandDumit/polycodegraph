import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:glob/glob.dart';
import 'package:path/path.dart' as p;
import 'package:yaml/yaml.dart';

/// Repository-scoped configuration. No server tool can switch the root.
class GraphConfig {
  static const defaultIncludes = [
    '**/*.dart',
    '**/*.ts',
    '**/*.tsx',
    '**/*.js',
    '**/*.jsx',
    '**/*.mjs',
    '**/*.cjs',
    '**/*.java',
    '**/*.go',
    '**/*.py',
    '**/*.pyi',
    '**/*.rs',
    '**/*.swift',
    '**/*.kt',
    '**/*.h',
    '**/*.m',
    '**/*.mm',
  ];
  final String? providersPath;
  final String nodePath, javaPath, goPath, rustAnalyzerPath;
  final String? pythonPath, rustSysrootSrc, libclangPath;
  final String swiftcPath, mobileProjectPath;
  final List<String> pythonSearchPaths, rustCfg;
  final List<String> javaClasspath;
  final int providerTimeoutSeconds;

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
    this.include = defaultIncludes,
    this.exclude = const [
      '**/.git/**',
      '**/.dart_tool/**',
      '**/build/**',
      '**/.polycodegraph/**',
    ],
    this.cache = '.polycodegraph',
    this.flutter = true,
    this.providersPath,
    this.nodePath = 'node',
    this.javaPath = 'java',
    this.goPath = 'go',
    this.pythonPath,
    this.swiftcPath = 'swiftc',
    this.libclangPath,
    this.mobileProjectPath = 'polycodegraph.mobile.json',
    this.pythonSearchPaths = const [],
    this.rustAnalyzerPath = 'rust-analyzer',
    this.rustCfg = const [],
    this.rustSysrootSrc,
    this.javaClasspath = const [],
    this.providerTimeoutSeconds = 120,
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
    safePath(mobileProjectPath);
    for (final value in [
      maxResults,
      maxSnippetLines,
      maxSnippetChars,
      maxFileBytes,
      providerTimeoutSeconds,
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
        'polycodegraph.yaml',
        'polycodegraph.yml',
        'polycodegraph.json',
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
      'providers_path',
      'node_path',
      'java_path',
      'go_path',
      'python_path',
      'rust_analyzer_path',
      'rust_sysroot_src',
      'swiftc_path',
      'libclang_path',
      'mobile_project_path',
      'java_classpath',
      'python_search_paths',
      'rust_cfg',
      'provider_timeout_seconds',
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
    for (final key in [
      'cache',
      'sdk_path',
      'providers_path',
      'node_path',
      'java_path',
      'go_path',
      'python_path',
      'rust_analyzer_path',
      'rust_sysroot_src',
      'swiftc_path',
      'libclang_path',
      'mobile_project_path',
    ]) {
      if (raw[key] != null && raw[key] is! String) {
        throw FormatException('$key must be a string');
      }
    }
    String runtime(String key, String fallback) {
      final value = raw[key] as String? ?? fallback;
      if (!p.isAbsolute(value) &&
          (value.contains('/') || value.contains('\\'))) {
        return p.normalize(p.join(base, value));
      }
      return value;
    }

    return GraphConfig(
      root: base,
      include: strings('include', defaultIncludes),
      exclude: strings('exclude', [
        '**/.git/**',
        '**/.dart_tool/**',
        '**/build/**',
        '**/.polycodegraph/**',
      ]),
      cache: raw['cache'] as String? ?? '.polycodegraph',
      flutter: raw['flutter'] as bool? ?? true,
      providersPath: raw['providers_path'] == null
          ? null
          : p.normalize(p.join(base, raw['providers_path'] as String)),
      nodePath: runtime('node_path', 'node'),
      javaPath: runtime('java_path', 'java'),
      goPath: runtime('go_path', 'go'),
      pythonPath: raw['python_path'] == null
          ? null
          : runtime('python_path', 'python3'),
      pythonSearchPaths: strings(
        'python_search_paths',
        [],
      ).map((v) => p.normalize(p.join(base, v))).toList(),
      swiftcPath: runtime('swiftc_path', 'swiftc'),
      libclangPath: raw['libclang_path'] == null
          ? null
          : p.normalize(p.join(base, raw['libclang_path'] as String)),
      mobileProjectPath:
          raw['mobile_project_path'] as String? ?? 'polycodegraph.mobile.json',
      rustAnalyzerPath: runtime('rust_analyzer_path', 'rust-analyzer'),
      rustCfg: strings('rust_cfg', []),
      rustSysrootSrc: raw['rust_sysroot_src'] == null
          ? null
          : p.normalize(p.join(base, raw['rust_sysroot_src'] as String)),
      javaClasspath: strings(
        'java_classpath',
        [],
      ).map((v) => p.normalize(p.join(base, v))).toList(),
      providerTimeoutSeconds: number('provider_timeout_seconds', 120),
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
            'providers': [
              providersPath,
              nodePath,
              javaPath,
              goPath,
              javaClasspath,
              providerTimeoutSeconds,
              pythonPath,
              pythonSearchPaths,
              rustAnalyzerPath,
              rustCfg,
              rustSysrootSrc,
              swiftcPath,
              libclangPath,
              mobileProjectPath,
              'semantic-v3',
            ],
            'runtime': Platform.version,
            'executable': Platform.resolvedExecutable,
          }),
        ),
      )
      .toString();
}
