import 'dart:io';
import 'dart:convert';
import 'package:path/path.dart' as p;
import 'processes.dart';
import 'native_smoke.dart';

Future<void> main(List<String> args) async {
  const flags = {'--providers', '--flutter', '--build'};
  if (args.any((arg) => !flags.contains(arg))) {
    stderr.writeln(
      'Usage: dart run tool/check.dart [--providers] [--flutter] [--build]',
    );
    exitCode = 64;
    return;
  }
  try {
    final environment = <String, String>{};
    if (args.contains('--flutter')) {
      if (!File(
        p.join(
          repositoryRoot,
          'examples/flutter_fixture/.dart_tool/package_config.json',
        ),
      ).existsSync()) {
        throw ToolFailure('Resolve Flutter fixture dependencies first.');
      }
      environment['POLYCODEGRAPH_REQUIRE_FLUTTER'] = '1';
    }
    if (args.contains('--providers')) {
      await runTool(command('NODE', 'node'), [
        '--check',
        'providers/typescript/index.cjs',
      ]);
      for (final path in [
        'providers/typescript/node_modules/typescript/package.json',
        'providers/go/graph$executableSuffix',
      ]) {
        if (!File(p.join(repositoryRoot, path)).existsSync()) {
          throw ToolFailure(
            'Missing $path. Run tool/setup_providers.dart first.',
          );
        }
      }
      final stateFile = File(
        p.join(repositoryRoot, 'providers/semantic/.installed.json'),
      );
      if (!stateFile.existsSync()) {
        throw ToolFailure('Prepare Python and Rust adapters first.');
      }
      final state = jsonDecode(stateFile.readAsStringSync()) as Map;
      if (state['jedi'] == null || state['rust_analyzer'] == null) {
        throw ToolFailure('Prepare Python and Rust adapters first.');
      }
      if (state['dev_tools'] == true) {
        await runTool(semanticPython, [
          '-I',
          '-m',
          'ruff',
          'check',
          'providers/semantic',
        ]);
        await runTool(semanticPython, [
          '-I',
          '-m',
          'ruff',
          'format',
          '--check',
          'providers/semantic',
        ]);
        await runTool(semanticPython, [
          '-I',
          '-m',
          'mypy',
          '--config-file',
          'providers/semantic/pyproject.toml',
          'providers/semantic',
        ]);
      }
      environment['POLYCODEGRAPH_REQUIRE_PROVIDERS'] = '1';
    }
    await runTool(dartCommand, [
      'format',
      '--output=none',
      '--set-exit-if-changed',
      'bin',
      'lib',
      'test',
      'tool',
    ]);
    await runTool(dartCommand, ['analyze', '--fatal-infos']);
    await runTool(dartCommand, [
      'test',
      '--reporter',
      'expanded',
    ], environment: environment);
    if (args.contains('--build')) {
      Directory(p.join(repositoryRoot, 'build')).createSync(recursive: true);
      final binary = p.join(
        repositoryRoot,
        'build',
        'polycodegraph$executableSuffix',
      );
      await runTool(dartCommand, [
        'compile',
        'exe',
        'bin/polycodegraph.dart',
        '-o',
        binary,
      ]);
      await runTool(binary, ['--version']);
      await smokeNative(binary, providers: args.contains('--providers'));
    }
  } on ToolFailure catch (error) {
    stderr.writeln(error);
    exitCode = error.code;
  }
}
