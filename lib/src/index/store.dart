import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as p;
import '../config.dart';
import '../graph/model.dart';

/// Atomic snapshot replacement; a kernel lock serializes writers across processes.
class IndexStore {
  final GraphConfig config;
  IndexStore(this.config);
  File get file => File(p.join(config.cachePath, 'index.json'));
  GraphSnapshot? read() {
    if (!file.existsSync()) return null;
    try {
      if (FileSystemEntity.typeSync(file.path, followLinks: false) ==
          FileSystemEntityType.link) {
        throw FormatException('Symlink cache');
      }
      final snapshot = GraphSnapshot.fromJson(
        jsonDecode(file.readAsStringSync()) as Map<String, dynamic>,
      );
      if (snapshot.root != config.root ||
          snapshot.fingerprint != config.fingerprint) {
        return null;
      }
      return snapshot;
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }

  Future<T> locked<T>(Future<T> Function() action) async {
    Directory(config.cachePath).createSync(recursive: true);
    final lockPath = p.join(config.cache, 'index.lockfile');
    final handle = await File(
      config.safePath(lockPath),
    ).open(mode: FileMode.append);
    await handle.lock(FileLock.blockingExclusive);
    try {
      return await action();
    } finally {
      await handle.unlock();
      await handle.close();
    }
  }

  Future<void> write(GraphSnapshot snapshot) async {
    final path = config.safePath(p.join(config.cache, 'index.$pid.tmp'));
    final temp = File(path);
    try {
      await temp.writeAsString(jsonEncode(snapshot.toJson()), flush: true);
      await temp.rename(file.path);
    } finally {
      if (await temp.exists()) await temp.delete();
    }
  }
}
