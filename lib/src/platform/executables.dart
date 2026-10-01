import 'dart:io';
import 'package:path/path.dart' as p;

/// Windows environment variable names are case-insensitive (PATH or Path).
String executableSearchPath(Map<String, String> environment, {bool? windows}) {
  final win = windows ?? Platform.isWindows;
  for (final entry in environment.entries) {
    if (win ? entry.key.toUpperCase() == 'PATH' : entry.key == 'PATH') {
      return entry.value;
    }
  }
  return '';
}

/// Resolve native programs before spawning: Windows ignores a child PATH when
/// locating its executable. Batch scripts are deliberately excluded.
String? resolveNativeExecutable(
  String name, {
  String? directory,
  Map<String, String>? environment,
  bool? windows,
  bool Function(String)? exists,
}) {
  final win = windows ?? Platform.isWindows;
  final paths = p.Context(
    style: win ? p.Style.windows : p.Style.posix,
    current: directory ?? Directory.current.path,
  );
  final env = environment ?? Platform.environment;
  final present = exists ?? (path) => File(path).existsSync();
  final extension = paths.extension(name).toLowerCase();
  if (win && {'.cmd', '.bat', '.ps1'}.contains(extension)) return null;
  final explicit =
      paths.isAbsolute(name) ||
      name.contains('/') ||
      (win && name.contains(r'\'));
  final candidates = explicit
      ? [paths.absolute(name)]
      : executableSearchPath(env, windows: win)
            .split(win ? ';' : ':')
            .where((dir) => dir.isNotEmpty)
            .map(
              (dir) =>
                  paths.absolute(paths.join(dir.replaceAll('"', ''), name)),
            );
  for (final value in candidates) {
    final candidate = paths.normalize(value);
    if (win && extension.isEmpty && present('$candidate.exe')) {
      return paths.normalize('$candidate.exe');
    }
    if (present(candidate)) return paths.normalize(candidate);
  }
  return null;
}
