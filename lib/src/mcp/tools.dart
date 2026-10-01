import '../config.dart';
import '../graph/query.dart';
import '../index/indexer.dart';
import '../providers/providers.dart';

class ToolSpec {
  final String name, description;
  final Map<String, dynamic> properties;
  final List<String> required;
  final bool readOnly;
  const ToolSpec(
    this.name,
    this.description,
    this.properties, {
    this.required = const [],
    this.readOnly = true,
  });
  Map<String, dynamic> toJson() => {
    'name': name,
    'description': description,
    'inputSchema': {
      'type': 'object',
      'properties': properties,
      'required': required,
      'additionalProperties': false,
    },
    'annotations': {
      'readOnlyHint': readOnly,
      'destructiveHint': false,
      'idempotentHint': true,
      'openWorldHint': false,
    },
  };
  void validate(Map<String, dynamic> args) {
    for (final key in required) {
      if (!args.containsKey(key)) {
        throw QueryException('Missing argument: $key');
      }
    }
    for (final entry in args.entries) {
      final schema = properties[entry.key] as Map<String, dynamic>?;
      if (schema == null) {
        throw QueryException('Unknown argument: ${entry.key}');
      }
      final v = entry.value;
      final valid = switch (schema['type']) {
        'string' => v is String,
        'integer' => v is int,
        'boolean' => v is bool,
        'array' => v is List && v.every((e) => e is String),
        _ => false,
      };
      if (!valid) throw QueryException('Invalid type for ${entry.key}');
      if (v is int &&
          ((schema['minimum'] != null && v < schema['minimum']) ||
              (schema['maximum'] != null && v > schema['maximum']))) {
        throw QueryException('${entry.key} is out of range');
      }
      if (v is String &&
          (v.length > 4096 || (schema['minLength'] != null && v.isEmpty))) {
        throw QueryException('Invalid length for ${entry.key}');
      }
      if (schema['enum'] != null && !(schema['enum'] as List).contains(v)) {
        throw QueryException('Invalid value for ${entry.key}');
      }
      if (v is List && (v.length > 32 || v.any((s) => s.length > 128))) {
        throw QueryException('Too many or oversized relation kinds');
      }
    }
  }
}

class ToolRegistry {
  final RepositoryIndexer indexer;
  late final List<ToolSpec> tools = _specs(indexer.config);
  ToolRegistry(this.indexer);
  Future<Map<String, dynamic>> call(
    String name,
    Map<String, dynamic> args,
  ) async {
    final spec = tools.where((s) => s.name == name).firstOrNull;
    if (spec == null) throw QueryException('Unknown tool: $name');
    spec.validate(args);
    if (name == 'detect_changes') {
      final data = indexer.detectChanges();
      for (final key in ['changed', 'deleted', 'skipped']) {
        final values = data[key] as List;
        data['${key}_total'] = values.length;
        data[key] = values.take(indexer.config.maxResults).toList();
      }
      return data;
    }
    final report = await indexer.refresh(force: args['force'] == true);
    if (name == 'index_repository') {
      return report.toJson(limit: indexer.config.maxResults);
    }
    final q = GraphQuery(report.snapshot, indexer.config);
    final target = args['target'] as String?;
    final offset = args['offset'] as int? ?? 0, limit = args['limit'] as int?;
    switch (name) {
      case 'search_symbol':
      case 'search':
        return q.search(
          args['query'] as String,
          kind: args['kind'],
          tag: args['tag'],
          file: args['file'],
          language: args['language'],
          offset: offset,
          limit: limit,
        );
      case 'get_architecture':
        return q.architecture(limit: limit ?? 20);
      case 'status':
        return {
          ...q.architecture(limit: 5),
          'index': report.toJson(limit: indexer.config.maxResults),
          'provider_health': ExternalProviders(indexer.config).doctor(),
        };
      case 'callers':
        return q.relations(
          target!,
          direction: 'in',
          kinds: {'calls'},
          offset: offset,
          limit: limit,
        );
      case 'callees':
        return q.relations(
          target!,
          direction: 'out',
          kinds: {'calls'},
          offset: offset,
          limit: limit,
        );
      case 'references':
        return q.relations(
          target!,
          direction: 'in',
          kinds: {'references'},
          offset: offset,
          limit: limit,
        );
      case 'implementations':
        return q.implementations(target!, offset: offset, limit: limit);
      case 'dependencies':
        return q.dependencies(
          target!,
          direction: args['direction'] ?? 'out',
          offset: offset,
          limit: limit,
        );
      case 'neighbors':
        return q.relations(
          target!,
          direction: args['direction'] ?? 'both',
          kinds: (args['kinds'] as List?)?.cast<String>().toSet(),
          offset: offset,
          limit: limit,
        );
      case 'affected_by_change':
      case 'blast_radius':
        return q.affected(
          target!,
          depth: args['depth'] ?? 6,
          offset: offset,
          limit: limit,
        );
      case 'snippet':
        if (target == null && args['file'] == null) {
          throw QueryException('Provide target or file');
        }
        return q.snippet(
          target: target,
          file: args['file'],
          startLine: args['start_line'],
          endLine: args['end_line'],
          context: args['context'] ?? 2,
        );
      default:
        throw QueryException('Unknown tool');
    }
  }
}

List<ToolSpec> _specs(GraphConfig config) {
  const text = {'type': 'string'},
      target = {
        'type': 'string',
        'minLength': 1,
        'description':
            'Stable id, unambiguous qualified/name, or indexed relative file path.',
      };
  final pagination = {
    'offset': {'type': 'integer', 'minimum': 0},
    'limit': {'type': 'integer', 'minimum': 1, 'maximum': config.maxResults},
  };
  final relation = {'target': target, ...pagination};
  final search = {
    'query': text,
    'kind': text,
    'tag': text,
    'file': text,
    'language': {
      'type': 'string',
      'enum': [
        'dart',
        'typescript',
        'javascript',
        'java',
        'go',
        'python',
        'rust',
        'swift',
        'objectivec',
        'kotlin',
      ],
    },
    ...pagination,
  };
  final impact = {
    ...relation,
    'depth': {'type': 'integer', 'minimum': 1, 'maximum': 32},
  };
  return [
    ToolSpec(
      'index_repository',
      'Refresh the index and report changed/deleted/reindexed files. Writes repository cache only.',
      {
        'force': {'type': 'boolean'},
      },
      readOnly: false,
    ),
    ToolSpec(
      'status',
      'Fresh index health, diagnostics, graph counts and precision limitations.',
      const {},
    ),
    ToolSpec(
      'detect_changes',
      'Report pending edits without rebuilding the index.',
      const {},
    ),
    ToolSpec(
      'get_architecture',
      'Compact architecture counts, Flutter discovery tags and most referenced symbols.',
      {'limit': pagination['limit']},
    ),
    ToolSpec(
      'search_symbol',
      'Search symbol names; returns compact rows and stable ids. Empty query lists symbols.',
      search,
      required: ['query'],
    ),
    ToolSpec('search', 'Alias of search_symbol.', search, required: ['query']),
    ToolSpec(
      'callers',
      'Statically resolved incoming call sites; dynamic dispatch may be incomplete.',
      relation,
      required: ['target'],
    ),
    ToolSpec(
      'callees',
      'Statically resolved outgoing call sites; no inferred callback targets.',
      relation,
      required: ['target'],
    ),
    ToolSpec(
      'references',
      'Incoming resolved symbol references with source locations.',
      relation,
      required: ['target'],
    ),
    ToolSpec(
      'implementations',
      'Transitive subtypes or overriding methods, including abstract declarations.',
      relation,
      required: ['target'],
    ),
    ToolSpec(
      'dependencies',
      'File dependencies from directives and resolved symbol edges.',
      {
        ...relation,
        'direction': {
          'type': 'string',
          'enum': ['in', 'out', 'both'],
        },
      },
      required: ['target'],
    ),
    ToolSpec(
      'neighbors',
      'Adjacent symbols and file directives; filter relation kinds and direction.',
      {
        ...relation,
        'direction': {
          'type': 'string',
          'enum': ['in', 'out', 'both'],
        },
        'kinds': {
          'type': 'array',
          'items': {'type': 'string'},
        },
      },
      required: ['target'],
    ),
    ToolSpec(
      'affected_by_change',
      'Conservative reverse dependency closure with distance and reason. Inspect depth_limited.',
      impact,
      required: ['target'],
    ),
    ToolSpec(
      'blast_radius',
      'Alias of affected_by_change.',
      impact,
      required: ['target'],
    ),
    ToolSpec(
      'snippet',
      'Read only a bounded symbol/line window from an indexed source file.',
      {
        'target': target,
        'file': text,
        'start_line': {'type': 'integer', 'minimum': 1},
        'end_line': {'type': 'integer', 'minimum': 1},
        'context': {'type': 'integer', 'minimum': 0, 'maximum': 20},
      },
    ),
  ];
}
