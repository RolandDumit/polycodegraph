import 'package:analyzer/dart/analysis/results.dart';
import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/visitor.dart';
import 'package:analyzer/dart/element/element.dart';
import 'package:path/path.dart' as p;
import '../config.dart';
import '../graph/model.dart';
import 'classifier.dart';
import 'identity.dart';

FileRecord extract(ResolvedUnitResult result, GraphConfig config, String hash) {
  final collector = _Collector(result, config);
  result.unit.accept(collector);
  result.unit.accept(_Relations(collector));
  collector.addImplicitConstructorCalls();
  collector.nodes.sort((a, b) => a.id.compareTo(b.id));
  final edges = {
    for (final edge in collector.edges) edge.key: edge,
  }.values.toList()..sort((a, b) => a.key.compareTo(b.key));
  return FileRecord(
    file: collector.file,
    hash: hash,
    nodes: collector.nodes,
    edges: edges,
    dependencies: collector.dependencies.toList()..sort(),
    unresolvedCalls: collector.unresolvedCalls,
    diagnostics: result.diagnostics
        .map(
          (d) => {
            'code': d.diagnosticCode.lowerCaseName,
            'severity': d.diagnosticCode.severity.name.toLowerCase(),
            'line': result.lineInfo.getLocation(d.offset).lineNumber,
            'message': d.message,
          },
        )
        .toList(),
  );
}

class _Collector extends GeneralizingAstVisitor<void> {
  final ResolvedUnitResult result;
  final GraphConfig config;
  late final String file = config.relative(result.path);
  final List<GraphNode> nodes = [];
  final List<GraphEdge> edges = [];
  final Set<String> dependencies = {};
  final Map<AstNode, GraphNode> declarations = {};
  final Map<String, Element> elements = {};
  final List<GraphNode> stack = [];
  int unresolvedCalls = 0;
  _Collector(this.result, this.config) {
    nodes.add(
      GraphNode(
        id: fileId(file),
        name: p.basename(file),
        kind: 'file',
        file: file,
        qualifiedName: file,
        line: 1,
        endLine: result.lineInfo.getLocation(result.content.length).lineNumber,
        offset: 0,
        length: result.content.length,
      ),
    );
  }
  int line(int offset) => result.lineInfo.getLocation(offset).lineNumber;
  @override
  void visitDeclaration(Declaration node) {
    final fragment = node.declaredFragment;
    final e = fragment?.element;
    final supported =
        node is ClassDeclaration ||
        node is MixinDeclaration ||
        node is EnumDeclaration ||
        node is ExtensionDeclaration ||
        node is ExtensionTypeDeclaration ||
        node is TypeAlias ||
        node is FunctionDeclaration ||
        node is MethodDeclaration ||
        node is ConstructorDeclaration ||
        node is EnumConstantDeclaration ||
        (node is VariableDeclaration &&
            (e is FieldElement || e is TopLevelVariableElement));
    final id = supported ? elementId(e, config) : null;
    if (id == null) {
      super.visitDeclaration(node);
      return;
    }
    // Malformed duplicate declarations are represented once, with diagnostics.
    final existing = nodes.where((n) => n.id == id).firstOrNull;
    final parent = stack.isEmpty ? fileId(file) : stack.last.id;
    final graphNode =
        existing ??
        GraphNode(
          id: id,
          name: e!.displayName,
          kind: elementKind(e),
          file: file,
          qualifiedName: qualified(e),
          line: line(node.offset),
          endLine: line(node.end - 1),
          offset: node.offset,
          length: node.length,
          parent: parent,
          tags: config.flutter ? classify(e, node, e.displayName) : [],
        );
    if (existing == null) {
      nodes.add(graphNode);
      elements[id] = e!;
      edges.add(
        GraphEdge(parent, id, 'contains', file, graphNode.line, node.offset),
      );
    }
    declarations[node] = graphNode;
    stack.add(graphNode);
    super.visitDeclaration(node);
    stack.removeLast();
    if (e is InterfaceElement) {
      for (final ctor in e.constructors) {
        final ctorId = elementId(ctor, config);
        if (ctorId == null || nodes.any((n) => n.id == ctorId)) continue;
        final primary = switch (node) {
          ClassDeclaration() => node.namePart,
          EnumDeclaration() => node.namePart,
          ExtensionTypeDeclaration() => node.namePart,
          _ => null,
        };
        final range = ctor.isPrimary && primary is PrimaryConstructorDeclaration
            ? primary
            : node;
        final ctorNode = GraphNode(
          id: ctorId,
          name: ctor.displayName,
          kind: 'constructor',
          file: file,
          qualifiedName: qualified(ctor),
          line: line(range.offset),
          endLine: line(range.end - 1),
          offset: range.offset,
          length: range.length,
          parent: id,
          synthetic: !ctor.isOriginDeclaration,
        );
        nodes.add(ctorNode);
        if (ctor.isPrimary && primary is PrimaryConstructorDeclaration) {
          declarations[primary] = ctorNode;
        }
        elements[ctorId] = ctor;
        edges.add(
          GraphEdge(id, ctorId, 'contains', file, graphNode.line, node.offset),
        );
      }
      for (final field in e.fields.where(
        (f) => f.isOriginDeclaringFormalParameter,
      )) {
        final fieldId = elementId(field, config);
        if (fieldId == null || nodes.any((n) => n.id == fieldId)) continue;
        final offset = field.firstFragment.offset;
        nodes.add(
          GraphNode(
            id: fieldId,
            name: field.displayName,
            kind: 'field',
            file: file,
            qualifiedName: qualified(field),
            line: line(offset),
            endLine: line(offset),
            offset: offset,
            length: field.displayName.length,
            parent: id,
          ),
        );
        elements[fieldId] = field;
        edges.add(
          GraphEdge(id, fieldId, 'contains', file, line(offset), offset),
        );
      }
    }
  }

  void addImplicitConstructorCalls() {
    for (final entry in elements.entries) {
      final e = entry.value;
      if (e is! ConstructorElement || e.superConstructor == null) continue;
      final target = elementId(e.superConstructor, config);
      if (target == null ||
          edges.any(
            (edge) =>
                edge.source == entry.key &&
                edge.target == target &&
                edge.kind == 'calls',
          )) {
        continue;
      }
      final source = nodes.firstWhere((n) => n.id == entry.key);
      final dep = elementFile(e.superConstructor!, config);
      if (dep != null && dep != file) dependencies.add(dep);
      edges.add(
        GraphEdge(entry.key, target, 'calls', file, source.line, source.offset),
      );
    }
  }

  GraphNode owner(AstNode node) {
    for (AstNode? cursor = node; cursor != null; cursor = cursor.parent) {
      final declaration = declarations[cursor];
      if (declaration != null) return declaration;
    }
    return nodes.firstWhere((n) => n.kind == 'file');
  }

  void relate(AstNode node, Element? input, String kind, {String? source}) {
    if (input == null) {
      if (kind == 'calls') unresolvedCalls++;
      return;
    }
    final e = canonical(input);
    if (e is LocalVariableElement ||
        e is FormalParameterElement ||
        e is TypeParameterElement ||
        e is PrefixElement ||
        e is LibraryElement) {
      return;
    }
    if (kind == 'calls' && e is! ExecutableElement) {
      unresolvedCalls++;
      return;
    }
    final target = elementId(e, config);
    final dep = elementFile(e, config);
    if (dep != null && dep != file) dependencies.add(dep);
    if (target == null) return;
    edges.add(
      GraphEdge(
        source ?? owner(node).id,
        target,
        kind,
        file,
        line(node.offset),
        node.offset,
      ),
    );
  }
}

class _Relations extends GeneralizingAstVisitor<void> {
  final _Collector c;
  _Relations(this.c);
  @override
  void visitSimpleIdentifier(SimpleIdentifier node) {
    if (!node.inDeclarationContext()) {
      c.relate(node, node.element, 'references');
      if (node.element is PropertyAccessorElement &&
          !(node.element as PropertyAccessorElement).isOriginVariable) {
        c.relate(node, node.element, 'calls');
      }
    }
    super.visitSimpleIdentifier(node);
  }

  @override
  void visitNamedType(NamedType node) {
    c.relate(node, node.element, 'references');
    final parent = node.parent;
    final kind = parent is ExtendsClause
        ? 'extends'
        : parent is ImplementsClause
        ? 'implements'
        : parent is WithClause
        ? 'with'
        : parent is MixinOnClause || parent is ExtensionOnClause
        ? 'on'
        : null;
    if (kind != null) c.relate(node, node.element, kind);
    if (parent is ClassTypeAlias && identical(parent.superclass, node)) {
      c.relate(node, node.element, 'extends');
    }
    super.visitNamedType(node);
  }

  @override
  void visitMethodInvocation(MethodInvocation node) {
    c.relate(node, node.methodName.element, 'calls');
    final e = node.methodName.element;
    if (c.config.flutter &&
        e != null &&
        e.library?.uri.toString().contains('get_it') == true &&
        node.methodName.name.startsWith('register')) {
      final owner = c.owner(node);
      if (!owner.tags.contains('GetItRegistration')) {
        owner.tags.add('GetItRegistration');
        owner.tags.sort();
      }
      for (final type
          in node.typeArguments?.arguments.whereType<NamedType>() ??
              <NamedType>[]) {
        c.relate(node, type.element, 'registers');
      }
    }
    super.visitMethodInvocation(node);
  }

  @override
  void visitFunctionExpressionInvocation(FunctionExpressionInvocation node) {
    c.relate(node, node.element, 'calls');
    super.visitFunctionExpressionInvocation(node);
  }

  @override
  void visitInstanceCreationExpression(InstanceCreationExpression node) {
    c.relate(node, node.constructorName.element, 'calls');
    super.visitInstanceCreationExpression(node);
  }

  @override
  void visitConstructorName(ConstructorName node) {
    c.relate(node, node.element, 'references');
    if (node.parent is ConstructorDeclaration) {
      c.relate(node, node.element, 'calls');
    }
    super.visitConstructorName(node);
  }

  @override
  void visitSuperConstructorInvocation(SuperConstructorInvocation node) {
    c.relate(node, node.element, 'calls');
    super.visitSuperConstructorInvocation(node);
  }

  @override
  void visitRedirectingConstructorInvocation(
    RedirectingConstructorInvocation node,
  ) {
    c.relate(node, node.element, 'calls');
    super.visitRedirectingConstructorInvocation(node);
  }

  @override
  void visitAssignmentExpression(AssignmentExpression node) {
    c.relate(node, node.writeElement, 'references');
    if (node.writeElement is PropertyAccessorElement &&
        !(node.writeElement as PropertyAccessorElement).isOriginVariable) {
      c.relate(node, node.writeElement, 'calls');
    }
    if (node.readElement is PropertyAccessorElement &&
        !(node.readElement as PropertyAccessorElement).isOriginVariable) {
      c.relate(node, node.readElement, 'calls');
    }
    if (node.element != null) c.relate(node, node.element, 'calls');
    super.visitAssignmentExpression(node);
  }

  @override
  void visitBinaryExpression(BinaryExpression node) {
    c.relate(node, node.element, 'calls');
    super.visitBinaryExpression(node);
  }

  @override
  void visitPrefixExpression(PrefixExpression node) {
    c.relate(node, node.element, 'calls');
    super.visitPrefixExpression(node);
  }

  @override
  void visitPostfixExpression(PostfixExpression node) {
    c.relate(node, node.element, 'calls');
    super.visitPostfixExpression(node);
  }

  @override
  void visitIndexExpression(IndexExpression node) {
    c.relate(node, node.element, 'calls');
    super.visitIndexExpression(node);
  }

  @override
  void visitDirective(Directive node) {
    final fragment = node is UriBasedDirective ? node : null;
    final kind = node is ImportDirective
        ? 'imports'
        : node is ExportDirective
        ? 'exports'
        : node is PartDirective
        ? 'part'
        : node is PartOfDirective
        ? 'part_of'
        : null;
    if (kind != null) {
      final uris = <String>{};
      String? targetPath;
      if (node is ImportDirective) {
        targetPath =
            node.libraryImport?.importedLibrary?.firstFragment.source.fullName;
      }
      if (node is ExportDirective) {
        targetPath =
            node.libraryExport?.exportedLibrary?.firstFragment.source.fullName;
      }
      if (fragment != null) {
        if (fragment.uri.stringValue != null) {
          uris.add(fragment.uri.stringValue!);
        }
        if (node is NamespaceDirective) {
          for (final option in node.configurations) {
            if (option.uri.stringValue != null) {
              uris.add(option.uri.stringValue!);
            }
          }
        }
      }
      if (node is PartOfDirective && node.uri?.stringValue != null) {
        uris.add(node.uri!.stringValue!);
      }
      if (node is PartOfDirective && uris.isEmpty) {
        targetPath = c.result.libraryElement.firstFragment.source.fullName;
      }
      if (targetPath != null && p.isWithin(c.config.root, targetPath)) {
        // Compiler paths are filesystem paths; directive identities are URIs.
        uris.add(
          p
              .toUri(p.relative(targetPath, from: p.dirname(c.result.path)))
              .toString(),
        );
      }
      for (final uri in uris) {
        final parsed = Uri.tryParse(uri);
        final local = parsed == null
            ? null
            : parsed.hasScheme
            ? c.result.session.uriConverter.uriToPath(parsed)
            : p.normalize(
                p.join(p.dirname(c.result.path), Uri.decodeComponent(uri)),
              );
        if (local != null && p.isWithin(c.config.root, local)) {
          c.config.safePath(c.config.relative(local), allowDirectory: true);
        }
        final dep = local != null && p.isWithin(c.config.root, local)
            ? c.config.relative(local)
            : null;
        if (dep != null) c.dependencies.add(dep);
        final target = dep != null ? fileId(dep) : 'uri::$uri';
        if (dep == null && !c.nodes.any((n) => n.id == target)) {
          c.nodes.add(
            GraphNode(
              id: target,
              name: uri,
              kind: 'external',
              file: uri,
              qualifiedName: uri,
              line: 0,
              endLine: 0,
              offset: 0,
              length: 0,
            ),
          );
        }
        c.edges.add(
          GraphEdge(
            fileId(c.file),
            target,
            kind,
            c.file,
            c.line(node.offset),
            node.offset,
          ),
        );
      }
    }
    super.visitDirective(node);
  }

  @override
  void visitMethodDeclaration(MethodDeclaration node) {
    final e = node.declaredFragment?.element;
    final container = e?.enclosingElement;
    if (e != null && container is InterfaceElement) {
      for (final type in container.allSupertypes) {
        final candidates = <ExecutableElement>[
          ...type.element.methods,
          ...type.element.getters,
          ...type.element.setters,
        ];
        for (final base in candidates.where(
          (m) =>
              m.lookupName == e.lookupName &&
              m.isAccessibleIn(container.library),
        )) {
          c.relate(node, base, 'overrides', source: elementId(e, c.config));
        }
      }
    }
    super.visitMethodDeclaration(node);
  }
}
