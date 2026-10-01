import 'dart:convert';
import 'dart:io';
import 'package:analyzer/dart/analysis/analysis_context_collection.dart';
import 'package:analyzer/dart/analysis/results.dart';
import 'package:path/path.dart' as p;
import 'package:polycodegraph_dart_provider/src/config.dart';
import 'package:polycodegraph_dart_provider/src/analysis/extractor.dart';

Future<void> main() async {
  try {
    final input =
        jsonDecode(await stdin.transform(utf8.decoder).join())
            as Map<String, dynamic>;
    final root = input['root'] as String,
        options = input['options'] as Map<String, dynamic>;
    final config = GraphConfig(
      root: root,
      flutter: options['flutter'] as bool? ?? true,
      sdkPath: options['sdk_path'] as String?,
    );
    final files = input['files'] as List;
    final emitted =
        (options['emit_files'] as List? ?? files.map((f) => f['file']).toList())
            .cast<String>()
            .toSet();
    final contexts = AnalysisContextCollection(
      includedPaths: [
        config.root,
        ...files.map((f) => config.safePath(f['file'])),
      ],
      sdkPath: config.sdkPath,
      excludedPaths: [
        config.cachePath,
        p.join(config.root, 'build'),
        p.join(config.root, '.git'),
      ],
    );
    try {
      final out = [];
      for (final f in files) {
        if (!emitted.contains(f['file'])) continue;
        final absolute = config.safePath(f['file']);
        final result = await contexts
            .contextFor(absolute)
            .currentSession
            .getResolvedUnit(absolute);
        if (result is! ResolvedUnitResult) {
          throw StateError('Analyzer could not resolve $absolute');
        }
        out.add(extract(result, config, f['hash']).toJson());
      }
      stdout.write(jsonEncode(out));
    } finally {
      await contexts.dispose();
    }
  } catch (e, st) {
    stderr.writeln('$e\n$st');
    exitCode = 1;
  }
}
