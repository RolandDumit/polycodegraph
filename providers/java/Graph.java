import com.sun.source.tree.*;
import com.sun.source.util.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import javax.lang.model.element.*;
import javax.lang.model.type.*;
import javax.lang.model.util.*;
import javax.tools.*;

/** javac semantic adapter; annotation processors and code emission are disabled. */
class Graph {

  static Map<String, Object> map(Object... pairs) {
    var m = new LinkedHashMap<String, Object>();
    for (int i = 0; i < pairs.length; i += 2) m.put(
      (String) pairs[i],
      pairs[i + 1]
    );
    return m;
  }

  @SuppressWarnings("unchecked")
  static Map<String, Object> obj(Object value) {
    return (Map<String, Object>) value;
  }

  @SuppressWarnings("unchecked")
  static List<Object> list(Object value) {
    return (List<Object>) value;
  }

  static String root;
  static Map<String, Map<String, Object>> records = new LinkedHashMap<>();
  static Map<Element, String> symbols = new HashMap<>();
  static Map<Tree, String> ids = new IdentityHashMap<>();
  static Map<String, Map<String, Object>> nodes = new HashMap<>();
  static Trees trees;
  static Elements elements;
  static Types types;

  static String file(CompilationUnitTree unit) {
    return Path.of(root)
      .relativize(
        Path.of(unit.getSourceFile().toUri()).toAbsolutePath().normalize()
      )
      .toString()
      .replace('\\', '/');
  }

  static long start(CompilationUnitTree unit, Tree tree) {
    return trees.getSourcePositions().getStartPosition(unit, tree);
  }

  static long end(CompilationUnitTree unit, Tree tree) {
    return trees.getSourcePositions().getEndPosition(unit, tree);
  }

  static long line(CompilationUnitTree unit, long pos) {
    return Math.max(1, unit.getLineMap().getLineNumber(Math.max(0, pos)));
  }

  static Map<String,Object> intentContext(CompilationUnitTree unit) {
    var statements = new ArrayList<Object>(); var bindings = new ArrayList<Object>(); var uses = new ArrayList<Object>(); var controls = new ArrayList<Object>();
    var bound = new HashMap<Element,Map<String,Object>>();
    class Context extends TreePathScanner<Void,Void> {
      String scope() { for(var p=getCurrentPath();p!=null;p=p.getParentPath()) {var id=ids.get(p.getLeaf()); if(id!=null)return id;} return file(unit)+"::file"; }
      Map<String,Object> site(Tree node) { return map("line",line(unit,start(unit,node)),"end",line(unit,Math.max(start(unit,node),end(unit,node)-1)),"offset",start(unit,node),"end_offset",end(unit,node),"scope",scope()); }
      @Override public Void visitVariable(VariableTree node,Void unused) {
        var e=trees.getElement(getCurrentPath());
        if(e!=null && Set.of(ElementKind.LOCAL_VARIABLE,ElementKind.PARAMETER,ElementKind.EXCEPTION_PARAMETER,ElementKind.RESOURCE_VARIABLE).contains(e.getKind()) && start(unit,node)>=0) {
          var b=site(node); b.putAll(map("id",file(unit)+"@"+start(unit,node),"name",e.getSimpleName().toString(),"kind",e.getKind()==ElementKind.PARAMETER?"parameter":"local","type",e.asType().toString()));bound.put(e,b);bindings.add(b);
        }
        return super.visitVariable(node,unused);
      }
    }
    new Context().scan(unit,null);
    new Context() {
      @Override public Void scan(Tree node,Void unused) {
        if(node==null || start(unit,node)<0 || end(unit,node)<start(unit,node))return null;
        var parent=getCurrentPath()==null?null:getCurrentPath().getLeaf();
        if(node instanceof StatementTree && parent instanceof BlockTree) {var s=site(node);s.put("block",start(unit,parent));statements.add(s);}
        var kind=node instanceof ReturnTree?"return":node instanceof BreakTree?"break":node instanceof ContinueTree?"continue":node instanceof ThrowTree?"throw":null;
        if(kind!=null){var s=site(node);s.put("kind",kind);controls.add(s);}
        return super.scan(node,unused);
      }
      @Override public Void visitIdentifier(IdentifierTree node,Void unused) {
        var binding=bound.get(trees.getElement(getCurrentPath()));
        if(binding!=null){var parent=getCurrentPath().getParentPath().getLeaf();boolean write=parent instanceof AssignmentTree a&&a.getVariable()==node || parent instanceof CompoundAssignmentTree b&&b.getVariable()==node || parent instanceof UnaryTree u&&Set.of(Tree.Kind.PREFIX_INCREMENT,Tree.Kind.POSTFIX_INCREMENT,Tree.Kind.PREFIX_DECREMENT,Tree.Kind.POSTFIX_DECREMENT).contains(u.getKind());boolean read=!(parent instanceof AssignmentTree a&&a.getVariable()==node);
          var s=site(node);s.putAll(map("binding",binding.get("id"),"read",read,"write",write));uses.add(s);}
        return super.visitIdentifier(node,unused);
      }
    }.scan(unit,null);
    return map("version",1,"offset_unit","utf16","statements",statements,"bindings",bindings,"uses",uses,"controls",controls,"limitations",List.of("No alias/lifetime, reflection, exception-path or hypothetical extracted type-check proof"));
  }

  static String qualified(Element e) {
    if (e instanceof TypeElement t) return t.getQualifiedName().toString();
    return (
      qualified(e.getEnclosingElement()) +
      "." +
      (e.getKind() == ElementKind.CONSTRUCTOR
        ? "new"
        : e.getSimpleName().toString())
    );
  }

  static String add(
    CompilationUnitTree unit,
    Tree tree,
    Element element,
    String kind,
    String parent
  ) {
    String f = file(unit);
    long pos = start(unit, tree),
      finish = end(unit, tree);
    if (pos < 0 || finish < pos) return null;
    String name =
      element.getKind() == ElementKind.CONSTRUCTOR
        ? "new"
        : element.getSimpleName().toString();
    String q = qualified(element);
    if (element instanceof ExecutableElement method) q +=
      "(" +
      String.join(
        ",",
        method
          .getParameters()
          .stream()
          .map(p -> types.erasure(p.asType()).toString())
          .toList()
      ) +
      ")";
    String id = f + "::" + q + "#" + kind;
    var n = map(
      "id",
      id,
      "name",
      name,
      "kind",
      kind,
      "file",
      f,
      "q",
      q,
      "line",
      line(unit, pos),
      "end",
      line(unit, Math.max(pos, finish - 1)),
      "offset",
      pos,
      "length",
      finish - pos,
      "parent",
      parent,
      "tags",
      List.of()
    );
    list(records.get(f).get("nodes")).add(n);
    nodes.put(id, n);
    symbols.put(element, id);
    ids.put(tree, id);
    edge(unit, parent, id, "contains", tree);
    return id;
  }

  static void edge(
    CompilationUnitTree unit,
    String source,
    String target,
    String kind,
    Tree site
  ) {
    if (source == null || target == null) return;
    String f = file(unit);
    long pos = start(unit, site);
    list(records.get(f).get("edges")).add(
      map(
        "source",
        source,
        "target",
        target,
        "kind",
        kind,
        "file",
        f,
        "line",
        line(unit, pos),
        "offset",
        Math.max(0, pos),
        "confidence",
        "resolved"
      )
    );
    String other = target.split("::", 2)[0];
    if (!f.equals(other) && records.containsKey(other)) list(
      records.get(f).get("dependencies")
    ).add(other);
  }

  public static void main(String[] args) throws Exception {
    var input = obj(
      new Json(
        new String(System.in.readAllBytes(), StandardCharsets.UTF_8)
      ).parse()
    );
    root = Path.of((String) input.get("root"))
      .toAbsolutePath()
      .normalize()
      .toString();
    var paths = new ArrayList<File>();
    for (Object value : list(input.get("files"))) {
      var f = obj(value);
      String name = (String) f.get("file");
      String text = Files.readString(Path.of(root, name));
      var r = map(
        "file",
        name,
        "hash",
        f.get("hash"),
        "nodes",
        new ArrayList<>(),
        "edges",
        new ArrayList<>(),
        "dependencies",
        new ArrayList<>(),
        "diagnostics",
        new ArrayList<>(),
        "unresolvedCalls",
        0
      );
      records.put(name, r);
      list(r.get("nodes")).add(
        map(
          "id",
          name + "::file",
          "name",
          name,
          "kind",
          "file",
          "file",
          name,
          "q",
          name,
          "line",
          1,
          "end",
          text.split("\n", -1).length,
          "offset",
          0,
          "length",
          text.length(),
          "tags",
          List.of()
        )
      );
      paths.add(Path.of(root, name).toFile());
    }
    var compiler = ToolProvider.getSystemJavaCompiler();
    if (compiler == null) throw new IllegalStateException(
      "A full JDK 17+ is required"
    );
    var diagnostics = new DiagnosticCollector<JavaFileObject>();
    try (
      var manager = compiler.getStandardFileManager(
        diagnostics,
        null,
        StandardCharsets.UTF_8
      )
    ) {
      var options = new ArrayList<>(
        List.of("-proc:none", "-implicit:none", "-Xlint:none")
      );
      var cp = list(obj(input.get("options")).get("classpath"));
      if (!cp.isEmpty()) {
        options.add("-classpath");
        options.add(
          String.join(
            File.pathSeparator,
            cp.stream().map(Object::toString).toList()
          )
        );
      }
      var task = (JavacTask) compiler.getTask(
        new PrintWriter(System.err),
        manager,
        diagnostics,
        options,
        null,
        manager.getJavaFileObjectsFromFiles(paths)
      );
      var units = new ArrayList<CompilationUnitTree>();
      task.parse().forEach(units::add);
      task.analyze();
      trees = Trees.instance(task);
      elements = task.getElements();
      types = task.getTypes();
      for (var unit : units)
        new TreePathScanner<Void, String>() {
          @Override
          public Void visitClass(ClassTree node, String parent) {
            Element e = trees.getElement(getCurrentPath());
            String k = switch (node.getKind()) {
              case INTERFACE, ANNOTATION_TYPE -> "interface";
              case ENUM -> "enum";
              case RECORD -> "record";
              default -> "class";
            };
            String id = e == null ? null : add(unit, node, e, k, parent);
            return super.visitClass(node, id == null ? parent : id);
          }

          @Override
          public Void visitMethod(MethodTree node, String parent) {
            Element e = trees.getElement(getCurrentPath());
            String id =
              e == null
                ? null
                : add(
                    unit,
                    node,
                    e,
                    e.getKind() == ElementKind.CONSTRUCTOR
                      ? "constructor"
                      : "method",
                    parent
                  );
            return super.visitMethod(node, id == null ? parent : id);
          }

          @Override
          public Void visitVariable(VariableTree node, String parent) {
            Element e = trees.getElement(getCurrentPath());
            if (
              e != null &&
              (e.getKind() == ElementKind.FIELD ||
                e.getKind() == ElementKind.ENUM_CONSTANT)
            ) add(unit, node, e, "field", parent);
            return super.visitVariable(node, parent);
          }
        }.scan(unit, file(unit) + "::file");
      // Implicit javac constructors do not have complete source spans.
      for (var entry : new ArrayList<>(symbols.entrySet()))
        if (entry.getKey() instanceof TypeElement type) {
          for (var e : type.getEnclosedElements())
            if (
              e.getKind() == ElementKind.CONSTRUCTOR && !symbols.containsKey(e)
            ) {
              var n = new LinkedHashMap<>(nodes.get(entry.getValue()));
              String q =
                type.getQualifiedName() +
                ".new(" +
                String.join(
                  ",",
                  ((ExecutableElement) e)
                    .getParameters()
                    .stream()
                    .map(p -> types.erasure(p.asType()).toString())
                    .toList()
                ) +
                ")";
              String id = n.get("file") + "::" + q + "#constructor";
              n.putAll(
                map(
                  "id",
                  id,
                  "q",
                  q,
                  "name",
                  "new",
                  "kind",
                  "constructor",
                  "parent",
                  entry.getValue(),
                  "synthetic",
                  true
                )
              );
              nodes.put(id, n);
              symbols.put(e, id);
              list(records.get(n.get("file")).get("nodes")).add(n);
              for (var unit : units)
                if (file(unit).equals(n.get("file"))) edge(
                  unit,
                  entry.getValue(),
                  id,
                  "contains",
                  unit
                );
            }
        }
      for (var unit : units)
        new TreePathScanner<Void, String>() {
          @Override
          public Void scan(Tree node, String owner) {
            if (node == null) return null;
            return super.scan(node, ids.getOrDefault(node, owner));
          }

          @Override
          public Void visitClass(ClassTree node, String owner) {
            Element element = trees.getElement(getCurrentPath());
            if (element instanceof TypeElement type) {
              edge(
                unit,
                owner,
                symbols.get(types.asElement(type.getSuperclass())),
                "extends",
                node
              );
              for (var it : type.getInterfaces())
                edge(
                  unit,
                  owner,
                  symbols.get(types.asElement(it)),
                  "implements",
                  node
                );
            }
            return super.visitClass(node, owner);
          }

          @Override
          public Void visitMethod(MethodTree node, String owner) {
            Element element = trees.getElement(getCurrentPath());
            if (
              element instanceof ExecutableElement method &&
              method.getEnclosingElement() instanceof TypeElement type
            ) {
              for (var entry : symbols.entrySet())
                if (
                  entry.getKey() instanceof ExecutableElement base &&
                  base != method &&
                  elements.overrides(method, base, type)
                ) edge(unit, owner, entry.getValue(), "overrides", node);
            }
            return super.visitMethod(node, owner);
          }

          @Override
          public Void visitMethodInvocation(
            MethodInvocationTree node,
            String owner
          ) {
            Element e = trees.getElement(getCurrentPath());
            if (e instanceof ExecutableElement) edge(
              unit,
              owner,
              symbols.get(e),
              "calls",
              node
            );
            else records
              .get(file(unit))
              .compute("unresolvedCalls", (k, v) -> (int) v + 1);
            return super.visitMethodInvocation(node, owner);
          }

          @Override
          public Void visitNewClass(NewClassTree node, String owner) {
            Element e = trees.getElement(getCurrentPath());
            if (e instanceof ExecutableElement) edge(
              unit,
              owner,
              symbols.get(e),
              "calls",
              node
            );
            else records
              .get(file(unit))
              .compute("unresolvedCalls", (k, v) -> (int) v + 1);
            return super.visitNewClass(node, owner);
          }

          @Override
          public Void visitIdentifier(IdentifierTree node, String owner) {
            edge(
              unit,
              owner,
              symbols.get(trees.getElement(getCurrentPath())),
              "references",
              node
            );
            return super.visitIdentifier(node, owner);
          }

          @Override
          public Void visitMemberSelect(MemberSelectTree node, String owner) {
            edge(
              unit,
              owner,
              symbols.get(trees.getElement(getCurrentPath())),
              "references",
              node
            );
            return super.visitMemberSelect(node, owner);
          }

          @Override
          public Void visitMemberReference(
            MemberReferenceTree node,
            String owner
          ) {
            edge(
              unit,
              owner,
              symbols.get(trees.getElement(getCurrentPath())),
              "references",
              node
            );
            return super.visitMemberReference(node, owner);
          }

          @Override
          public Void visitImport(ImportTree node, String owner) {
            var path = new TreePath(
              getCurrentPath(),
              node.getQualifiedIdentifier()
            );
            String target = symbols.get(trees.getElement(path));
            if (target != null) edge(
              unit,
              file(unit) + "::file",
              target.split("::", 2)[0] + "::file",
              "imports",
              node
            );
            return super.visitImport(node, owner);
          }
        }.scan(unit, file(unit) + "::file");
      for (var unit : units) records.get(file(unit)).put("intent",map("capabilities",List.of("region_bindings"),"ast",intentContext(unit)));
      for (var d : diagnostics.getDiagnostics()) {
        String f =
          d.getSource() == null
            ? records.keySet().iterator().next()
            : Path.of(root)
                .relativize(Path.of(d.getSource().toUri()))
                .toString()
                .replace('\\', '/');
        var rec = records.get(f);
        if (rec != null && list(rec.get("diagnostics")).size() < 200) list(
          rec.get("diagnostics")
        ).add(
          map(
            "severity",
            d.getKind() == Diagnostic.Kind.ERROR ? "error" : "warning",
            "code",
            d.getCode(),
            "message",
            d.getMessage(Locale.ROOT),
            "line",
            Math.max(1, d.getLineNumber())
          )
        );
      }
    }
    for (var rec : records.values()) {
      var deps = new TreeSet<String>();
      for (var d : list(rec.get("dependencies"))) deps.add(d.toString());
      rec.put("dependencies", new ArrayList<>(deps));
      list(rec.get("nodes")).sort(
        Comparator.comparing(n -> obj(n).get("id").toString())
      );
      list(rec.get("edges")).sort(Comparator.comparing(Json::write));
    }
    var emitted = obj(input.get("options")).get("emit_files");
    var output = new ArrayList<>(records.values());
    if (emitted instanceof List<?> selected) output.removeIf(r -> !selected.contains(r.get("file")));
    System.out.print(Json.write(output));
  }

  // Minimal JSON codec avoids a provider dependency; only standard JSON is accepted.
  static class Json {

    final String s;
    int i;

    Json(String s) {
      this.s = s;
    }

    void ws() {
      while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++;
    }

    Object parse() {
      Object v = value();
      ws();
      if (i != s.length()) throw new IllegalArgumentException("Trailing JSON");
      return v;
    }

    Object value() {
      ws();
      char c = s.charAt(i);
      if (c == '"') return string();
      if (c == '{') {
        i++;
        var m = new LinkedHashMap<String, Object>();
        ws();
        if (s.charAt(i) == '}') {
          i++;
          return m;
        }
        while (true) {
          ws();
          String k = string();
          ws();
          if (s.charAt(i++) != ':') throw new IllegalArgumentException(
            "Expected colon"
          );
          m.put(k, value());
          ws();
          c = s.charAt(i++);
          if (c == '}') return m;
          if (c != ',') throw new IllegalArgumentException("Expected comma");
        }
      }
      if (c == '[') {
        i++;
        var a = new ArrayList<>();
        ws();
        if (s.charAt(i) == ']') {
          i++;
          return a;
        }
        while (true) {
          a.add(value());
          ws();
          c = s.charAt(i++);
          if (c == ']') return a;
          if (c != ',') throw new IllegalArgumentException("Expected comma");
        }
      }
      for (String lit : List.of("null", "true", "false"))
        if (s.startsWith(lit, i)) {
          i += lit.length();
          return lit.equals("null") ? null : lit.equals("true");
        }
      int start = i;
      while (i < s.length() && "-+0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
      return Double.valueOf(s.substring(start, i));
    }

    String string() {
      if (s.charAt(i++) != '"') throw new IllegalArgumentException(
        "Expected string"
      );
      var b = new StringBuilder();
      while (i < s.length()) {
        char c = s.charAt(i++);
        if (c == '"') return b.toString();
        if (c == '\\') {
          c = s.charAt(i++);
          switch (c) {
            case '"', '\\', '/' -> b.append(c);
            case 'b' -> b.append('\b');
            case 'f' -> b.append('\f');
            case 'n' -> b.append('\n');
            case 'r' -> b.append('\r');
            case 't' -> b.append('\t');
            case 'u' -> {
              b.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
              i += 4;
            }
            default -> throw new IllegalArgumentException("Invalid escape");
          }
        } else {
          if (c < 32) throw new IllegalArgumentException("Control character");
          b.append(c);
        }
      }
      throw new IllegalArgumentException("Unterminated string");
    }

    static String write(Object v) {
      if (v == null) return "null";
      if (v instanceof String s) {
        var b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
          switch (c) {
            case '"' -> b.append("\\\"");
            case '\\' -> b.append("\\\\");
            case '\n' -> b.append("\\n");
            case '\r' -> b.append("\\r");
            case '\t' -> b.append("\\t");
            default -> {
              if (c < 32) b.append(String.format("\\u%04x", (int) c));
              else b.append(c);
            }
          }
        }
        return b.append('"').toString();
      }
      if (v instanceof Map<?, ?> m) {
        var parts = new ArrayList<String>();
        m.forEach((k, val) ->
          parts.add(write(k.toString()) + ":" + write(val))
        );
        return "{" + String.join(",", parts) + "}";
      }
      if (v instanceof Collection<?> a) return (
        "[" + String.join(",", a.stream().map(Json::write).toList()) + "]"
      );
      return v.toString();
    }
  }
}
