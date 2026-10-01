import 'dart:io';
import 'package:path/path.dart' as p;

/// Analyzer provider settings supplied by the Rust core.
class GraphConfig {
  final String root;
  final bool flutter;
  final String? sdkPath;
  final String cache;
  GraphConfig({
    required String root,
    this.flutter = true,
    this.sdkPath,
    this.cache = '.polycodegraph',
  }) : root = Directory(
         p.normalize(p.absolute(root)),
       ).resolveSymbolicLinksSync();
  String get cachePath => safePath(cache, allowDirectory: true);
  String relative(String path) =>
      p.relative(path, from: root).replaceAll('\\', '/');
  String safePath(String relative, {bool allowDirectory = false}) {
    if (p.isAbsolute(relative)) {
      throw FormatException('Use a repository-relative path');
    }
    final candidate = p.normalize(p.join(root, relative));
    if (!p.isWithin(root, candidate)) {
      throw FormatException('Path escapes repository');
    }
    // Reject symlinks at every level, including cache paths and snippet files.
    var cursor = candidate;
    while (cursor != root) {
      if (FileSystemEntity.typeSync(cursor, followLinks: false) ==
          FileSystemEntityType.link) {
        throw FormatException('Symlink paths are not supported');
      }
      cursor = p.dirname(cursor);
    }
    if (!allowDirectory &&
        FileSystemEntity.typeSync(candidate) ==
            FileSystemEntityType.directory) {
      throw FormatException('Expected a file');
    }
    return candidate;
  }
}
