import 'dart:io';
import 'package:path/path.dart' as p;
import 'processes.dart';

Future<void> main(List<String> args) async {
  const flags = {'--typescript', '--java', '--go'};
  if (args.any((arg) => !flags.contains(arg))) {
    stderr.writeln(
      'Usage: dart run tool/setup_providers.dart [--typescript] [--java] [--go]',
    );
    exitCode = 64;
    return;
  }
  bool enabled(String flag) => args.isEmpty || args.contains(flag);
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
  } on ToolFailure catch (error) {
    stderr.writeln(error);
    exitCode = error.code;
  }
}
