import 'dart:io';
import 'package:analyzer/dart/analysis/analysis_context_collection.dart';
import 'package:analyzer/dart/analysis/results.dart';
import 'package:path/path.dart' as p;
import 'package:polycodegraph_dart_provider/src/analysis/extractor.dart';
import 'package:polycodegraph_dart_provider/src/config.dart';
import 'package:test/test.dart';

void main() {
  test(
    'intent bindings preserve primitive graph and exclude DTO homonyms',
    () async {
      final root = Directory.systemTemp.createTempSync('intent bindings ');
      addTearDown(() => root.deleteSync(recursive: true));
      File(p.join(root.path, 'domain.dart')).writeAsStringSync('''
class Presenza {
  final int data;
  Presenza({required this.data});
  int get current => data;
  set current(int value) {}
}
class Dto {
  final int data;
  Dto({required this.data});
  Map<String, int> toJson() => {'data': data};
}
int read(Presenza entity) {
  final p = Presenza(data: 1);
  final dto = Dto(data: 2);
  return entity.data + p.current + dto.data;
}
''');
      final config = GraphConfig(root: root.path);
      final contexts = AnalysisContextCollection(includedPaths: [config.root]);
      try {
        final path = config.safePath('domain.dart');
        final unit =
            await contexts.contextFor(path).currentSession.getResolvedUnit(path)
                as ResolvedUnitResult;
        final record = extract(unit, config, 'hash');
        expect(
          record.diagnostics.where((d) => d['severity'] == 'error'),
          isEmpty,
        );
        final relations = (record.intent['relations'] as List)
            .cast<Map<String, dynamic>>();
        final binding = relations.singleWhere(
          (e) =>
              e['kind'] == 'binds_field' &&
              e['target'] == 'domain.dart::Presenza.data#field',
        );
        expect(binding['source'], contains('Presenza.new.data'));
        expect(
          relations.where(
            (e) =>
                e['kind'] == 'parameter_reference' &&
                e['target'] == binding['source'],
          ),
          hasLength(1),
        );
        expect(
          relations.where(
            (e) =>
                e['kind'] == 'binds_field' &&
                e['target'] == 'domain.dart::Dto.data#field',
          ),
          hasLength(1),
        );
        expect(
          relations.where((e) => e['kind'] == 'accessor_pair'),
          hasLength(2),
        );
        expect(record.nodes.where((n) => n.kind == 'parameter'), isEmpty);
        expect(
          record.edges.where(
            (e) => ['binds_field', 'parameter_reference'].contains(e.kind),
          ),
          isEmpty,
        );
        expect(record.intent['capabilities'], contains('parameter_bindings'));
        final ast = record.intent['ast'] as Map<String, dynamic>;
        expect(ast['version'], 1);
        expect((ast['statements'] as List), isNotEmpty);
        expect(
          (ast['bindings'] as List).where((b) => b['name'] == 'entity'),
          hasLength(1),
        );
        final entity = (ast['bindings'] as List).singleWhere(
          (b) => b['name'] == 'entity',
        );
        expect(
          (ast['uses'] as List).where((u) => u['binding'] == entity['id']),
          isNotEmpty,
        );
        expect(
          (ast['controls'] as List).where((e) => e['kind'] == 'return'),
          isNotEmpty,
        );
      } finally {
        await contexts.dispose();
      }
    },
  );
}
