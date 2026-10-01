String languageFor(String file) {
  final ext = file.split('.').last;
  return switch (ext) {
    'ts' || 'tsx' => 'typescript',
    'js' || 'jsx' || 'mjs' || 'cjs' => 'javascript',
    'java' => 'java',
    'go' => 'go',
    'py' || 'pyi' => 'python',
    'rs' => 'rust',
    'swift' => 'swift',
    'kt' => 'kotlin',
    'h' || 'm' || 'mm' => 'objectivec',
    _ => 'dart',
  };
}

/// Stable IDs are file::qualifiedName#kind; source offsets are never IDs.
class GraphNode {
  final String id, name, kind, file, qualifiedName;
  final int line, endLine, offset, length;
  final String? parent;
  final List<String> tags;
  final bool synthetic;
  const GraphNode({
    required this.id,
    required this.name,
    required this.kind,
    required this.file,
    required this.qualifiedName,
    required this.line,
    required this.endLine,
    required this.offset,
    required this.length,
    this.parent,
    this.tags = const [],
    this.synthetic = false,
  });
  Map<String, dynamic> compact() => {
    'id': id,
    'kind': kind,
    'name': name,
    'file': file,
    'line': line,
    if (tags.isNotEmpty) 'tags': tags,
    if (synthetic) 'synthetic': true,
  };
  Map<String, dynamic> toJson() => {
    ...compact(),
    'q': qualifiedName,
    'end': endLine,
    'offset': offset,
    'length': length,
    if (parent != null) 'parent': parent,
  };
  factory GraphNode.fromJson(Map<String, dynamic> j) => GraphNode(
    id: j['id'],
    name: j['name'],
    kind: j['kind'],
    file: j['file'],
    qualifiedName: j['q'],
    line: j['line'],
    endLine: j['end'],
    offset: j['offset'],
    length: j['length'],
    parent: j['parent'],
    tags: (j['tags'] as List? ?? []).cast<String>(),
    synthetic: j['synthetic'] ?? false,
  );
}

class GraphEdge {
  final String source, target, kind, file, confidence;
  final int line, offset;
  const GraphEdge(
    this.source,
    this.target,
    this.kind,
    this.file,
    this.line,
    this.offset, {
    this.confidence = 'resolved',
  });
  String get key => '$source|$target|$kind|$file|$offset';
  Map<String, dynamic> toJson() => {
    'source': source,
    'target': target,
    'kind': kind,
    'file': file,
    'line': line,
    'offset': offset,
    'confidence': confidence,
  };
  factory GraphEdge.fromJson(Map<String, dynamic> j) => GraphEdge(
    j['source'],
    j['target'],
    j['kind'],
    j['file'],
    j['line'],
    j['offset'],
    confidence: j['confidence'] ?? 'resolved',
  );
}

class FileRecord {
  final String file, hash;
  String get language => languageFor(file);
  final List<GraphNode> nodes;
  final List<GraphEdge> edges;
  final List<String> dependencies;
  final List<Map<String, dynamic>> diagnostics;
  final int unresolvedCalls;
  const FileRecord({
    required this.file,
    required this.hash,
    required this.nodes,
    required this.edges,
    required this.dependencies,
    this.diagnostics = const [],
    this.unresolvedCalls = 0,
  });
  Map<String, dynamic> toJson() => {
    'file': file,
    'hash': hash,
    'nodes': nodes.map((n) => n.toJson()).toList(),
    'edges': edges.map((e) => e.toJson()).toList(),
    'dependencies': dependencies,
    'diagnostics': diagnostics,
    'unresolvedCalls': unresolvedCalls,
  };
  factory FileRecord.fromJson(Map<String, dynamic> j) => FileRecord(
    file: j['file'],
    hash: j['hash'],
    nodes: (j['nodes'] as List)
        .map((n) => GraphNode.fromJson(Map<String, dynamic>.from(n)))
        .toList(),
    edges: (j['edges'] as List)
        .map((e) => GraphEdge.fromJson(Map<String, dynamic>.from(e)))
        .toList(),
    dependencies: (j['dependencies'] as List).cast<String>(),
    diagnostics: (j['diagnostics'] as List)
        .map((d) => Map<String, dynamic>.from(d))
        .toList(),
    unresolvedCalls: j['unresolvedCalls'] ?? 0,
  );
}
