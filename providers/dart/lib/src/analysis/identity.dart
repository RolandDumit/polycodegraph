import 'package:analyzer/dart/element/element.dart';
import 'package:path/path.dart' as p;
import '../config.dart';

String fileId(String file) => '$file::file';
Element canonical(Element element) {
  element = element.baseElement;
  if (element is PropertyAccessorElement && element.isOriginVariable) {
    return element.variable.baseElement;
  }
  return element;
}

String elementKind(Element e) => switch (e) {
  ConstructorElement() => 'constructor',
  ClassElement() => 'class',
  MixinElement() => 'mixin',
  EnumElement() => 'enum',
  ExtensionElement() => 'extension',
  ExtensionTypeElement() => 'extension_type',
  TypeAliasElement() => 'typedef',
  GetterElement() => 'getter',
  SetterElement() => 'setter',
  MethodElement() => 'method',
  FieldElement() => 'field',
  TopLevelVariableElement() => 'variable',
  TopLevelFunctionElement() => 'function',
  LocalFunctionElement() => 'function',
  _ => e.kind.name.toLowerCase(),
};
String qualified(Element e) {
  final names = <String>[];
  for (
    Element? cursor = e;
    cursor != null && cursor is! LibraryElement;
    cursor = cursor.enclosingElement
  ) {
    final name = cursor is MethodElement ? cursor.lookupName : cursor.name;
    names.add(
      name == null || name.isEmpty ? '@${cursor.firstFragment.offset}' : name,
    );
  }
  return names.reversed.join('.');
}

String? elementFile(Element e, GraphConfig config) {
  final path = e.firstFragment.libraryFragment?.source.fullName;
  if (path == null || !p.isWithin(config.root, p.normalize(path))) return null;
  return config.relative(path);
}

String? elementId(Element? input, GraphConfig config) {
  if (input == null) return null;
  final e = canonical(input);
  final file = elementFile(e, config);
  if (file == null) return null;
  return '$file::${qualified(e)}#${elementKind(e)}';
}
