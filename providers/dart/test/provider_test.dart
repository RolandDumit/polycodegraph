import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as p;
import 'package:test/test.dart';

void main() {
  test(
    'Analyzer emits only requested records with full semantic context',
    () async {
      final root = Directory.systemTemp.createTempSync('dart provider spaces ');
      addTearDown(() => root.deleteSync(recursive: true));
      File(p.join(root.path, 'domain.dart')).writeAsStringSync('''
abstract class Repository { String fetch(); }
class MemoryRepository implements Repository {
  @override
  String fetch() => 'value';
}
mixin Logging { void log() {} }
enum State { ready, waiting }
typedef Factory = Repository Function();
extension Pretty on State { String label() => name; }
''');
      File(p.join(root.path, 'use.dart')).writeAsStringSync('''
import 'domain.dart';
class LoadUseCase {
  final Repository repository;
  LoadUseCase(this.repository);
  String call() => repository.fetch();
}
''');
      final process = await Process.start(Platform.resolvedExecutable, [
        'bin/graph.dart',
      ]);
      process.stdin.write(
        jsonEncode({
          'root': root.path,
          'files': [
            for (final f in ['domain.dart', 'use.dart'])
              {'file': f, 'hash': 'fixture-$f'},
          ],
          'options': {
            'emit_files': ['use.dart'],
            'sdk_path': p.dirname(p.dirname(Platform.resolvedExecutable)),
          },
        }),
      );
      await process.stdin.close();
      final output = utf8.decoder.bind(process.stdout).join();
      final errors = utf8.decoder.bind(process.stderr).join();
      final records = jsonDecode(await output) as List;
      expect(await process.exitCode, 0, reason: await errors);
      expect(records, hasLength(1));
      final r = records.single as Map;
      expect(r['file'], 'use.dart');
      expect(r['hash'], 'fixture-use.dart');
      expect((r['dependencies'] as List), contains('domain.dart'));
      expect(
        (r['diagnostics'] as List).where((d) => d['severity'] == 'error'),
        isEmpty,
      );
      expect(
        (r['nodes'] as List).any(
          (n) => (n['tags'] as List).contains('UseCase'),
        ),
        isTrue,
      );
      expect(
        (r['edges'] as List).any(
          (e) =>
              e['kind'] == 'calls' &&
              e['target'] == 'domain.dart::Repository.fetch#method',
        ),
        isTrue,
      );
    },
  );
}
