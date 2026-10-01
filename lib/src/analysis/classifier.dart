import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/element/element.dart';

/// Semantic tags where SDK/package types resolve; naming/annotation tags are
/// optional discovery hints, never used to invent call/reference edges.
List<String> classify(Element? element, AstNode node, String name) {
  final tags = <String>{};
  if (element is InterfaceElement) {
    for (final t in element.allSupertypes) {
      final base = t.element;
      final uri = base.library.uri.toString();
      if (uri.startsWith('package:flutter/') &&
          {'Widget', 'StatelessWidget', 'StatefulWidget'}.contains(base.name)) {
        tags.add('Widget');
      }
      if (uri.contains('bloc') && {'Bloc', 'Cubit'}.contains(base.name)) {
        tags.add(base.name!);
      }
      if (uri.contains('riverpod') && (base.name ?? '').contains('Provider')) {
        tags.add('Provider');
      }
    }
  }
  if (tags.contains('Widget') &&
      RegExp(r'(Screen|Page|View)$').hasMatch(name)) {
    tags.add('Screen');
  }
  if (element is InterfaceElement &&
      RegExp(r'Repository(Impl)?$').hasMatch(name)) {
    tags.add('Repository');
  }
  if (element is InterfaceElement && name.endsWith('UseCase')) {
    tags.add('UseCase');
  }
  if (element is InterfaceElement &&
      RegExp(r'(Route|Router)$').hasMatch(name)) {
    tags.add('Route');
  }
  AnnotatedNode? annotated;
  for (AstNode? cursor = node; cursor != null; cursor = cursor.parent) {
    if (cursor is AnnotatedNode) {
      annotated = cursor;
      break;
    }
  }
  for (final a in annotated?.metadata ?? <Annotation>[]) {
    final n = a.name.toSource().split('.').last.toLowerCase();
    if (n == 'freezed' || n == 'unfreezed') tags.add('Freezed');
    if (n == 'riverpod') tags.add('Provider');
  }
  if (node is VariableDeclaration &&
      node.initializer is InstanceCreationExpression) {
    final c = (node.initializer as InstanceCreationExpression)
        .constructorName
        .element;
    final uri = c?.library.uri.toString() ?? '';
    final type = c?.enclosingElement.name ?? '';
    if (uri.contains('riverpod') && type.contains('Provider')) {
      tags.add('Provider');
    }
    if (uri.contains('go_router') && type.contains('Route')) tags.add('Route');
  }
  return tags.toList()..sort();
}
