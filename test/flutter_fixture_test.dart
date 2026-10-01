import 'dart:io';
import 'package:dart_codegraph/dart_codegraph.dart';
import 'package:test/test.dart';

void main() {
  final fixture = Directory('examples/flutter_fixture').absolute.path;
  final configured = File(
    '$fixture/.dart_tool/package_config.json',
  ).existsSync();
  test(
    'real Flutter, Bloc, Riverpod, Freezed, Route and GetIt classifications',
    () async {
      final indexer = RepositoryIndexer(GraphConfig(root: fixture));
      final report = await indexer.refresh(force: true);
      final graph = GraphQuery(report.snapshot, indexer.config);
      expect(
        graph.resolve('HomeScreen').tags,
        containsAll(['Widget', 'Screen']),
      );
      expect(graph.resolve('UserCubit').tags, contains('Cubit'));
      expect(
        graph.resolve('userRepositoryProvider').tags,
        contains('Provider'),
      );
      expect(graph.resolve('homeRoute').tags, contains('Route'));
      expect(graph.resolve('User').tags, contains('Freezed'));
      expect(
        graph.resolve('registerServices').tags,
        contains('GetItRegistration'),
      );
      expect(
        graph.resolve('MemoryUserRepository').tags,
        contains('Repository'),
      );
      expect(graph.resolve('LoadUserUseCase').tags, contains('UseCase'));
      expect(
        graph.snapshot.files.values
            .expand((r) => r.diagnostics)
            .where((d) => d['severity'] == 'error'),
        isEmpty,
      );
      expect(
        graph.affected('UserRepository', depth: 12)['affected_files'],
        contains('lib/main.dart'),
      );
      expect(
        graph.relations(
          'registerServices',
          direction: 'out',
          kinds: {'registers'},
        )['total'],
        2,
      );
      final disabled = RepositoryIndexer(
        GraphConfig(root: fixture, flutter: false),
      );
      final plain = GraphQuery(
        (await disabled.refresh()).snapshot,
        disabled.config,
      );
      expect(plain.nodes.values.expand((n) => n.tags), isEmpty);
    },
    skip: configured
        ? false
        : 'Run flutter pub get in examples/flutter_fixture to enable the real Flutter integration test.',
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
