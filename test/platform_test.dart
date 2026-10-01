import 'package:polycodegraph/src/platform/executables.dart';
import 'package:test/test.dart';

void main() {
  test('Windows Path casing, quoted paths and exe suffix resolve natively', () {
    final resolved = resolveNativeExecutable(
      'node',
      windows: true,
      directory: r'C:\project with spaces',
      environment: {'Path': r'"C:\Program Files\nodejs";C:\tools'},
      exists: (path) => path == r'C:\Program Files\nodejs\node.exe',
    );
    expect(resolved, r'C:\Program Files\nodejs\node.exe');
  });
  test('Windows relative paths accept either separator and exclude shells', () {
    for (final name in ['tools/node', r'tools\node']) {
      expect(
        resolveNativeExecutable(
          name,
          windows: true,
          directory: r'C:\repo',
          environment: {},
          exists: (path) => path == r'C:\repo\tools\node.exe',
        ),
        r'C:\repo\tools\node.exe',
      );
    }
    for (final name in ['node.cmd', 'node.bat', 'node.ps1']) {
      expect(
        resolveNativeExecutable(
          name,
          windows: true,
          directory: r'C:\repo',
          environment: {},
          exists: (_) => true,
        ),
        isNull,
      );
    }
  });
  test('POSIX executable resolution preserves spaces and explicit paths', () {
    expect(
      resolveNativeExecutable(
        'go',
        windows: false,
        directory: '/repo',
        environment: {'PATH': '/tools with spaces:/bin'},
        exists: (path) => path == '/tools with spaces/go',
      ),
      '/tools with spaces/go',
    );
    expect(
      resolveNativeExecutable(
        'tools/go',
        windows: false,
        directory: '/repo',
        environment: {},
        exists: (path) => path == '/repo/tools/go',
      ),
      '/repo/tools/go',
    );
    expect(
      resolveNativeExecutable(
        'missing',
        windows: false,
        directory: '/repo',
        environment: {},
        exists: (_) => false,
      ),
      isNull,
    );
  });
}
