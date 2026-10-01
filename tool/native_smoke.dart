import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:cli_util/cli_util.dart' as cli;
import 'package:path/path.dart' as p;
import 'processes.dart';

/// Exercise the compiled server, URI escaping, CRLF and paths with spaces.
Future<void> smokeNative(String binary) async {
  final root = Directory.systemTemp.createTempSync(
    'polycodegraph native spaces ',
  );
  Process? process;
  StreamIterator<String>? responses;
  final errors = StringBuffer();
  try {
    File(p.join(root.path, 'polycodegraph.json')).writeAsStringSync(
      jsonEncode({
        'sdk_path': cli.sdkPath ?? (throw ToolFailure('Dart SDK not found')),
        'providers_path': p.join(repositoryRoot, 'providers'),
      }),
    );
    final source = File(p.join(root.path, 'library with spaces.dart'));
    source.writeAsStringSync(
      "library fixture;\r\npart 'part%20with%20spaces.dart';\r\nabstract class Repository { String fetch(); }\r\nclass MemoryRepository implements Repository { String fetch() => 'ok'; }\r\nString load(Repository repository) => repository.fetch();\r\n",
    );
    File(
      p.join(root.path, 'part with spaces.dart'),
    ).writeAsStringSync('part of fixture;\r\nclass Model {}\r\n');
    process = await Process.start(binary, ['serve', '--root', root.path]);
    process.stderr.transform(utf8.decoder).listen(errors.write);
    responses = StreamIterator(
      process.stdout.transform(utf8.decoder).transform(const LineSplitter()),
    );
    var id = 0;
    Future<Map<String, dynamic>> request(
      String method, [
      Map<String, dynamic>? params,
    ]) async {
      final requestId = ++id;
      process!.stdin.writeln(
        jsonEncode({
          'jsonrpc': '2.0',
          'id': requestId,
          'method': method,
          'params': ?params,
        }),
      );
      if (!await responses!.moveNext().timeout(const Duration(seconds: 120))) {
        throw ToolFailure('Native MCP closed unexpectedly: $errors', 1);
      }
      final reply = jsonDecode(responses!.current) as Map<String, dynamic>;
      if (reply['id'] != requestId || reply.containsKey('error')) {
        throw ToolFailure('Invalid native MCP reply: $reply', 1);
      }
      return reply['result'] as Map<String, dynamic>;
    }

    Future<Map<String, dynamic>> call(
      String name, [
      Map<String, dynamic> args = const {},
    ]) async {
      final result = await request('tools/call', {
        'name': name,
        'arguments': args,
      });
      if (result['isError'] == true) {
        throw ToolFailure('Native MCP tool failed: $result', 1);
      }
      return result['structuredContent'] as Map<String, dynamic>;
    }

    await request('initialize', {
      'protocolVersion': '2025-11-25',
      'capabilities': {},
      'clientInfo': {'name': 'native-smoke', 'version': '1'},
    });
    process.stdin.writeln(
      jsonEncode({'jsonrpc': '2.0', 'method': 'notifications/initialized'}),
    );
    final search = await call('search_symbol', {
      'query': 'MemoryRepository',
      'kind': 'class',
    });
    if (search['total'] != 1) {
      throw ToolFailure('Native search failed: $search', 1);
    }
    final target = (search['rows'] as List).single[0] as String;
    await call('snippet', {'target': target});
    final deps = await call('dependencies', {
      'target': 'part with spaces.dart',
    });
    if (deps['total'] != 1) {
      throw ToolFailure('Native part_of dependency failed: $deps', 1);
    }
    final before = search['generation'];
    source.writeAsStringSync('// edit\r\n${source.readAsStringSync()}');
    final refreshed = await call('search_symbol', {
      'query': 'MemoryRepository',
      'kind': 'class',
    });
    if (refreshed['generation'] == before) {
      throw ToolFailure('Native invalidation failed', 1);
    }
    await process.stdin.close();
    if (await process.exitCode.timeout(const Duration(seconds: 30)) != 0) {
      throw ToolFailure('Native server failed: $errors', 1);
    }
    stdout.writeln(
      'Native MCP: search, snippet, part dependencies, incremental cache and EOF passed.',
    );
  } finally {
    process?.kill();
    await responses?.cancel();
    root.deleteSync(recursive: true);
  }
}
