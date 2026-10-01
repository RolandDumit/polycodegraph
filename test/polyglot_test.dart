import 'dart:io';
import 'support.dart';
import 'package:path/path.dart' as p;
import 'package:polycodegraph/polycodegraph.dart';
import 'package:test/test.dart';

List<String> ids(Map<String, dynamic> result) =>
    (result['rows'] as List).map((row) => row[0] as String).toList();

void main() {
  final providers = Directory('providers').absolute.path;
  final options = GraphConfig(
    root: '.',
    providersPath: providers,
    javaPath: Platform.environment['JAVA'] ?? 'java',
    nodePath: Platform.environment['NODE'] ?? 'node',
    goPath: Platform.environment['GO'] ?? 'go',
  );
  final health = ExternalProviders(options).doctor();
  final available = [
    'typescript_javascript',
    'java',
    'go',
  ].every((language) => (health[language] as Map)['available'] == true);
  final required =
      Platform.environment['POLYCODEGRAPH_REQUIRE_PROVIDERS'] == '1';
  if (required && !available) {
    throw StateError('Required providers unavailable: $health');
  }

  group(
    'compiler-backed polyglot graph',
    () {
      late Directory repo;
      late RepositoryIndexer indexer;
      late GraphQuery graph;
      setUpAll(() async {
        repo = Directory.systemTemp.createTempSync('polycodegraph mixed ');
        final source = Directory('test/fixtures/polyglot').absolute;
        copyTree(source, repo);
        File(
          p.join(repo.path, 'dart_side.dart'),
        ).writeAsStringSync('class DartIndependent {}');
        indexer = RepositoryIndexer(
          GraphConfig(
            root: repo.path,
            providersPath: providers,
            javaPath: options.javaPath,
            nodePath: options.nodePath,
            goPath: options.goPath,
          ),
        );
        graph = GraphQuery((await indexer.refresh()).snapshot, indexer.config);
      });
      tearDownAll(() async {
        if (repo.existsSync()) await repo.delete(recursive: true);
      });

      test('all five languages produce declarations with healthy bindings', () {
        expect(graph.architecture()['languages'], containsPair('dart', 1));
        expect(
          (graph.architecture()['languages'] as Map).keys,
          containsAll(['dart', 'typescript', 'javascript', 'java', 'go']),
        );
        final errors = graph.snapshot.files.values
            .expand((f) => f.diagnostics)
            .where((d) => d['severity'] == 'error')
            .toList();
        expect(errors, isEmpty, reason: '$errors');
        expect(
          graph.search(
            'MemoryRepository',
            language: 'typescript',
            kind: 'class',
          )['total'],
          1,
        );
        expect(
          graph.search(
            'MemoryRepository',
            language: 'go',
            kind: 'struct',
          )['total'],
          1,
        );
        expect(
          graph.search(
            'MemoryRepository',
            language: 'java',
            kind: 'class',
          )['total'],
          1,
        );
      });
      test(
        'TypeScript aliases, interface calls and JavaScript imports resolve',
        () {
          const contract = 'ts/domain.ts::Repository.fetch#method';
          expect(
            ids(
              graph.relations(
                'ts/use.ts::load#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            contains(contract),
          );
          expect(
            ids(
              graph.relations(
                'ts/use.ts::decoy#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            isNot(contains(contract)),
          );
          expect(
            ids(graph.implementations(contract)),
            contains('ts/domain.ts::MemoryRepository.fetch#method'),
          );
          expect(
            ids(
              graph.relations(
                'ts/use.ts::run#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            contains('ts/domain.ts::helper#function'),
          );
          expect(
            ids(
              graph.relations(
                'ts/consumer.js::javascriptConsumer#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            contains('ts/domain.ts::helper#function'),
          );
          expect(
            ids(
              graph.relations(contract, direction: 'in', kinds: {'references'}),
            ),
            contains('ts/use.ts::load#function'),
          );
          expect(
            graph.affected(contract, depth: 12)['affected_files'],
            contains('ts/use.ts'),
          );
          expect(
            ids(
              graph.relations(
                'ts/use.ts::run#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            contains('ts/domain.ts::MemoryRepository.new#constructor'),
          );
          expect(
            ids(
              graph.relations(
                'ts/alt/use.ts::altRun#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            contains('ts/domain.ts::MemoryRepository.new#constructor'),
          );
          expect(
            ids(graph.dependencies('ts/use.ts')),
            contains('ts/domain.ts'),
          );
          expect(
            ids(
              graph.relations(
                'ts/common.cjs::commonJsConsumer#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            contains('ts/domain.ts::helper#function'),
          );
          expect(
            ids(
              graph.relations(
                'ts/common.cjs',
                direction: 'out',
                kinds: {'imports'},
              ),
            ),
            contains('ts/domain.ts::file'),
          );
        },
      );
      test('Java overloaded members, constructors and overrides are distinct', () {
        const contract =
            'java/demo/Repository.java::demo.Repository.fetch()#method';
        expect(
          ids(
            graph.relations(
              'java/demo/App.java::demo.App.load(demo.Repository)#method',
              direction: 'out',
              kinds: {'calls'},
            ),
          ),
          contains(contract),
        );
        expect(
          ids(
            graph.relations(
              'java/demo/App.java::demo.App.decoy()#method',
              direction: 'out',
              kinds: {'calls'},
            ),
          ),
          isNot(contains(contract)),
        );
        expect(
          ids(graph.implementations(contract)),
          contains(
            'java/demo/MemoryRepository.java::demo.MemoryRepository.fetch()#method',
          ),
        );
        expect(
          ids(
            graph.relations(
              'java/demo/App.java::demo.App.overload()#method',
              direction: 'out',
              kinds: {'calls'},
            ),
          ),
          contains(
            'java/demo/MemoryRepository.java::demo.MemoryRepository.fetch(int)#method',
          ),
        );
        expect(
          graph.affected(contract, depth: 12)['affected_files'],
          contains('java/demo/App.java'),
        );
        expect(
          graph.snippet(target: contract, context: 0)['text'],
          contains('String fetch()'),
        );
      });
      test(
        'Go aliases, implicit implementations and static interface calls resolve',
        () {
          const contract = 'go/domain/domain.go::Repository.Fetch#method';
          expect(
            ids(
              graph.relations(
                'go/app/app.go::Load#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            contains(contract),
          );
          expect(
            ids(
              graph.relations(
                'go/app/app.go::Decoy#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            isNot(contains(contract)),
          );
          expect(
            ids(graph.implementations(contract)),
            contains('go/domain/memory.go::MemoryRepository.Fetch#method'),
          );
          expect(
            ids(
              graph.implementations(
                'go/domain/domain.go::Repository#interface',
              ),
            ),
            contains('go/domain/domain.go::MemoryRepository#struct'),
          );
          expect(
            ids(
              graph.relations(
                'go/app/app.go::Run#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            contains('go/domain/domain.go::Helper#function'),
          );
          expect(
            graph.affected(contract, depth: 12)['affected_files'],
            contains('go/app/app.go'),
          );
          expect(
            ids(
              graph.relations(
                'go/domain/domain.go::MemoryRepository#struct',
                direction: 'out',
                kinds: {'contains'},
              ),
            ),
            contains('go/domain/memory.go::MemoryRepository.Fetch#method'),
          );
          expect(
            ids(graph.dependencies('go/app/app.go')),
            contains('go/domain/domain.go'),
          );
        },
      );
      test(
        'mixed graphs remain language-scoped and reuse warm snapshots',
        () async {
          for (final edge in graph.edges) {
            if (edge.kind != 'contains') {
              expect(
                languageFor(
                  graph.nodes[edge.source]!.file,
                ).replaceAll('javascript', 'typescript'),
                languageFor(
                  graph.nodes[edge.target]!.file,
                ).replaceAll('javascript', 'typescript'),
              );
            }
          }
          final warm = await indexer.refresh();
          expect(warm.reindexed, isEmpty);
          expect(warm.snapshot.generation, graph.snapshot.generation);
          final source = File(p.join(repo.path, 'ts/domain.ts'));
          source.writeAsStringSync(
            source.readAsStringSync().replaceAll('fetch()', 'retrieve()'),
          );
          final next = await indexer.refresh();
          expect(
            next.reindexed,
            containsAll(['ts/domain.ts', 'ts/use.ts', 'ts/consumer.js']),
          );
          expect(next.reindexed, isNot(contains('go/app/app.go')));
          final updated = GraphQuery(next.snapshot, indexer.config);
          expect(
            updated.search('Repository.fetch', language: 'typescript')['total'],
            0,
          );
          expect(
            ids(
              updated.relations(
                'ts/use.ts::load#function',
                direction: 'out',
                kinds: {'calls'},
              ),
            ),
            isEmpty,
          );
          expect(next.snapshot.files['ts/use.ts']!.diagnostics, isNotEmpty);
        },
      );

      test(
        'Java and Go semantic changes remove stale unchanged-consumer calls',
        () async {
          for (final change in [
            [
              'java/demo/Repository.java',
              'fetch()',
              'retrieve()',
              'java/demo/App.java::demo.App.load(demo.Repository)#method',
              'java/demo/App.java',
              'java/demo/Repository.java::demo.Repository.fetch()#method',
              'java',
            ],
            [
              'go/domain/domain.go',
              'Fetch() string',
              'Retrieve() string',
              'go/app/app.go::Load#function',
              'go/app/app.go',
              'go/domain/domain.go::Repository.Fetch#method',
              'go',
            ],
          ]) {
            final source = File(p.join(repo.path, change[0]));
            source.writeAsStringSync(
              source.readAsStringSync().replaceAll(change[1], change[2]),
            );
            final next = await indexer.refresh();
            expect(next.reindexed, contains(change[4]));
            final updated = GraphQuery(next.snapshot, indexer.config);
            expect(updated.search(change[5], language: change[6])['total'], 0);
            expect(
              ids(
                updated.relations(
                  change[3],
                  direction: 'out',
                  kinds: {'calls'},
                ),
              ),
              isEmpty,
            );
            expect(next.snapshot.files[change[4]]!.diagnostics, isNotEmpty);
          }
        },
      );
    },
    skip: available
        ? false
        : 'Install semantic adapters with tool/setup-providers.sh',
    timeout: const Timeout(Duration(minutes: 3)),
  );

  test(
    'missing adapter emits diagnostics while preserving Dart queries',
    () async {
      final repo = Directory.systemTemp.createTempSync(
        'polycodegraph-unavailable-',
      );
      addTearDown(() => repo.deleteSync(recursive: true));
      File(p.join(repo.path, 'one.dart')).writeAsStringSync('class Healthy {}');
      File(
        p.join(repo.path, 'one.ts'),
      ).writeAsStringSync('export class Unavailable {}');
      final config = GraphConfig(
        root: repo.path,
        providersPath: p.join(repo.path, 'missing'),
        nodePath: p.join(repo.path, 'missing-node'),
      );
      final snapshot = (await RepositoryIndexer(config).refresh()).snapshot;
      expect(
        GraphQuery(snapshot, config).search('Healthy', kind: 'class')['total'],
        1,
      );
      expect(
        snapshot.files['one.ts']!.diagnostics.single['code'],
        'provider_unavailable',
      );
    },
  );
}
