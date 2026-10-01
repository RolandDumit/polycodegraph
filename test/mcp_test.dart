import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:dart_codegraph/dart_codegraph.dart';
import 'package:path/path.dart' as p;
import 'package:test/test.dart';
import 'support.dart';

Map<String, dynamic> request(
  Object id,
  String method, [
  Map<String, dynamic>? params,
]) => {'jsonrpc': '2.0', 'id': id, 'method': method, 'params': ?params};
Map<String, dynamic> initialize(int id, {String version = '2025-11-25'}) =>
    request(id, 'initialize', {
      'protocolVersion': version,
      'capabilities': {},
      'clientInfo': {'name': 'test', 'version': '1.0'},
    });
void main() {
  late Directory repo;
  late McpServer server;
  setUp(() {
    repo = fixtureCopy();
    server = McpServer(RepositoryIndexer(GraphConfig(root: repo.path)));
  });
  tearDown(() => repo.deleteSync(recursive: true));
  test('handshake, negotiation, lifecycle and validation', () async {
    expect(
      (await server.handle(request(1, 'tools/list')))!.containsKey('error'),
      isTrue,
    );
    expect(
      (await server.handle(
        initialize(2, version: 'future'),
      ))!['result']['protocolVersion'],
      '2025-11-25',
    );
    await server.handle({
      'jsonrpc': '2.0',
      'method': 'notifications/initialized',
    });
    final listing =
        (await server.handle(request(3, 'tools/list')))!['result']['tools']
            as List;
    expect(listing, hasLength(15));
    expect((await server.handle(initialize(4)))!['error']['code'], -32600);
    expect((await server.handle(request(5, 'nope')))!['error']['code'], -32601);
    expect(
      (await server.handle(
        request(6, 'tools/call', {'name': 'missing'}),
      ))!['error']['code'],
      -32602,
    );
    final invalid = await server.handle(
      request(7, 'tools/call', {
        'name': 'callers',
        'arguments': {'target': 1},
      }),
    );
    expect(invalid!['result']['isError'], isTrue);
    expect(await server.handle({'jsonrpc': '2.0', 'method': 'nope'}), isNull);
    expect((await server.handle([]))!['error']['code'], -32600);
  });
  test('MCP tool registry covers every query and error response', () async {
    final registry = server.registry;
    for (final spec in registry.tools) {
      final args = <String, dynamic>{};
      if (spec.required.contains('target')) {
        args['target'] = spec.name == 'dependencies'
            ? 'lib/domain.dart'
            : 'UserRepository.fetch';
      }
      if (spec.required.contains('query')) args['query'] = 'MemoryRepository';
      if (spec.name == 'snippet') args['target'] = 'MemoryRepository';
      final data = await registry.call(spec.name, args);
      expect(data, isNotEmpty, reason: spec.name);
    }
    await server.handle(initialize(1));
    await server.handle({
      'jsonrpc': '2.0',
      'method': 'notifications/initialized',
    });
    final result = await server.handle(
      request(2, 'tools/call', {
        'name': 'search_symbol',
        'arguments': {'query': 'fetch', 'limit': 1},
      }),
    );
    expect(result!['result']['structuredContent']['rows'], hasLength(1));
    expect(
      jsonDecode(result['result']['content'][0]['text']),
      result['result']['structuredContent'],
    );
    final ambiguous = await server.handle(
      request(3, 'tools/call', {
        'name': 'callers',
        'arguments': {'target': 'fetch'},
      }),
    );
    expect(ambiguous!['result']['isError'], isTrue);
    expect(
      () => registry.call('search_symbol', {'query': 'x', 'limit': -1}),
      throwsA(isA<QueryException>()),
    );
    expect(
      () => registry.call('snippet', {'unknown': true}),
      throwsA(isA<QueryException>()),
    );
  });
  test(
    'real stdio process handles malformed framing, tools, refresh and EOF',
    () async {
      final process = await Process.start(
        Platform.resolvedExecutable,
        ['bin/dart_codegraph.dart', 'serve', '--root', repo.path],
        workingDirectory: Directory.current.path,
        environment: {'DASH__SUPPRESS_ANALYTICS': 'true'},
      );
      final errors = StringBuffer();
      process.stderr.transform(utf8.decoder).listen(errors.write);
      final responses = StreamIterator(
        process.stdout.transform(utf8.decoder).transform(const LineSplitter()),
      );
      Future<Map<String, dynamic>> read() async {
        expect(
          await responses.moveNext().timeout(const Duration(seconds: 30)),
          isTrue,
        );
        return jsonDecode(responses.current) as Map<String, dynamic>;
      }

      void send(dynamic message) => process.stdin.writeln(jsonEncode(message));
      send(initialize(1));
      expect((await read())['result']['protocolVersion'], '2025-11-25');
      send({'jsonrpc': '2.0', 'method': 'notifications/initialized'});
      process.stdin.writeln('not json');
      expect((await read())['error']['code'], -32700);
      process.stdin.writeln('x' * (McpServer.maxMessageBytes + 1));
      expect((await read())['error']['code'], -32700);
      send(request(2, 'ping'));
      expect((await read())['result'], isEmpty);
      send(request(3, 'tools/list'));
      expect((await read())['result']['tools'], hasLength(15));
      send(
        request(4, 'tools/call', {
          'name': 'search_symbol',
          'arguments': {'query': 'MemoryRepository', 'kind': 'class'},
        }),
      );
      final result = (await read())['result'];
      expect(result['isError'], isFalse);
      final generation = result['structuredContent']['generation'];
      final source = File(p.join(repo.path, 'lib/domain.dart'));
      source.writeAsStringSync('// edit\n${source.readAsStringSync()}');
      send(
        request(5, 'tools/call', {
          'name': 'search_symbol',
          'arguments': {'query': 'MemoryRepository', 'kind': 'class'},
        }),
      );
      expect(
        (await read())['result']['structuredContent']['generation'],
        isNot(generation),
      );
      await process.stdin.close();
      expect(
        await process.exitCode.timeout(const Duration(seconds: 30)),
        0,
        reason: errors.toString(),
      );
      await responses.cancel();
    },
    timeout: const Timeout(Duration(seconds: 90)),
  );
  test('separate index processes serialize persistent writes', () async {
    Future<ProcessResult> run() => Process.run(
      Platform.resolvedExecutable,
      ['bin/dart_codegraph.dart', 'index', '--root', repo.path],
      environment: {'DASH__SUPPRESS_ANALYTICS': 'true'},
    );
    final results = await Future.wait([run(), run()]);
    for (final result in results) {
      expect(result.exitCode, 0, reason: result.stderr.toString());
    }
    expect(
      results
          .map((r) => (jsonDecode(r.stdout as String) as Map)['full'])
          .toSet(),
      {true, false},
    );
    expect(
      RepositoryIndexer(GraphConfig(root: repo.path)).load()!.files,
      hasLength(4),
    );
  });
}
