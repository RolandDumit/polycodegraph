// Compile against the v0.4.0 oracle, not the current Analyzer provider.
import 'dart:convert';
import 'dart:io';
import 'package:polycodegraph/polycodegraph.dart';

void main(List<String> args) {
  final config = GraphConfig(root: args.first);
  final source = File('${config.root}/bench.dart');
  final content = source.readAsStringSync();
  final nodes = [
    for (var i = 0; i < 100000; i++)
      GraphNode(
        id: 'bench.dart::f$i#function',
        name: 'f$i',
        kind: 'function',
        file: 'bench.dart',
        qualifiedName: 'f$i',
        line: 1,
        endLine: 1,
        offset: 0,
        length: 1,
      ),
  ];
  final edges = [
    for (var i = 0; i < 500000; i++)
      GraphEdge(
        nodes[i % 100000].id,
        nodes[(i + 1) % 100000].id,
        'calls',
        'bench.dart',
        1,
        i,
      ),
  ];
  final s = GraphSnapshot(
    root: config.root,
    fingerprint: config.fingerprint,
    environment: 'bench',
    generation: 'benchmark',
    files: {
      'bench.dart': FileRecord(
        file: 'bench.dart',
        hash: digest(content),
        nodes: nodes,
        edges: edges,
        dependencies: [],
      ),
    },
  );
  if (args.contains('--storage')) {
    final t = Stopwatch()..start();
    final file = File('${config.root}/index-v0.4.json');
    file.writeAsStringSync(jsonEncode(s.toJson()));
    final writeMs = t.elapsedMicroseconds / 1000;
    t.reset();
    final loaded = GraphSnapshot.fromJson(
      jsonDecode(file.readAsStringSync()) as Map<String, dynamic>,
    );
    if (loaded.files.length != 1) throw StateError('invalid storage');
    stdout.writeln(
      jsonEncode({
        'engine': 'dart-json',
        'symbols': 100000,
        'edges': 500000,
        'write_ms': writeMs,
        'read_ms': t.elapsedMicroseconds / 1000,
        'bytes': file.lengthSync(),
        'workload': 'separate cold persistence; no providers or queries',
      }),
    );
    return;
  }
  final start = Stopwatch()..start();
  final samples = <double>[];
  while (start.elapsedMilliseconds < 31000) {
    final t = Stopwatch()..start();
    digest(source.readAsStringSync());
    final q = GraphQuery(s, config);
    q.relations(
      'bench.dart::f50#function',
      direction: 'in',
      kinds: {'calls'},
      limit: 20,
    );
    samples.add(t.elapsedMicroseconds / 1000);
    sleep(Duration(milliseconds: 100));
  }
  samples.sort();
  stdout.writeln(
    jsonEncode({
      'engine': 'dart-v0.4.0',
      'symbols': 100000,
      'edges': 500000,
      'samples': samples.length,
      'median_ms': samples[samples.length ~/ 2],
      'p95_ms': samples[(samples.length * 0.95).floor()],
      'mean_ms': samples.reduce((a, b) => a + b) / samples.length,
      'max_ms': samples.last,
      'reconciliations': samples.length,
      'source_bytes': source.lengthSync(),
      'workload':
          'in-memory graph query including per-query SHA-256 reconciliation; excludes provider analysis and database startup',
    }),
  );
}
