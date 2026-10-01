import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as p;
import 'package:polycodegraph/polycodegraph.dart';
import 'package:test/test.dart';
import 'support.dart';

void main() {
  final providers = Directory('providers').absolute.path;
  final initialHealth = ExternalProviders(
    GraphConfig(root: '.', providersPath: providers),
  ).doctor();
  final ios =
      Platform.isMacOS &&
      File('/usr/bin/xcrun').existsSync() &&
      (initialHealth['objectivec'] as Map)['available'] == true &&
      (initialHealth['swift'] as Map)['available'] == true;
  if (Platform.environment['POLYCODEGRAPH_REQUIRE_IOS'] == '1' && !ios) {
    throw StateError('iOS validation requires macOS with Xcode');
  }
  test(
    'real UIKit and Objective-C bridging header resolve on the iOS simulator SDK',
    () async {
      final repo = Directory.systemTemp.createTempSync(
        'polycodegraph iOS SDK ',
      );
      addTearDown(() => repo.deleteSync(recursive: true));
      copyTree(Directory('test/fixtures/ios_sdk'), repo);
      Future<String> xcrun(List<String> args) async {
        final result = await Process.run('/usr/bin/xcrun', args);
        if (result.exitCode != 0) throw StateError('xcrun: ${result.stderr}');
        return '${result.stdout}'.trim();
      }

      final sdk = await xcrun(['--sdk', 'iphonesimulator', '--show-sdk-path']);
      final swiftc = await xcrun(['--find', 'swiftc']);
      final clang = await xcrun(['--find', 'clang']);
      final resourceResult = await Process.run(clang, ['-print-resource-dir']);
      expect(resourceResult.exitCode, 0);
      final resourceDir = '${resourceResult.stdout}'.trim();
      final library = p.normalize(
        p.join(p.dirname(clang), '..', 'lib', 'libclang.dylib'),
      );
      expect(File(library).existsSync(), isTrue, reason: library);
      final target =
          '${Platform.version.contains('arm64') ? 'arm64' : 'x86_64'}-apple-ios17.0-simulator';
      File(p.join(repo.path, 'polycodegraph.mobile.json')).writeAsStringSync(
        jsonEncode({
          'swift': [
            {
              'name': 'IOSFixture',
              'files': ['*.swift'],
              'sdk': sdk,
              'target': target,
              'bridging_header': 'Domain.h',
            },
          ],
          'objectivec': [
            {
              'files': ['*.h', '*.m'],
              'sdk': sdk,
              'target': target,
              'arc': true,
              'resource_dir': resourceDir,
            },
          ],
        }),
      );
      final config = GraphConfig(
        root: repo.path,
        providersPath: providers,
        swiftcPath: swiftc,
        libclangPath: library,
      );
      final graph = GraphQuery(
        (await RepositoryIndexer(config).refresh()).snapshot,
        config,
      );
      final errors = graph.snapshot.files.values
          .expand((f) => f.diagnostics)
          .where((d) => d['severity'] == 'error')
          .toList();
      expect(errors, isEmpty, reason: '$errors');
      expect(
        graph.search('Screen', language: 'swift', kind: 'class')['total'],
        1,
      );
      expect(
        graph.search('bridge', language: 'swift', kind: 'function')['total'],
        1,
      );
      expect(
        graph.search(
          'ProductViewController',
          language: 'objectivec',
          tag: 'view_controller',
        )['total'],
        greaterThan(0),
      );
      final reload = graph.nodes.values.singleWhere(
        (n) => n.name == 'reload' && n.file == 'Screen.swift',
      );
      expect(
        (graph.relations(reload.id, direction: 'out', kinds: {'calls'})['rows']
                as List)
            .any((r) => (r[0] as String).contains('SwiftRepository.fetch')),
        isTrue,
      );
      final method = graph.nodes.values.singleWhere(
        (n) => n.name == 'reload:' && n.file == 'Domain.m',
      );
      expect(
        graph.relations(method.id, direction: 'out', kinds: {'calls'})['total'],
        1,
      );
    },
    timeout: const Timeout(Duration(minutes: 2)),
    skip: ios ? false : 'iOS UIKit SDK checks require macOS with Xcode',
  );

  final sdkRoot =
      Platform.environment['ANDROID_HOME'] ??
      Platform.environment['ANDROID_SDK_ROOT'];
  final candidates = <File>[];
  if (sdkRoot != null && Directory(p.join(sdkRoot, 'platforms')).existsSync()) {
    for (final directory in Directory(
      p.join(sdkRoot, 'platforms'),
    ).listSync().whereType<Directory>()) {
      final jar = File(p.join(directory.path, 'android.jar'));
      if (jar.existsSync()) candidates.add(jar);
    }
    candidates.sort((a, b) => b.path.compareTo(a.path));
  }
  final health = ExternalProviders(
    GraphConfig(
      root: '.',
      providersPath: providers,
      javaPath: Platform.environment['JAVA'] ?? 'java',
    ),
  ).doctor();
  final android =
      candidates.isNotEmpty && (health['kotlin'] as Map)['available'] == true;
  if (Platform.environment['POLYCODEGRAPH_REQUIRE_ANDROID'] == '1' &&
      !android) {
    throw StateError('Android SDK platform and Kotlin adapter required');
  }
  test(
    'real Android SDK classpath resolves Activity and local typed calls',
    () async {
      final repo = Directory.systemTemp.createTempSync(
        'polycodegraph Android SDK ',
      );
      addTearDown(() => repo.deleteSync(recursive: true));
      copyTree(Directory('test/fixtures/android_sdk'), repo);
      File(p.join(repo.path, 'polycodegraph.mobile.json')).writeAsStringSync(
        jsonEncode({
          'kotlin': [
            {
              'name': 'AndroidFixture',
              'files': ['*.kt'],
              'classpath': [candidates.first.path],
            },
          ],
        }),
      );
      final config = GraphConfig(
        root: repo.path,
        providersPath: providers,
        javaPath: Platform.environment['JAVA'] ?? 'java',
      );
      final graph = GraphQuery(
        (await RepositoryIndexer(config).refresh()).snapshot,
        config,
      );
      final errors = graph.snapshot.files.values
          .expand((f) => f.diagnostics)
          .where((d) => d['severity'] == 'error')
          .toList();
      expect(errors, isEmpty, reason: '$errors');
      expect(
        graph.search(
          'MainActivity',
          language: 'kotlin',
          kind: 'class',
        )['total'],
        1,
      );
      final reload = graph.nodes.values.singleWhere(
        (n) => n.name == 'reload' && n.kind == 'method',
      );
      expect(
        (graph.relations(reload.id, direction: 'out', kinds: {'calls'})['rows']
                as List)
            .any((r) => (r[0] as String).contains('Repository.fetch')),
        isTrue,
      );
    },
    skip: android
        ? false
        : 'Set ANDROID_HOME to a prepared Android SDK and prepare Kotlin',
  );
}
