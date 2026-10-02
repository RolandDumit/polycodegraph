/// Compact AST transport; offsets and compiler identities are losslessly retained.
Map<String, dynamic> packAst(Map<String, dynamic> ast) {
  final scopes = <String>[];
  int scope(dynamic value) {
    final id = value as String? ?? '';
    final found = scopes.indexOf(id);
    if (found >= 0) return found;
    scopes.add(id);
    return scopes.length - 1;
  }

  final bindings = (ast['bindings'] as List).cast<Map<String, dynamic>>();
  final lookup = <String, int>{
    for (var i = 0; i < bindings.length; i++) bindings[i]['id'] as String: i,
  };
  final result = <String, dynamic>{
    'format': 'pcg-ast-1',
    'version': 1,
    'offset_unit': ast['offset_unit'],
    'bindings': bindings
        .map(
          (b) => [
            b['id'],
            b['name'],
            b['kind'],
            b['type'],
            b['line'],
            b['end'],
            b['offset'],
            b['end_offset'],
            scope(b['scope']),
          ],
        )
        .toList(),
    'uses': (ast['uses'] as List)
        .map(
          (u) => [
            u['line'],
            u['end'],
            u['offset'],
            u['end_offset'],
            scope(u['scope']),
            lookup[u['binding']] ?? u['binding'],
            u['read'],
            u['write'],
          ],
        )
        .toList(),
    'statements': (ast['statements'] as List)
        .map(
          (s) => [
            s['line'],
            s['end'],
            s['offset'],
            s['end_offset'],
            scope(s['scope']),
            s['block'],
          ],
        )
        .toList(),
    'controls': (ast['controls'] as List)
        .map(
          (s) => [
            s['line'],
            s['end'],
            s['offset'],
            s['end_offset'],
            scope(s['scope']),
            s['kind'],
          ],
        )
        .toList(),
    'limitations': ast['limitations'],
  };
  result['scopes'] = scopes;
  return result;
}
