import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import '../graph/query.dart';
import '../index/indexer.dart';
import 'tools.dart';

/// MCP stdio: one UTF-8 JSON-RPC object per line; stdout is protocol-only.
/// Supports the released stateful protocol revisions, not draft revisions.
class McpServer {
  static const versions = ['2025-11-25', '2025-06-18', '2025-03-26'];
  static const maxMessageBytes = 1048576;
  final ToolRegistry registry;
  bool _initialized = false, _ready = false;
  McpServer(RepositoryIndexer indexer) : registry = ToolRegistry(indexer);
  Future<Map<String, dynamic>?> handle(dynamic value) async {
    if (value is! Map<String, dynamic> ||
        value['jsonrpc'] != '2.0' ||
        value['method'] is! String ||
        (value.containsKey('id') &&
            value['id'] is! String &&
            value['id'] is! int &&
            value['id'] != null)) {
      return _error(null, -32600, 'Invalid Request');
    }
    final id = value['id'];
    final method = value['method'] as String;
    if (!value.containsKey('id')) {
      if (method == 'notifications/initialized' && _initialized) _ready = true;
      return null;
    }
    final params = value['params'] ?? <String, dynamic>{};
    if (params is! Map<String, dynamic>) {
      return _error(id, -32602, 'Params must be an object');
    }
    try {
      Map<String, dynamic> result;
      switch (method) {
        case 'initialize':
          if (_initialized) return _error(id, -32600, 'Already initialized');
          if (params['protocolVersion'] is! String ||
              params['capabilities'] is! Map ||
              params['clientInfo'] is! Map) {
            return _error(
              id,
              -32602,
              'protocolVersion, capabilities and clientInfo are required',
            );
          }
          _initialized = true;
          result = {
            'protocolVersion': versions.contains(params['protocolVersion'])
                ? params['protocolVersion']
                : versions.first,
            'capabilities': {
              'tools': {'listChanged': false},
            },
            'serverInfo': {'name': 'polycodegraph', 'version': '0.3.0'},
            'instructions':
                'Use get_architecture then search_symbol and callers/implementations/blast_radius. Use ids from compact rows. Read source only through snippet. Static dispatch is incomplete; check status diagnostics.',
          };
        case 'ping':
          result = {};
        case 'tools/list':
          if (!_ready) {
            return _error(
              id,
              -32000,
              'Initialize and send notifications/initialized first',
            );
          }
          if (params.isNotEmpty) {
            return _error(
              id,
              -32602,
              'tools/list has no cursor; all tools fit on one page',
            );
          }
          result = {'tools': registry.tools.map((t) => t.toJson()).toList()};
        case 'tools/call':
          if (!_ready) {
            return _error(
              id,
              -32000,
              'Initialize and send notifications/initialized first',
            );
          }
          if (params['name'] is! String ||
              (params['arguments'] != null &&
                  params['arguments'] is! Map<String, dynamic>)) {
            return _error(id, -32602, 'Invalid tool call');
          }
          final name = params['name'] as String;
          if (!registry.tools.any((t) => t.name == name)) {
            return _error(id, -32602, 'Unknown tool: $name');
          }
          try {
            final data = await registry.call(
              name,
              params['arguments'] as Map<String, dynamic>? ?? {},
            );
            result = {
              'content': [
                {'type': 'text', 'text': jsonEncode(data)},
              ],
              'structuredContent': data,
              'isError': false,
            };
          } on QueryException catch (e) {
            result = {
              'content': [
                {
                  'type': 'text',
                  'text': jsonEncode({'error': e.message, ...e.details}),
                },
              ],
              'isError': true,
            };
          } on FormatException catch (e) {
            result = {
              'content': [
                {'type': 'text', 'text': e.message},
              ],
              'isError': true,
            };
          } on FileSystemException {
            result = {
              'content': [
                {
                  'type': 'text',
                  'text':
                      'Repository/cache file could not be accessed. Check paths and permissions.',
                },
              ],
              'isError': true,
            };
          } on StateError catch (e) {
            result = {
              'content': [
                {'type': 'text', 'text': e.message},
              ],
              'isError': true,
            };
          }
        default:
          return _error(id, -32601, 'Method not found');
      }
      return {'jsonrpc': '2.0', 'id': id, 'result': result};
    } catch (e, stack) {
      stderr.writeln('polycodegraph: unexpected request failure: $e\n$stack');
      return _error(id, -32603, 'Internal error; see server stderr');
    }
  }

  Future<void> serve({Stream<List<int>>? input, IOSink? output}) async {
    final source = input ?? stdin;
    final sink = output ?? stdout;
    var pending = 0;
    var tail = Future<void>.value();
    final cancelled = <Object?>{};
    final active = <Object?>{};
    await for (final line in _lines(source)) {
      dynamic message;
      try {
        message = jsonDecode(line);
      } catch (_) {
        sink.writeln(
          jsonEncode(_error(null, -32700, 'Parse error or oversized message')),
        );
        continue;
      }
      if (message is Map && message['method'] == 'notifications/cancelled') {
        final params = message['params'];
        final id = params is Map ? params['requestId'] : null;
        if (active.contains(id)) cancelled.add(id);
        continue;
      }
      final id = message is Map ? message['id'] : null;
      if (pending >= 64) {
        if (message is Map && message.containsKey('id')) {
          sink.writeln(jsonEncode(_error(id, -32000, 'Server queue full')));
        }
        continue;
      }
      if (message is Map && message.containsKey('id')) {
        if (!active.add(id)) {
          sink.writeln(
            jsonEncode(_error(id, -32600, 'Request id already in flight')),
          );
          continue;
        }
      }
      pending++;
      final request = message;
      tail = tail.then((_) async {
        try {
          if (cancelled.contains(id)) return;
          final response = await handle(request);
          if (response != null && !cancelled.contains(id)) {
            sink.writeln(jsonEncode(response));
          }
        } finally {
          pending--;
          active.remove(id);
          cancelled.remove(id);
        }
      });
    }
    await tail;
    await sink.flush();
  }
}

Map<String, dynamic> _error(dynamic id, int code, String message) => {
  'jsonrpc': '2.0',
  'id': id,
  'error': {'code': code, 'message': message},
};
Stream<String> _lines(Stream<List<int>> source) async* {
  final buffer = BytesBuilder(copy: false);
  var size = 0, overflow = false;
  await for (final chunk in source) {
    var start = 0;
    for (var i = 0; i < chunk.length; i++) {
      if (chunk[i] != 10) continue;
      size += i - start;
      if (!overflow && size <= McpServer.maxMessageBytes) {
        buffer.add(chunk.sublist(start, i));
      } else {
        overflow = true;
      }
      String line;
      try {
        line = overflow ? '' : utf8.decode(buffer.takeBytes());
      } on FormatException {
        line = '';
      }
      if (overflow) buffer.clear();
      yield line;
      size = 0;
      overflow = false;
      start = i + 1;
    }
    if (start < chunk.length) {
      size += chunk.length - start;
      if (!overflow && size <= McpServer.maxMessageBytes) {
        buffer.add(chunk.sublist(start));
      } else {
        overflow = true;
        buffer.clear();
      }
    }
  }
  if (size > 0) yield ''; // Unterminated JSON is not valid stdio framing.
}
