import 'dart:io';
import '../analysis/identity.dart';
import '../config.dart';
import '../index/indexer.dart';
import 'model.dart';

class QueryException implements Exception {
  final String message;
  final Map<String, dynamic> details;
  QueryException(this.message, [this.details = const {}]);
  @override
  String toString() => message;
}

/// In-memory adjacency indexes reconstructed from the persistent snapshot.
class GraphQuery {
  final GraphSnapshot snapshot;
  final GraphConfig config;
  final Map<String, GraphNode> nodes = {};
  final Map<String, List<GraphEdge>> outgoing = {}, incoming = {};
  final List<GraphEdge> edges = [];
  int droppedEdges = 0;
  GraphQuery(this.snapshot, this.config) {
    for (final f in snapshot.files.values) {
      for (final n in f.nodes) {
        nodes[n.id] = n;
      }
    }
    final seen = <String>{};
    for (final f in snapshot.files.values) {
      for (final e in f.edges) {
        if (!nodes.containsKey(e.source) || !nodes.containsKey(e.target)) {
          droppedEdges++;
          continue;
        }
        if (!seen.add(e.key)) continue;
        edges.add(e);
        outgoing.putIfAbsent(e.source, () => []).add(e);
        incoming.putIfAbsent(e.target, () => []).add(e);
      }
    }
    edges.sort((a, b) => a.key.compareTo(b.key));
    for (final list in [...outgoing.values, ...incoming.values]) {
      list.sort((a, b) => a.key.compareTo(b.key));
    }
  }
  GraphNode resolve(String target) {
    if (nodes.containsKey(target)) return nodes[target]!;
    if (nodes.containsKey(fileId(target))) return nodes[fileId(target)]!;
    final exact = nodes.values.where((n) => n.qualifiedName == target).toList();
    final candidates =
        (exact.isNotEmpty
              ? exact
              : nodes.values.where((n) => n.name == target).toList())
          ..sort((a, b) => a.id.compareTo(b.id));
    if (candidates.isEmpty) {
      throw QueryException('Symbol or file not found: $target');
    }
    if (candidates.length > 1) {
      throw QueryException('Ambiguous symbol; use an id from search_symbol', {
        'matches': candidates.take(10).map((n) => n.compact()).toList(),
      });
    }
    return candidates.single;
  }

  Map<String, dynamic> table(
    List<String> columns,
    List<List<dynamic>> rows, {
    int offset = 0,
    int? limit,
    Map<String, dynamic> extra = const {},
  }) {
    if (offset < 0 || (limit != null && limit < 1)) {
      throw QueryException('Invalid pagination');
    }
    final count = (limit ?? 50).clamp(1, config.maxResults);
    final page = rows.skip(offset).take(count).toList();
    return {
      'generation': snapshot.generation,
      ...extra,
      'columns': columns,
      'rows': page,
      'total': rows.length,
      'offset': offset,
      'next_offset': offset + page.length < rows.length
          ? offset + page.length
          : null,
    };
  }

  List<dynamic> row(GraphNode n) => [
    n.id,
    n.kind,
    n.name,
    n.file,
    n.line,
    n.tags,
  ];
  static const nodeColumns = ['id', 'kind', 'name', 'file', 'line', 'tags'];
  Map<String, dynamic> search(
    String query, {
    String? kind,
    String? tag,
    String? file,
    String? language,
    int offset = 0,
    int? limit,
  }) {
    final q = query.toLowerCase();
    final matched = nodes.values
        .where(
          (n) =>
              n.kind != 'external' &&
              (kind == null ? n.kind != 'file' : n.kind == kind) &&
              (tag == null || n.tags.contains(tag)) &&
              (language == null || languageFor(n.file) == language) &&
              (file == null || n.file.startsWith(file)) &&
              (n.name.toLowerCase().contains(q) ||
                  n.qualifiedName.toLowerCase().contains(q)),
        )
        .toList();
    int rank(GraphNode n) => n.name.toLowerCase() == q
        ? 0
        : n.name.toLowerCase().startsWith(q)
        ? 1
        : 2;
    matched.sort((a, b) {
      final r = rank(a).compareTo(rank(b));
      return r == 0 ? a.id.compareTo(b.id) : r;
    });
    return table(
      nodeColumns,
      matched.map(row).toList(),
      offset: offset,
      limit: limit,
    );
  }

  Map<String, dynamic> relations(
    String target, {
    String direction = 'both',
    Set<String>? kinds,
    int offset = 0,
    int? limit,
  }) {
    final n = resolve(target);
    final found = <List<dynamic>>[];
    if (direction != 'in') {
      for (final e in outgoing[n.id] ?? <GraphEdge>[]) {
        if (kinds != null && !kinds.contains(e.kind)) continue;
        found.add([
          ...row(nodes[e.target]!),
          e.kind,
          'out',
          e.file,
          e.line,
          e.confidence,
        ]);
      }
    }
    if (direction != 'out') {
      for (final e in incoming[n.id] ?? <GraphEdge>[]) {
        if (kinds != null && !kinds.contains(e.kind)) continue;
        found.add([
          ...row(nodes[e.source]!),
          e.kind,
          'in',
          e.file,
          e.line,
          e.confidence,
        ]);
      }
    }
    found.sort((a, b) => a.join('\t').compareTo(b.join('\t')));
    return table(
      [
        ...nodeColumns,
        'relation',
        'direction',
        'site_file',
        'site_line',
        'confidence',
      ],
      found,
      offset: offset,
      limit: limit,
      extra: {'target': n.id},
    );
  }

  Map<String, dynamic> implementations(
    String target, {
    int offset = 0,
    int? limit,
  }) {
    final n = resolve(target);
    final kinds = {'extends', 'implements', 'with', 'overrides'};
    final visited = {n.id};
    final queue = [n.id];
    final result = <GraphNode>[];
    for (var i = 0; i < queue.length; i++) {
      for (final e in incoming[queue[i]] ?? <GraphEdge>[]) {
        if (!kinds.contains(e.kind) || !visited.add(e.source)) continue;
        queue.add(e.source);
        result.add(nodes[e.source]!);
      }
    }
    result.sort((a, b) => a.id.compareTo(b.id));
    return table(
      nodeColumns,
      result.map(row).toList(),
      offset: offset,
      limit: limit,
      extra: {'target': n.id},
    );
  }

  Map<String, dynamic> dependencies(
    String target, {
    String direction = 'out',
    int offset = 0,
    int? limit,
  }) {
    final n = resolve(target);
    final file = n.kind == 'file' ? n : resolve(n.file);
    final byKey = <String, List<dynamic>>{};
    for (final e in edges) {
      if (e.kind == 'contains') continue;
      final from = nodes[e.source]!;
      final to = nodes[e.target]!;
      if (from.file == to.file) continue;
      final out = from.file == file.file;
      final into = to.file == file.file;
      if ((direction == 'out' && !out) ||
          (direction == 'in' && !into) ||
          (direction == 'both' && !out && !into)) {
        continue;
      }
      final other = out ? to : from;
      final key = '${other.file}|${e.kind}|${out ? 'out' : 'in'}';
      byKey[key] = [other.file, e.kind, out ? 'out' : 'in'];
    }
    final rows = byKey.values.toList()
      ..sort((a, b) => a.join().compareTo(b.join()));
    return table(
      ['file', 'relation', 'direction'],
      rows,
      offset: offset,
      limit: limit,
      extra: {'target': file.id},
    );
  }

  Map<String, dynamic> affected(
    String target, {
    int depth = 6,
    int offset = 0,
    int? limit,
  }) {
    if (depth < 1 || depth > 32) throw QueryException('depth must be 1..32');
    final start = resolve(target);
    const dependencyKinds = {
      'references',
      'calls',
      'extends',
      'implements',
      'with',
      'on',
      'overrides',
      'registers',
      'imports',
      'exports',
      'part',
      'part_of',
    };
    final visited = <String, int>{start.id: 0};
    final reasons = <String, List<String>>{
      start.id: [start.id, 'seed'],
    };
    final queue = [start.id];
    bool depthLimited = false;
    for (var i = 0; i < queue.length; i++) {
      final id = queue[i], distance = visited[id]!;
      final n = nodes[id]!;
      final candidates = <List<String>>[];
      for (final e in incoming[id] ?? <GraphEdge>[]) {
        if (dependencyKinds.contains(e.kind)) {
          candidates.add([e.source, e.kind]);
        }
      }
      if ({
        'file',
        'class',
        'mixin',
        'enum',
        'extension',
        'extension_type',
        'interface',
        'struct',
        'record',
        'type',
      }.contains(n.kind)) {
        for (final e in outgoing[id] ?? <GraphEdge>[]) {
          if (e.kind == 'contains') {
            candidates.add([e.target, 'member_of_changed_container']);
          }
        }
      }
      for (final e in outgoing[id] ?? <GraphEdge>[]) {
        if (e.kind == 'overrides') {
          candidates.add([e.target, 'dispatch_contract']);
        }
      }
      if (n.parent != null && nodes[n.parent]?.kind != 'file') {
        candidates.add([n.parent!, 'container_of_affected_member']);
      }
      for (final candidate in candidates) {
        if (visited.containsKey(candidate[0])) continue;
        if (distance >= depth) {
          depthLimited = true;
          continue;
        }
        visited[candidate[0]] = distance + 1;
        reasons[candidate[0]] = [id, candidate[1]];
        queue.add(candidate[0]);
      }
    }
    final affected =
        queue.where((id) => id != start.id).map((id) => nodes[id]!).toList()
          ..sort((a, b) {
            final d = visited[a.id]!.compareTo(visited[b.id]!);
            return d == 0 ? a.id.compareTo(b.id) : d;
          });
    final affectedFiles =
        affected
            .map((n) => n.file)
            .where(snapshot.files.containsKey)
            .toSet()
            .toList()
          ..sort();
    return table(
      [...nodeColumns, 'distance', 'via', 'reason'],
      affected
          .map((n) => [...row(n), visited[n.id], ...reasons[n.id]!])
          .toList(),
      offset: offset,
      limit: limit,
      extra: {
        'target': start.id,
        'conservative': true,
        'depth': depth,
        'depth_limited': depthLimited,
        'affected_files': affectedFiles.take(config.maxResults).toList(),
        'affected_files_total': affectedFiles.length,
      },
    );
  }

  Map<String, dynamic> snippet({
    String? target,
    String? file,
    int? startLine,
    int? endLine,
    int context = 2,
  }) {
    final n = target == null ? null : resolve(target);
    file ??= n?.file;
    if (file == null || !snapshot.files.containsKey(file)) {
      throw QueryException('Choose an indexed source file');
    }
    final path = config.safePath(file);
    final content = File(path).readAsStringSync();
    if (digest(content) != snapshot.files[file]!.hash) {
      throw QueryException('Source changed while reading; retry the query');
    }
    final lines = content.split('\n');
    if (context < 0 || context > 20) {
      throw QueryException('context must be 0..20');
    }
    final requestedStart = startLine ?? n?.line ?? 1;
    final requestedEnd = endLine ?? n?.endLine ?? requestedStart;
    if (requestedStart < 1 ||
        requestedEnd < requestedStart ||
        requestedStart > lines.length) {
      throw QueryException('Invalid line range');
    }
    final start = (requestedStart - context).clamp(1, lines.length);
    final desiredEnd = (requestedEnd + context).clamp(start, lines.length);
    final end = desiredEnd.clamp(start, start + config.maxSnippetLines - 1);
    var text = lines.sublist(start - 1, end).join('\n');
    final charTruncated = text.length > config.maxSnippetChars;
    if (charTruncated) text = text.substring(0, config.maxSnippetChars);
    return {
      'generation': snapshot.generation,
      'file': file,
      'start_line': start,
      'end_line': start + text.split('\n').length - 1,
      'truncated': end < desiredEnd || charTruncated,
      'text': text,
    };
  }

  Map<String, dynamic> architecture({int limit = 20}) {
    Map<String, int> counts(Iterable<String> values) {
      final out = <String, int>{};
      for (final v in values) {
        out[v] = (out[v] ?? 0) + 1;
      }
      return Map.fromEntries(
        out.entries.toList()..sort((a, b) => a.key.compareTo(b.key)),
      );
    }

    final symbols = nodes.values
        .where((n) => n.kind != 'file' && n.kind != 'external')
        .toList();
    final hubs = symbols.toList()
      ..sort((a, b) {
        final d = (incoming[b.id]?.length ?? 0).compareTo(
          incoming[a.id]?.length ?? 0,
        );
        return d == 0 ? a.id.compareTo(b.id) : d;
      });
    final directories = counts(
      snapshot.files.keys.map(
        (f) => f.contains('/')
            ? f.split('/').take(f.split('/').length - 1).take(2).join('/')
            : '.',
      ),
    );
    return {
      'generation': snapshot.generation,
      'files': snapshot.files.length,
      'symbols': symbols.length,
      'languages': counts(snapshot.files.values.map((f) => f.language)),
      'edges': edges.length,
      'kinds': counts(symbols.map((n) => n.kind)),
      'tags': counts(symbols.expand((n) => n.tags)),
      'directories': Map.fromEntries(
        directories.entries.take(config.maxResults),
      ),
      'directories_total': directories.length,
      'relations': counts(edges.map((e) => e.kind)),
      'diagnostics': counts(
        snapshot.files.values
            .expand((f) => f.diagnostics)
            .map((d) => d['severity'] as String),
      ),
      'diagnostic_samples': [
        for (final key in (snapshot.files.keys.toList()..sort()))
          for (final d in snapshot.files[key]!.diagnostics)
            {
              'file': key,
              ...d,
              if (d['message'] is String)
                'message': (d['message'] as String).substring(
                  0,
                  (d['message'] as String).length.clamp(0, 512),
                ),
              if (d['message'] is String &&
                  (d['message'] as String).length > 512)
                'message_truncated': true,
            },
      ].take(limit.clamp(1, config.maxResults)).toList(),
      'diagnostic_samples_total': snapshot.files.values.fold<int>(
        0,
        (sum, f) => sum + f.diagnostics.length,
      ),
      'unresolved_calls': snapshot.files.values.fold<int>(
        0,
        (sum, f) => sum + f.unresolvedCalls,
      ),
      'dropped_edges': droppedEdges,
      'skipped': snapshot.skipped.take(config.maxResults).toList(),
      'skipped_total': snapshot.skipped.length,
      'hubs': {
        'columns': [...nodeColumns, 'incoming_edges'],
        'rows': hubs
            .take(limit.clamp(1, config.maxResults))
            .map((n) => [...row(n), incoming[n.id]?.length ?? 0])
            .toList(),
      },
      'precision':
          'Static semantic targets across Dart, TypeScript/JavaScript, Java, Go, Python, Rust, Swift, Objective-C and Kotlin; dynamic/callback flow, external Rust crates and macro expansion may be incomplete. Flutter tags are optional discovery hints.',
    };
  }
}
