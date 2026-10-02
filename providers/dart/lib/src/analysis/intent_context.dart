import 'package:analyzer/dart/analysis/results.dart';
import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/visitor.dart';
import 'package:analyzer/dart/element/element.dart';
import '../config.dart';
import '../graph/model.dart';
import 'identity.dart';

/// Additional compiler evidence for intents; primitive symbols/edges are unchanged.
Map<String, dynamic> intentContext(
  ResolvedUnitResult unit,
  GraphConfig config,
  List<GraphNode> declarations,
) {
  final visitor = _Context(unit, config, declarations);
  unit.unit.accept(visitor);
  return {
    'symbols': visitor.symbols.values.map((n) => n.toJson()).toList(),
    'relations': visitor.relations.values.map((e) => e.toJson()).toList(),
    'tests': visitor.tests,
    'ast': visitor.ast,

    'capabilities': [
      'parameter_bindings',
      'resolved_test_cases',
      'region_bindings',
    ],
  };
}

class _Context extends GeneralizingAstVisitor<void> {
  final ResolvedUnitResult unit;
  final GraphConfig config;
  final List<GraphNode> declarations;
  final symbols = <String, GraphNode>{};
  final relations = <String, GraphEdge>{};
  final tests = <Map<String, dynamic>>[];
  final ast = <String, dynamic>{
    'version': 1,
    'offset_unit': 'utf16',
    'statements': <Map<String, dynamic>>[],
    'bindings': <Map<String, dynamic>>[],
    'uses': <Map<String, dynamic>>[],
    'controls': <Map<String, dynamic>>[],
    'limitations': [
      'No hypothetical type-check, alias/lifetime proof or callback execution model',
    ],
  };
  String binding(Element e) =>
      '${elementFile(e, config)}@${e.firstFragment.offset}';
  Map<String, dynamic> site(AstNode node) => {
    'line': line(node.offset),
    'end': line(node.end - 1),
    'offset': node.offset,
    'end_offset': node.end,
    'scope': owner(node),
  };
  @override
  void visitNode(AstNode node) {
    if (node is Statement && node.parent is Block) {
      (ast['statements'] as List).add({
        ...site(node),
        'block': node.parent!.offset,
      });
    }
    final control = node is ReturnStatement
        ? 'return'
        : node is BreakStatement
        ? 'break'
        : node is ContinueStatement
        ? 'continue'
        : node is AwaitExpression
        ? 'await'
        : node is ThrowExpression
        ? 'throw'
        : node is YieldStatement
        ? 'yield'
        : null;
    if (control != null) {
      (ast['controls'] as List).add({...site(node), 'kind': control});
    }
    super.visitNode(node);
  }

  @override
  void visitVariableDeclaration(VariableDeclaration node) {
    final e = node.declaredFragment?.element;
    if (e is LocalVariableElement) {
      (ast['bindings'] as List).add({
        ...site(node),
        'id': binding(e),
        'name': e.displayName,
        'kind': 'local',
        'type': e.type.getDisplayString(),
      });
    }
    super.visitVariableDeclaration(node);
  }

  _Context(this.unit, this.config, this.declarations);
  String get file => config.relative(unit.path);
  int line(int offset) => unit.lineInfo.getLocation(offset).lineNumber;
  String owner(AstNode node) {
    final candidates =
        declarations
            .where(
              (n) =>
                  n.kind != 'file' &&
                  n.offset <= node.offset &&
                  node.end <= n.offset + n.length,
            )
            .toList()
          ..sort((a, b) => a.length.compareTo(b.length));
    return candidates.firstOrNull?.id ?? fileId(file);
  }

  void relation(String? source, String? target, String kind, AstNode site) {
    if (source == null || target == null) return;
    final edge = GraphEdge(
      source,
      target,
      kind,
      file,
      line(site.offset),
      site.offset,
    );
    relations[edge.key] = edge;
  }

  void parameter(FormalParameterElement e, AstNode node) {
    final id = elementId(e, config);
    if (id == null || elementFile(e, config) != file) return;
    symbols.putIfAbsent(
      id,
      () => GraphNode(
        id: id,
        name: e.displayName,
        kind: 'parameter',
        file: file,
        qualifiedName: qualified(e),
        line: line(node.offset),
        endLine: line(node.end - 1),
        offset: node.offset,
        length: node.length,
        parent: elementId(e.enclosingElement, config),
      ),
    );
    relation(elementId(e.enclosingElement, config), id, 'contains', node);
    if (e is FieldFormalParameterElement) {
      relation(id, elementId(e.field, config), 'binds_field', node);
    }
    if (e is SuperFormalParameterElement) {
      relation(
        id,
        elementId(e.superConstructorParameter, config),
        'super_parameter',
        node,
      );
    }
  }

  @override
  void visitFormalParameter(FormalParameter node) {
    final e = node.declaredFragment?.element;
    if (e != null) {
      parameter(e, node);
      (ast['bindings'] as List).add({
        ...site(node),
        'id': binding(e),
        'name': e.displayName,
        'kind': 'parameter',
        'type': e.type.getDisplayString(),
      });
    }
    super.visitFormalParameter(node);
  }

  @override
  void visitSimpleIdentifier(SimpleIdentifier node) {
    final e = node.element;
    if ((e is FormalParameterElement || e is LocalVariableElement) &&
        !node.inDeclarationContext()) {
      (ast['uses'] as List).add({
        ...site(node),
        'binding': binding(e!),
        'read': node.inGetterContext(),
        'write': node.inSetterContext(),
      });
    }
    if (e is FormalParameterElement && !node.inDeclarationContext()) {
      relation(owner(node), elementId(e, config), 'parameter_reference', node);
    }
    super.visitSimpleIdentifier(node);
  }

  @override
  void visitNamedArgument(NamedArgument node) {
    relation(
      owner(node),
      elementId(node.correspondingParameter, config),
      'parameter_reference',
      node,
    );
    super.visitNamedArgument(node);
  }

  @override
  void visitConstructorFieldInitializer(ConstructorFieldInitializer node) {
    final e = node.expression;
    if (e is SimpleIdentifier && e.element is FormalParameterElement) {
      relation(
        elementId(e.element, config),
        elementId(node.fieldName.element, config),
        'binds_field',
        node,
      );
    }
    super.visitConstructorFieldInitializer(node);
  }

  @override
  void visitMethodDeclaration(MethodDeclaration node) {
    final e = node.declaredFragment?.element;
    if (e is PropertyAccessorElement) {
      relation(
        elementId(e.variable.getter, config),
        elementId(e.variable.setter, config),
        'accessor_pair',
        node,
      );
    }
    super.visitMethodDeclaration(node);
  }

  @override
  void visitMethodInvocation(MethodInvocation node) {
    final e = node.methodName.element;
    final uri = e?.library?.uri.toString() ?? '';
    if (e != null &&
        ['test', 'testWidgets'].contains(e.displayName) &&
        (uri.startsWith('package:test/') ||
            uri.startsWith('package:test_api/') ||
            uri.startsWith('package:flutter_test/'))) {
      tests.add({
        'name':
            node.argumentList.arguments.firstOrNull?.toSource() ?? 'unknown',
        'framework': uri.startsWith('package:flutter_test/')
            ? 'flutter_test'
            : 'test',
        'line': line(node.offset),
        'end': line(node.end - 1),
        'owner': owner(node),
        'confidence': 'resolved',
      });
    }
    super.visitMethodInvocation(node);
  }
}
