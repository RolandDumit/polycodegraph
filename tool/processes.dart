import 'dart:io';
import 'package:cli_util/cli_util.dart' as cli;
import 'package:path/path.dart' as p;
import 'package:polycodegraph/src/platform/executables.dart';

final repositoryRoot = p.dirname(p.dirname(File.fromUri(Platform.script).path));
String get dartCommand =>
    Platform.environment['DART'] ??
    cli.dartExecutable ??
    (throw StateError('Dart SDK not found'));
String command(String variable, String fallback) =>
    Platform.environment[variable] ?? fallback;
String get executableSuffix => Platform.isWindows ? '.exe' : '';

class ToolFailure implements Exception {
  final String message;
  final int code;
  ToolFailure(this.message, [this.code = 78]);
  @override
  String toString() => message;
}

Future<void> runTool(
  String program,
  List<String> args, {
  String? directory,
  Map<String, String>? environment,
}) async {
  final executable = resolveNativeExecutable(
    program,
    directory: directory ?? repositoryRoot,
  );
  if (executable == null) {
    throw ToolFailure('Native executable not found: $program');
  }
  final process = await Process.start(
    executable,
    args,
    workingDirectory: directory ?? repositoryRoot,
    environment: environment,
    mode: ProcessStartMode.inheritStdio,
  );
  final code = await process.exitCode;
  if (code != 0) throw ToolFailure('$program failed ($code)', code);
}

/// Run npm's JavaScript entrypoint through native Node. No Windows batch shell
/// is involved, even when paths contain spaces or shell metacharacters.
String npmCli(String node) {
  if (Platform.environment['NPM_CLI'] case final String configured) {
    final path = p.absolute(configured);
    if (File(path).existsSync()) return path;
    throw ToolFailure('NPM_CLI does not exist: $path');
  }
  final executable = resolveNativeExecutable(node);
  if (executable == null) throw ToolFailure('Node.js not found: $node');
  final directories = executableSearchPath(Platform.environment)
      .split(Platform.isWindows ? ';' : ':')
      .where((d) => d.isNotEmpty)
      .map((d) => d.replaceAll('"', ''));
  final candidates = <String>[
    p.join(p.dirname(executable), 'node_modules', 'npm', 'bin', 'npm-cli.js'),
    p.join(
      p.dirname(executable),
      '..',
      'lib',
      'node_modules',
      'npm',
      'bin',
      'npm-cli.js',
    ),
  ];
  for (final dir in directories) {
    final npm = File(p.join(dir, 'npm'));
    if (npm.existsSync()) {
      final resolved = npm.resolveSymbolicLinksSync();
      if (p.basename(resolved) == 'npm-cli.js') candidates.add(resolved);
    }
    candidates.add(p.join(dir, 'node_modules', 'npm', 'bin', 'npm-cli.js'));
  }
  for (final path in candidates) {
    if (File(path).existsSync()) return p.normalize(p.absolute(path));
  }
  throw ToolFailure(
    'npm-cli.js not found. Install npm with Node.js or set NPM_CLI.',
  );
}
