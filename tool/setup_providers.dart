import 'dart:io';
import 'dart:convert';
import 'package:path/path.dart' as p;
import 'processes.dart';

Future<void> main(List<String> args) async {
  const flags = {
    '--typescript',
    '--java',
    '--go',
    '--python',
    '--rust',
    '--dev',
  };
  if (args.any((arg) => !flags.contains(arg))) {
    stderr.writeln(
      'Usage: dart run tool/setup_providers.dart [--typescript] [--java] [--go] [--python] [--rust] [--dev]',
    );
    exitCode = 64;
    return;
  }
  final selected = args.where((arg) => arg != '--dev').toList();
  bool enabled(String flag) => selected.isEmpty || selected.contains(flag);
  try {
    if (enabled('--typescript')) {
      final node = command('NODE', 'node');
      await runTool(node, ['--version']);
      await runTool(node, [
        npmCli(node),
        'ci',
        '--ignore-scripts',
        '--prefix',
        'providers/typescript',
      ]);
    }
    if (enabled('--java')) await runTool(command('JAVA', 'java'), ['-version']);
    if (enabled('--go')) {
      final go = command('GO', 'go');
      final directory = p.join(repositoryRoot, 'providers', 'go');
      await runTool(go, ['version']);
      await runTool(go, ['mod', 'verify'], directory: directory);
      await runTool(go, [
        'build',
        '-buildvcs=false',
        '-mod=readonly',
        '-o',
        'graph$executableSuffix',
        '.',
      ], directory: directory);
    }
    if (enabled('--python') || enabled('--rust')) {
      final python = command(
        'PYTHON',
        Platform.isWindows ? 'python' : 'python3',
      );
      await runTool(python, [
        '-I',
        '-c',
        "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'",
      ]);
      final directory = p.join(repositoryRoot, 'providers', 'semantic');
      if (!File(semanticPython).existsSync()) {
        await runTool(python, ['-I', '-m', 'venv', p.join(directory, '.venv')]);
      }
      final metadata = File(p.join(directory, '.installed.json'));
      final state = metadata.existsSync()
          ? jsonDecode(metadata.readAsStringSync()) as Map<String, dynamic>
          : <String, dynamic>{};
      state['python'] = (await captureTool(semanticPython, [
        '--version',
      ])).trim();
      if (enabled('--python')) {
        await runTool(semanticPython, [
          '-I',
          '-m',
          'pip',
          'install',
          '--disable-pip-version-check',
          '--require-hashes',
          '--only-binary=:all:',
          '-r',
          p.join(directory, 'requirements.lock'),
        ]);
        final versions =
            jsonDecode(
                  await captureTool(semanticPython, [
                    '-I',
                    '-c',
                    "import json,jedi,parso; print(json.dumps({'jedi':jedi.__version__,'parso':parso.__version__}))",
                  ]),
                )
                as Map<String, dynamic>;
        state.addAll(versions);
      }
      if (enabled('--rust')) {
        final custom = Platform.environment['RUST_ANALYZER'];
        if (custom == null) {
          await runTool(semanticPython, [
            '-I',
            p.join(directory, 'setup_rust_analyzer.py'),
          ]);
        }
        state['rust_analyzer'] = (await captureTool(
          custom ?? bundledRustAnalyzer,
          ['--version'],
        )).trim();
      }
      if (args.contains('--dev')) {
        await runTool(semanticPython, [
          '-I',
          '-m',
          'pip',
          'install',
          '--disable-pip-version-check',
          '--only-binary=:all:',
          'ruff==0.16.9',
          'mypy==2.3.1',
        ]);
        state['dev_tools'] = true;
      }
      metadata.writeAsStringSync(jsonEncode(state));
    }
  } on ToolFailure catch (error) {
    stderr.writeln(error);
    exitCode = error.code;
  }
}
