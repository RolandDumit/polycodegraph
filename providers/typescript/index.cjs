"use strict";
// No repository code, plugins or package scripts are executed by this adapter.
const ts = require("typescript");
const fs = require("node:fs");
const path = require("node:path");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const root = path.resolve(input.root);
const records = new Map(
  input.files.map(({ file, hash }) => [
    file,
    {
      file,
      hash,
      nodes: [],
      edges: [],
      dependencies: [],
      diagnostics: [],
      unresolvedCalls: 0,
    },
  ]),
);
const relative = (f) =>
  path.relative(root, path.resolve(f)).replaceAll("\\", "/");
const wanted = new Set(input.files.map((f) => path.resolve(root, f.file)));
const scopes = new Map();
for (const file of wanted) {
  const config =
    ts.findConfigFile(
      path.dirname(file),
      (f) => path.resolve(f).startsWith(root + path.sep) && fs.existsSync(f),
      "tsconfig.json",
    ) ||
    ts.findConfigFile(
      path.dirname(file),
      (f) => path.resolve(f).startsWith(root + path.sep) && fs.existsSync(f),
      "jsconfig.json",
    );
  const key = config || root;
  if (!scopes.has(key)) scopes.set(key, []);
  scopes.get(key).push(file);
}
for (const [scope, requested] of scopes) {
  let options = {
    allowJs: true,
    checkJs: true,
    jsx: ts.JsxEmit.ReactJSX,
    target: ts.ScriptTarget.ESNext,
    module: ts.ModuleKind.NodeNext,
    moduleResolution: ts.ModuleResolutionKind.NodeNext,
    noEmit: true,
    skipLibCheck: true,
  };
  let roots = requested;
  let projectReferences;
  let configDiagnostics = [];
  if (scope !== root) {
    const read = ts.readConfigFile(scope, ts.sys.readFile);
    if (read.error) configDiagnostics.push(read.error);
    const parsed = ts.parseJsonConfigFileContent(
      read.config || {},
      ts.sys,
      path.dirname(scope),
    );
    options = {
      ...parsed.options,
      noEmit: true,
      disableSourceOfProjectReferenceRedirect: false,
    };
    configDiagnostics.push(...parsed.errors);
    projectReferences = parsed.projectReferences;
    roots = [...new Set([...parsed.fileNames, ...requested])];
  }
  const program = ts.createProgram({ rootNames: roots, options, projectReferences });
  const checker = program.getTypeChecker();
  const sources = program
    .getSourceFiles()
    .filter((sf) => wanted.has(path.resolve(sf.fileName)));
  const canonical = (symbol) => {
    if (!symbol) return undefined;
    try {
      return symbol.flags & ts.SymbolFlags.Alias
        ? checker.getAliasedSymbol(symbol)
        : symbol;
    } catch {
      return symbol;
    }
  };
  const symbols = new Map(),
    constructors = new Map(),
    nodeIds = new Map();
  const location = (sf, node) => {
    const start = node.getStart(sf),
      end = node.getEnd();
    return {
      line: sf.getLineAndCharacterOfPosition(start).line + 1,
      end: sf.getLineAndCharacterOfPosition(Math.max(start, end - 1)).line + 1,
      offset: start,
      length: end - start,
    };
  };
  function edge(sf, source, target, kind, site) {
    if (!source || !target) return;
    const record = records.get(relative(sf.fileName));
    const loc = location(sf, site);
    record.edges.push({
      source,
      target,
      kind,
      file: record.file,
      line: loc.line,
      offset: loc.offset,
      confidence: "resolved",
    });
    const targetFile = target.split("::")[0];
    if (targetFile !== record.file && records.has(targetFile))
      record.dependencies.push(targetFile);
  }
  function declare(sf, node, parent, parentQ) {
    const record = records.get(relative(sf.fileName));
    let kind, name;
    if (ts.isClassDeclaration(node) || ts.isClassExpression(node)) {
      kind = "class";
      name =
        node.name?.text ||
        (ts.isVariableDeclaration(node.parent)
          ? node.parent.name.getText(sf)
          : `anonymous@${node.pos}`);
    } else if (ts.isInterfaceDeclaration(node)) {
      kind = "interface";
      name = node.name.text;
    } else if (ts.isEnumDeclaration(node)) {
      kind = "enum";
      name = node.name.text;
    } else if (ts.isEnumMember(node)) {
      kind = "field";
      name = node.name.getText(sf);
    } else if (ts.isTypeAliasDeclaration(node)) {
      kind = "typedef";
      name = node.name.text;
    } else if (ts.isFunctionDeclaration(node) && node.name) {
      kind = "function";
      name = node.name.text;
    } else if (ts.isMethodDeclaration(node) || ts.isMethodSignature(node)) {
      kind = "method";
      name = node.name.getText(sf);
    } else if (ts.isConstructorDeclaration(node)) {
      kind = "constructor";
      name = "new";
    } else if (ts.isGetAccessor(node)) {
      kind = "getter";
      name = node.name.getText(sf);
    } else if (ts.isSetAccessor(node)) {
      kind = "setter";
      name = node.name.getText(sf);
    } else if (ts.isPropertyDeclaration(node) || ts.isPropertySignature(node)) {
      kind = "field";
      name = node.name.getText(sf);
    } else if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      ts.isVariableStatement(node.parent.parent) &&
      ts.isSourceFile(node.parent.parent.parent)
    ) {
      kind =
        node.initializer &&
        (ts.isArrowFunction(node.initializer) ||
          ts.isFunctionExpression(node.initializer))
          ? "function"
          : "variable";
      name = node.name.text;
    }
    if (kind) {
      let q = parentQ ? `${parentQ}.${name}` : name;
      const symbol = canonical(
        node.name ? checker.getSymbolAtLocation(node.name) : undefined,
      );
      const overload = symbol?.declarations?.filter(
        (d) =>
          ts.isFunctionDeclaration(d) ||
          ts.isMethodDeclaration(d) ||
          ts.isMethodSignature(d),
      );
      if (overload?.length > 1 && !node.body)
        q += `(${(node.parameters || []).map((p) => p.type?.getText(sf) || "any").join(",")})`;
      const id = `${record.file}::${q}#${kind}`;
      const graphNode = {
        id,
        name,
        kind,
        file: record.file,
        q,
        ...location(sf, node),
        parent,
        tags: [],
      };
      if (!record.nodes.some((n) => n.id === id)) record.nodes.push(graphNode);
      nodeIds.set(node, id);
      edge(sf, parent, id, "contains", node);
      if (symbol && (!symbols.has(symbol) || node.body))
        symbols.set(symbol, id);
      if (kind === "constructor")
        constructors.set(
          canonical(checker.getSymbolAtLocation(node.parent.name)),
          id,
        );
      parent = id;
      parentQ = q;
      if (kind === "class" && !node.members.some(ts.isConstructorDeclaration)) {
        const ctor = {
          ...graphNode,
          id: `${record.file}::${q}.new#constructor`,
          name: "new",
          kind: "constructor",
          q: `${q}.new`,
          parent: id,
          synthetic: true,
        };
        record.nodes.push(ctor);
        constructors.set(symbol, ctor.id);
        edge(sf, id, ctor.id, "contains", node);
      }
    }
    ts.forEachChild(node, (child) => declare(sf, child, parent, parentQ));
  }
  for (const sf of sources) {
    const record = records.get(relative(sf.fileName));
    if (record.nodes.length) continue; // overlapping tsconfig scopes share declarations
    record.nodes.push({
      id: `${record.file}::file`,
      name: record.file,
      kind: "file",
      file: record.file,
      q: record.file,
      line: 1,
      end: sf.getLineAndCharacterOfPosition(sf.end).line + 1,
      offset: 0,
      length: sf.end,
      tags: [],
    });
    declare(sf, sf, `${record.file}::file`, "");
  }
  // Register already-indexed declarations as this Program owns distinct Symbol objects.
  for (const sf of sources) {
    const rec = records.get(relative(sf.fileName));
    function bind(node) {
      const id = nodeIds.get(node);
      if (!id && node.name) {
        const loc = location(sf, node);
        const candidate = rec.nodes.find(
          (n) => n.offset === loc.offset && n.kind !== "file" && !n.synthetic,
        );
        if (candidate) {
          nodeIds.set(node, candidate.id);
          if (ts.isClassDeclaration(node) || ts.isClassExpression(node)) {
            const constructor = rec.nodes.find(
              (n) =>
                n.parent === candidate.id &&
                n.kind === "constructor" &&
                n.synthetic,
            );
            if (constructor)
              constructors.set(
                canonical(checker.getSymbolAtLocation(node.name)),
                constructor.id,
              );
          }
          const sym = canonical(checker.getSymbolAtLocation(node.name));
          if (sym && (!symbols.has(sym) || node.body))
            symbols.set(sym, candidate.id);
        }
      }
      ts.forEachChild(node, bind);
    }
    bind(sf);
  }
  function targetAt(node) {
    return symbols.get(canonical(checker.getSymbolAtLocation(node)));
  }
  function visit(sf, node, owner) {
    owner = nodeIds.get(node) || owner;
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      if (node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
        const resolved = ts.resolveModuleName(
          node.moduleSpecifier.text,
          sf.fileName,
          options,
          ts.sys,
        ).resolvedModule;
        if (resolved && records.has(relative(resolved.resolvedFileName)))
          edge(
            sf,
            `${relative(sf.fileName)}::file`,
            `${relative(resolved.resolvedFileName)}::file`,
            ts.isImportDeclaration(node) ? "imports" : "exports",
            node,
          );
      }
    }
    // Resolve static CommonJS/import-equals/dynamic-import module dependencies.
    let moduleLiteral;
    if (
      ts.isImportEqualsDeclaration(node) &&
      ts.isExternalModuleReference(node.moduleReference)
    )
      moduleLiteral = node.moduleReference.expression;
    if (ts.isCallExpression(node) && node.arguments.length === 1) {
      const exp = node.expression;
      if (exp.kind === ts.SyntaxKind.ImportKeyword)
        moduleLiteral = node.arguments[0];
      if (ts.isIdentifier(exp) && exp.text === "require") {
        const local = checker
          .getSymbolAtLocation(exp)
          ?.declarations?.some((d) =>
            wanted.has(path.resolve(d.getSourceFile().fileName)),
          );
        if (!local) moduleLiteral = node.arguments[0];
      }
    }
    if (moduleLiteral && ts.isStringLiteral(moduleLiteral)) {
      const resolved = ts.resolveModuleName(
        moduleLiteral.text,
        sf.fileName,
        options,
        ts.sys,
      ).resolvedModule;
      if (resolved && records.has(relative(resolved.resolvedFileName)))
        edge(
          sf,
          `${relative(sf.fileName)}::file`,
          `${relative(resolved.resolvedFileName)}::file`,
          "imports",
          node,
        );
    }
    if (
      (ts.isClassDeclaration(node) || ts.isInterfaceDeclaration(node)) &&
      node.heritageClauses
    ) {
      for (const clause of node.heritageClauses)
        for (const type of clause.types) {
          edge(
            sf,
            owner,
            targetAt(type.expression),
            clause.token === ts.SyntaxKind.ImplementsKeyword
              ? "implements"
              : "extends",
            type,
          );
        }
    }
    if (
      (ts.isMethodDeclaration(node) ||
        ts.isMethodSignature(node) ||
        ts.isGetAccessor(node) ||
        ts.isSetAccessor(node)) &&
      node.parent.name
    ) {
      for (const clause of node.parent.heritageClauses || [])
        for (const type of clause.types) {
          const base = checker.getTypeAtLocation(type);
          const member = canonical(
            checker.getPropertyOfType(base, node.name.getText(sf)),
          );
          edge(sf, owner, symbols.get(member), "overrides", node);
        }
    }
    if (ts.isCallExpression(node) || ts.isNewExpression(node)) {
      const signature = checker.getResolvedSignature(node);
      const declaration = signature?.declaration;
      let target = declaration && nodeIds.get(declaration);
      if (!target)
        target = targetAt(
          ts.isPropertyAccessExpression(node.expression)
            ? node.expression.name
            : node.expression,
        );
      if (ts.isNewExpression(node))
        target =
          constructors.get(
            canonical(checker.getSymbolAtLocation(node.expression)),
          ) || target;
      if (target) edge(sf, owner, target, "calls", node);
      else if (!signature || !declaration)
        records.get(relative(sf.fileName)).unresolvedCalls++;
    }
    if (
      ts.isIdentifier(node) &&
      (node.parent.name !== node ||
        ts.isPropertyAccessExpression(node.parent) ||
        ts.isQualifiedName(node.parent)) &&
      !ts.isImportSpecifier(node.parent) &&
      !ts.isImportClause(node.parent) &&
      !ts.isExportSpecifier(node.parent)
    )
      edge(sf, owner, targetAt(node), "references", node);
    ts.forEachChild(node, (child) => visit(sf, child, owner));
  }
  for (const sf of sources) visit(sf, sf, `${relative(sf.fileName)}::file`);
  for (const diagnostic of [
    ...configDiagnostics,
    ...ts.getPreEmitDiagnostics(program),
  ]) {
    const file = diagnostic.file
      ? relative(diagnostic.file.fileName)
      : relative(requested[0]);
    const rec = records.get(file);
    if (!rec || rec.diagnostics.length >= 200) continue;
    rec.diagnostics.push({
      severity:
        diagnostic.category === ts.DiagnosticCategory.Error
          ? "error"
          : "warning",
      code: `TS${diagnostic.code}`,
      message: ts
        .flattenDiagnosticMessageText(diagnostic.messageText, "\n")
        .slice(0, 2000),
      line: diagnostic.file
        ? diagnostic.file.getLineAndCharacterOfPosition(diagnostic.start || 0)
            .line + 1
        : 1,
    });
  }
}
for (const rec of records.values()) {
  rec.dependencies = [...new Set(rec.dependencies)].sort();
  rec.edges = [
    ...new Map(rec.edges.map((e) => [JSON.stringify(e), e])).values(),
  ].sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b), "en"));
  rec.nodes.sort((a, b) => a.id.localeCompare(b.id, "en"));
}
const emitted = new Set(input.options?.emit_files ?? input.files.map((f) => f.file));
process.stdout.write(JSON.stringify([...records.values()].filter((r) => emitted.has(r.file))));
