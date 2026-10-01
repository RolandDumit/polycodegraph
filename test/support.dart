import 'dart:io';
import 'package:path/path.dart' as p;

Directory fixtureCopy() {
  final destination = Directory.systemTemp.createTempSync(
    'dart-codegraph-test-',
  );
  copyTree(Directory('test/fixtures/dart_app'), destination);
  return destination;
}

void copyTree(Directory source, Directory target) {
  target.createSync(recursive: true);
  for (final entry in source.listSync(followLinks: false)) {
    if ({'.dart_tool', '.dart-codegraph'}.contains(p.basename(entry.path))) {
      continue;
    }
    final destination = p.join(target.path, p.basename(entry.path));
    if (entry is Directory) copyTree(entry, Directory(destination));
    if (entry is File) entry.copySync(destination);
  }
}
