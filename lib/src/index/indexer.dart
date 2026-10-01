import 'dart:convert';
import 'dart:io';
import 'package:analyzer/dart/analysis/analysis_context_collection.dart';
import 'package:analyzer/dart/analysis/results.dart';
import 'package:crypto/crypto.dart';
import 'package:glob/glob.dart';
import 'package:path/path.dart' as p;
import '../analysis/extractor.dart';
import '../providers/providers.dart';
import '../config.dart';
import '../graph/model.dart';
import 'store.dart';

String digest(String value) => sha256.convert(utf8.encode(value)).toString();

class IndexReport {
  final GraphSnapshot snapshot;
  final List<String> changed, deleted, reindexed;
  final bool full;
  IndexReport(
    this.snapshot,
    this.changed,
    this.deleted,
    this.reindexed,
    this.full,
  );
  Map<String, dynamic> toJson({int? limit}) => {
    'generation': snapshot.generation,
    'files': snapshot.files.length,
    'changed': limit == null ? changed : changed.take(limit).toList(),
    'changed_total': changed.length,
    'deleted': limit == null ? deleted : deleted.take(limit).toList(),
    'deleted_total': deleted.length,
    'reindexed': limit == null ? reindexed : reindexed.take(limit).toList(),
    'reindexed_total': reindexed.length,
    'full': full,
    'skipped': limit == null
        ? snapshot.skipped
        : snapshot.skipped.take(limit).toList(),
    'skipped_total': snapshot.skipped.length,
  };
}

class _Scan {
  final Map<String, String> hashes;
  final String environment;
  final List<String> skipped;
  _Scan(this.hashes, this.environment, this.skipped);
}

class RepositoryIndexer {
  final GraphConfig config;
  late final IndexStore store = IndexStore(config);
  GraphSnapshot? snapshot;
  static final Map<String, Future<void>> _queues = {};
  RepositoryIndexer(this.config);
  Future<IndexReport> refresh({bool force = false}) {
    final key = config.cachePath;
    final task = (_queues[key] ?? Future<void>.value()).then(
      (_) => store.locked(() => _refresh(force)),
    );
    late final Future<void> completion;
    void release() {
      if (identical(_queues[key], completion)) _queues.remove(key);
    }

    completion = task.then<void>(
      (_) {
        release();
      },
      onError: (Object _, StackTrace trace) {
        release();
      },
    );
    _queues[key] = completion;
    return task;
  }

  GraphSnapshot? load() => snapshot = store.read();
  _Scan _scan() {
    final includes = config.include.map(Glob.new).toList();
    final excludes = config.exclude.map(Glob.new).toList();
    final hashes = <String, String>{};
    final environment = <String, String>{};
    final skipped = <String>[];
    void walk(Directory directory) {
      final entries = directory.listSync(followLinks: false)
        ..sort((a, b) => a.path.compareTo(b.path));
      for (final entry in entries) {
        final rel = config.relative(entry.path);
        if (entry is Link) {
          skipped.add(rel);
          continue;
        }
        if (entry is Directory) {
          if ({
                '.git',
                '.polycodegraph',
                'build',
                'node_modules',
                'vendor',
                'target',
                'dist',
              }.contains(p.basename(entry.path)) ||
              p.equals(entry.path, config.cachePath)) {
            continue;
          }
          if (p.basename(entry.path) == '.dart_tool') {
            final packageFile = File(p.join(entry.path, 'package_config.json'));
            if (packageFile.existsSync() &&
                FileSystemEntity.typeSync(
                      packageFile.path,
                      followLinks: false,
                    ) !=
                    FileSystemEntityType.link) {
              environment[config.relative(packageFile.path)] = sha256
                  .convert(packageFile.readAsBytesSync())
                  .toString();
            }
            continue;
          }
          walk(entry);
          continue;
        }
        if (entry is! File) continue;
        if ({
              'pubspec.yaml',
              'pubspec.lock',
              'analysis_options.yaml',
              'package.json',
              'package-lock.json',
              'pnpm-lock.yaml',
              'yarn.lock',
              'go.mod',
              'go.sum',
              'go.work',
              'go.work.sum',
              'pom.xml',
              'build.gradle',
              'build.gradle.kts',
              'settings.gradle',
              'settings.gradle.kts',
              'gradle.properties',
            }.contains(p.basename(entry.path)) ||
            p.basename(entry.path).startsWith('tsconfig') ||
            p.basename(entry.path) == 'jsconfig.json') {
          environment[rel] = sha256.convert(entry.readAsBytesSync()).toString();
        }
        if (!{
          'dart',
          'ts',
          'tsx',
          'js',
          'jsx',
          'mjs',
          'cjs',
          'java',
          'go',
        }.contains(p.extension(entry.path).replaceFirst('.', ''))) {
          continue;
        }
        if (entry.lengthSync() > config.maxFileBytes) {
          skipped.add(rel);
          continue;
        }
        final hash = sha256.convert(entry.readAsBytesSync()).toString();
        if (includes.any((g) => g.matches(rel)) &&
            !excludes.any((g) => g.matches(rel))) {
          hashes[rel] = hash;
        } else {
          environment[rel] = hash;
        }
      }
    }

    walk(Directory(config.root));
    environment['provider_runtime'] = ExternalProviders(config).fingerprint;
    return _Scan(hashes, digest(jsonEncode(environment)), skipped..sort());
  }

  Future<IndexReport> _refresh(bool force) async {
    for (var attempt = 0; attempt < 3; attempt++) {
      final old = store.read();
      final scan = _scan();
      final changed =
          scan.hashes.keys
              .where((f) => old?.files[f]?.hash != scan.hashes[f])
              .toList()
            ..sort();
      final deleted =
          (old?.files.keys ?? <String>[])
              .where((f) => !scan.hashes.containsKey(f))
              .toList()
            ..sort();
      final full =
          force ||
          old == null ||
          old.environment != scan.environment ||
          deleted.isNotEmpty ||
          changed.any((f) => !old.files.containsKey(f));
      final affected = full ? scan.hashes.keys.toSet() : changed.toSet();
      if (!full && affected.isNotEmpty) {
        var grew = true;
        while (grew) {
          grew = false;
          for (final record in old.files.values) {
            if (!affected.contains(record.file) &&
                record.dependencies.any(affected.contains)) {
              affected.add(record.file);
              grew = true;
            }
          }
        }
      }
      // Compiler bindings depend on project/package scopes, including implicit imports.
      // Rebuild an affected non-Dart language scope conservatively.
      final languages = affected
          .where((f) => languageFor(f) != 'dart')
          .map(languageFor)
          .toSet();
      affected.addAll(
        scan.hashes.keys.where((f) => languages.contains(languageFor(f))),
      );
      if (languages.contains('typescript') ||
          languages.contains('javascript')) {
        affected.addAll(
          scan.hashes.keys.where(
            (f) => {'typescript', 'javascript'}.contains(languageFor(f)),
          ),
        );
      }
      final reindexed = affected.toList()..sort();
      if (reindexed.isEmpty &&
          deleted.isEmpty &&
          old != null &&
          !full &&
          _sameList(scan.skipped, old.skipped)) {
        snapshot = old;
        return IndexReport(old, changed, deleted, [], false);
      }
      final files = <String, FileRecord>{if (!full) ...old.files};
      final dartFiles = reindexed
          .where((f) => languageFor(f) == 'dart')
          .toList();
      final collection = dartFiles.isEmpty
          ? null
          : AnalysisContextCollection(
              includedPaths: [
                config.root,
                ...scan.hashes.keys
                    .where((f) => languageFor(f) == 'dart')
                    .map(config.safePath),
              ],
              sdkPath: config.sdkPath,
              excludedPaths: [
                config.cachePath,
                p.join(config.root, 'build'),
                p.join(config.root, '.git'),
              ],
            );
      try {
        for (final file in dartFiles) {
          final absolute = config.safePath(file);
          final result = await collection!
              .contextFor(absolute)
              .currentSession
              .getResolvedUnit(absolute);
          if (result is! ResolvedUnitResult) {
            throw StateError(
              'Analyzer could not resolve $file (${result.runtimeType})',
            );
          }
          if (digest(result.content) != scan.hashes[file]) {
            files.clear();
            break;
          }
          files[file] = extract(result, config, scan.hashes[file]!);
        }
      } finally {
        await collection?.dispose();
      }
      files.addAll(
        await ExternalProviders(config).extract({
          for (final f in reindexed.where((f) => languageFor(f) != 'dart'))
            f: scan.hashes[f]!,
        }),
      );
      final after = _scan();
      if (files.length != scan.hashes.length ||
          !_sameMap(scan.hashes, after.hashes) ||
          scan.environment != after.environment) {
        continue;
      }
      final generation = digest(
        jsonEncode({
          'files': scan.hashes,
          'environment': scan.environment,
          'config': config.fingerprint,
          'skipped': scan.skipped,
        }),
      ).substring(0, 20);
      final next = GraphSnapshot(
        root: config.root,
        fingerprint: config.fingerprint,
        environment: scan.environment,
        generation: generation,
        files: files,
        skipped: scan.skipped,
      );
      await store.write(next);
      snapshot = next;
      return IndexReport(next, changed, deleted, reindexed, full);
    }
    throw StateError(
      'Repository changed repeatedly during indexing; retry when writes finish',
    );
  }

  Map<String, dynamic> detectChanges() {
    final old = store.read();
    final scan = _scan();
    return {
      'indexed': old != null,
      'changed':
          scan.hashes.keys
              .where((f) => old?.files[f]?.hash != scan.hashes[f])
              .toList()
            ..sort(),
      'deleted':
          (old?.files.keys ?? <String>[])
              .where((f) => !scan.hashes.containsKey(f))
              .toList()
            ..sort(),
      'environment_changed': old?.environment != scan.environment,
      'skipped': scan.skipped,
    };
  }
}

bool _sameMap(Map<String, String> a, Map<String, String> b) =>
    a.length == b.length && a.entries.every((e) => b[e.key] == e.value);
bool _sameList(List<String> a, List<String> b) =>
    a.length == b.length &&
    List.generate(a.length, (i) => a[i] == b[i]).every((e) => e);
