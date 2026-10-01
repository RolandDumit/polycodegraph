// PolyCodeGraph compiler adapter. It never executes packages being indexed.
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/types"
	"golang.org/x/tools/go/packages"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type InputFile struct {
	File string `json:"file"`
	Hash string `json:"hash"`
}
type Input struct {
	Root    string      `json:"root"`
	Files   []InputFile `json:"files"`
	Options struct {
		EmitFiles []string `json:"emit_files"`
	} `json:"options"`
}
type Node struct {
	ID     string   `json:"id"`
	Name   string   `json:"name"`
	Kind   string   `json:"kind"`
	File   string   `json:"file"`
	Q      string   `json:"q"`
	Line   int      `json:"line"`
	End    int      `json:"end"`
	Offset int      `json:"offset"`
	Length int      `json:"length"`
	Parent string   `json:"parent,omitempty"`
	Tags   []string `json:"tags"`
}
type Edge struct {
	Source     string `json:"source"`
	Target     string `json:"target"`
	Kind       string `json:"kind"`
	File       string `json:"file"`
	Line       int    `json:"line"`
	Offset     int    `json:"offset"`
	Confidence string `json:"confidence"`
}
type Diagnostic struct {
	Severity string `json:"severity"`
	Code     string `json:"code"`
	Message  string `json:"message"`
	Line     int    `json:"line"`
}
type Record struct {
	File         string       `json:"file"`
	Hash         string       `json:"hash"`
	Nodes        []Node       `json:"nodes"`
	Edges        []Edge       `json:"edges"`
	Dependencies []string     `json:"dependencies"`
	Diagnostics  []Diagnostic `json:"diagnostics"`
	Unresolved   int          `json:"unresolvedCalls"`
}
type Source struct {
	pkg  *packages.Package
	tree *ast.File
	file string
}
type Decl struct {
	obj types.Object
	id  string
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	var input Input
	if err := json.NewDecoder(os.Stdin).Decode(&input); err != nil {
		return err
	}
	records := map[string]*Record{}
	wanted := map[string]string{}
	scopes := map[string][]string{}
	rel := func(f string) string { r, _ := filepath.Rel(input.Root, f); return filepath.ToSlash(r) }
	for _, f := range input.Files {
		abs := filepath.Join(input.Root, filepath.FromSlash(f.File))
		wanted[abs] = f.File
		records[f.File] = &Record{File: f.File, Hash: f.Hash, Nodes: []Node{}, Edges: []Edge{}, Dependencies: []string{}, Diagnostics: []Diagnostic{}}
		scope := filepath.Dir(abs)
		for d := scope; ; d = filepath.Dir(d) {
			if _, err := os.Stat(filepath.Join(d, "go.mod")); err == nil {
				scope = d
				break
			}
			if d == input.Root || filepath.Dir(d) == d {
				break
			}
		}
		scopes[scope] = append(scopes[scope], abs)
	}
	var sources []Source
	seen := map[string]bool{}
	var allpkgs []*packages.Package
	keys := make([]string, 0, len(scopes))
	for k := range scopes {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, scope := range keys {
		patterns := []string{}
		for _, f := range scopes[scope] {
			patterns = append(patterns, "file="+f)
		}
		loaded, err := packages.Load(&packages.Config{Dir: scope, Env: append(os.Environ(), "GOPROXY=off", "GOSUMDB=off", "GOPACKAGESDRIVER=off"), BuildFlags: []string{"-mod=readonly"}, Mode: packages.NeedName | packages.NeedFiles | packages.NeedCompiledGoFiles | packages.NeedImports | packages.NeedDeps | packages.NeedTypes | packages.NeedSyntax | packages.NeedTypesInfo | packages.NeedTypesSizes, Tests: true}, patterns...)
		if err != nil {
			return err
		}
		packages.Visit(loaded, nil, func(pkg *packages.Package) {
			allpkgs = append(allpkgs, pkg)
			for _, tree := range pkg.Syntax {
				abs := pkg.Fset.Position(tree.Pos()).Filename
				file, ok := wanted[abs]
				if !ok || seen[file] {
					continue
				}
				seen[file] = true
				sources = append(sources, Source{pkg, tree, file})
			}
			for _, e := range pkg.Errors {
				for _, file := range input.Files {
					rec := records[file.File]
					if strings.HasPrefix(e.Pos, filepath.Join(input.Root, file.File)+":") && len(rec.Diagnostics) < 200 {
						rec.Diagnostics = append(rec.Diagnostics, Diagnostic{"error", "go_typecheck", e.Msg, 1})
					}
				}
			}
		})
	}
	sort.Slice(sources, func(i, j int) bool { return sources[i].file < sources[j].file })
	symbols := map[string]string{}
	owners := map[ast.Node]string{}
	receiverKeys := map[string]string{}
	var typesDecl []Decl
	objectKeys := map[types.Object]string{}
	objKey := func(pkg *packages.Package, obj types.Object) string {
		if obj == nil {
			return ""
		}
		if f, ok := obj.(*types.Func); ok {
			obj = f.Origin()
		}
		if key := objectKeys[obj]; key != "" {
			return key
		}
		pos := pkg.Fset.Position(obj.Pos())
		key := filepath.Clean(pos.Filename) + fmt.Sprint(":", pos.Offset)
		objectKeys[obj] = key
		return key
	}
	addEdge := func(src Source, source, target, kind string, node ast.Node) {
		if source == "" || target == "" {
			return
		}
		pos := src.pkg.Fset.Position(node.Pos())
		rec := records[src.file]
		rec.Edges = append(rec.Edges, Edge{source, target, kind, src.file, pos.Line, pos.Offset, "resolved"})
		f := strings.Split(target, "::")[0]
		if f != src.file && records[f] != nil {
			rec.Dependencies = append(rec.Dependencies, f)
		}
	}
	for _, src := range sources {
		rec := records[src.file]
		text, err := os.ReadFile(filepath.Join(input.Root, src.file))
		if err != nil {
			return err
		}
		rec.Nodes = append(rec.Nodes, Node{ID: src.file + "::file", Name: src.file, Kind: "file", File: src.file, Q: src.file, Line: 1, End: strings.Count(string(text), "\n") + 1, Length: len(text), Tags: []string{}})
		var walk func(ast.Node, string, string)
		walk = func(node ast.Node, parent, qparent string) {
			if node == nil {
				return
			}
			kind, name := "", ""
			var obj types.Object
			receiverKey := ""
			switch n := node.(type) {
			case *ast.TypeSpec:
				name = n.Name.Name
				obj = src.pkg.TypesInfo.Defs[n.Name]
				kind = "type"
				switch n.Type.(type) {
				case *ast.StructType:
					kind = "struct"
				case *ast.InterfaceType:
					kind = "interface"
				}
				if n.Assign.IsValid() {
					kind = "typedef"
				}
			case *ast.FuncDecl:
				name = n.Name.Name
				obj = src.pkg.TypesInfo.Defs[n.Name]
				kind = "function"
				if n.Recv != nil {
					kind = "method"
					if f, ok := obj.(*types.Func); ok {
						sig := f.Type().(*types.Signature)
						t := sig.Recv().Type()
						if ptr, ok := t.(*types.Pointer); ok {
							t = ptr.Elem()
						}
						if named, ok := t.(*types.Named); ok {
							qparent = named.Obj().Name()
							receiverKey = objKey(src.pkg, named.Obj())
						}
					}
				}
			case *ast.Field:
				if strings.HasSuffix(parent, "#struct") || strings.HasSuffix(parent, "#interface") {
					for _, ident := range n.Names {
						if ident.Name == "_" {
							continue
						}
						fieldObj := src.pkg.TypesInfo.Defs[ident]
						fk := "field"
						if _, ok := fieldObj.(*types.Func); ok {
							fk = "method"
						}
						p := src.pkg.Fset.Position(n.Pos())
						end := src.pkg.Fset.Position(n.End())
						q := qparent + "." + ident.Name
						id := src.file + "::" + q + "#" + fk
						rec.Nodes = append(rec.Nodes, Node{id, ident.Name, fk, src.file, q, p.Line, end.Line, p.Offset, end.Offset - p.Offset, parent, []string{}})
						symbols[objKey(src.pkg, fieldObj)] = id
						addEdge(src, parent, id, "contains", n)
					}
				}
			case *ast.ValueSpec:
				if strings.HasSuffix(parent, "::file") {
					for _, ident := range n.Names {
						if ident.Name == "_" {
							continue
						}
						v := src.pkg.TypesInfo.Defs[ident]
						p := src.pkg.Fset.Position(n.Pos())
						end := src.pkg.Fset.Position(n.End())
						k := "variable"
						if _, ok := v.(*types.Const); ok {
							k = "constant"
						}
						id := src.file + "::" + ident.Name + "#" + k
						rec.Nodes = append(rec.Nodes, Node{id, ident.Name, k, src.file, ident.Name, p.Line, end.Line, p.Offset, end.Offset - p.Offset, parent, []string{}})
						symbols[objKey(src.pkg, v)] = id
						addEdge(src, parent, id, "contains", n)
					}
				}
			}
			if kind != "" && obj != nil {
				q := name
				if qparent != "" {
					q = qparent + "." + name
				}
				id := src.file + "::" + q + "#" + kind
				p := src.pkg.Fset.Position(node.Pos())
				end := src.pkg.Fset.Position(node.End())
				rec.Nodes = append(rec.Nodes, Node{id, name, kind, src.file, q, p.Line, end.Line, p.Offset, end.Offset - p.Offset, parent, []string{}})
				symbols[objKey(src.pkg, obj)] = id
				owners[node] = id
				if receiverKey != "" {
					receiverKeys[id] = receiverKey
				}
				addEdge(src, parent, id, "contains", node)
				if _, ok := obj.(*types.TypeName); ok {
					typesDecl = append(typesDecl, Decl{obj, id})
				}
				parent = id
				qparent = q
			}
			ast.Inspect(node, func(child ast.Node) bool {
				if child == node {
					return true
				}
				if child != nil {
					walk(child, parent, qparent)
				}
				return false
			})
		}
		walk(src.tree, src.file+"::file", "")
	}
	for _, src := range sources {
		rec := records[src.file]
		// Receiver methods belong to their named type, not just the source file.
		for i := range rec.Nodes {
			member := &rec.Nodes[i]
			if member.Kind != "method" || !strings.HasSuffix(member.Parent, "::file") {
				continue
			}
			if container := symbols[receiverKeys[member.ID]]; container != "" {
				member.Parent = container
				for j := range rec.Edges {
					if rec.Edges[j].Kind == "contains" && rec.Edges[j].Target == member.ID {
						rec.Edges[j].Source = container
					}
				}
			}
		}
		var walk func(ast.Node, string)
		walk = func(node ast.Node, owner string) {
			if node == nil {
				return
			}
			if id := owners[node]; id != "" {
				owner = id
			}
			if ident, ok := node.(*ast.Ident); ok {
				if obj := src.pkg.TypesInfo.Uses[ident]; obj != nil {
					addEdge(src, owner, symbols[objKey(src.pkg, obj)], "references", ident)
				}
			}
			if call, ok := node.(*ast.CallExpr); ok {
				fn := call.Fun
				switch n := fn.(type) {
				case *ast.IndexExpr:
					fn = n.X
				case *ast.IndexListExpr:
					fn = n.X
				}
				var obj types.Object
				switch n := fn.(type) {
				case *ast.Ident:
					obj = src.pkg.TypesInfo.Uses[n]
				case *ast.SelectorExpr:
					if selection := src.pkg.TypesInfo.Selections[n]; selection != nil {
						obj = selection.Obj()
					} else {
						obj = src.pkg.TypesInfo.Uses[n.Sel]
					}
				}
				switch obj.(type) {
				case *types.Func:
					addEdge(src, owner, symbols[objKey(src.pkg, obj)], "calls", call)
				case *types.TypeName, *types.Builtin:
				default:
					rec.Unresolved++
				}
			}
			if imp, ok := node.(*ast.ImportSpec); ok {
				importPath := strings.Trim(imp.Path.Value, "\"")
				if imported := src.pkg.Imports[importPath]; imported != nil {
					for _, f := range imported.CompiledGoFiles {
						rf := rel(f)
						if records[rf] != nil {
							addEdge(src, src.file+"::file", rf+"::file", "imports", imp)
						}
					}
				}
			}
			ast.Inspect(node, func(child ast.Node) bool {
				if child == node {
					return true
				}
				if child != nil {
					walk(child, owner)
				}
				return false
			})
		}
		walk(src.tree, src.file+"::file")
		for _, declaration := range typesDecl {
			if !strings.HasPrefix(declaration.id, src.file+"::") {
				continue
			}
			candidate := declaration.obj.Type()
			named, ok := candidate.(*types.Named)
			if !ok {
				continue
			}
			for _, contract := range typesDecl {
				iface, ok := contract.obj.Type().Underlying().(*types.Interface)
				if !ok || contract.id == declaration.id {
					continue
				}
				iface.Complete()
				if !types.Implements(candidate, iface) && !types.Implements(types.NewPointer(named), iface) {
					continue
				}
				addEdge(src, declaration.id, contract.id, "implements", src.tree)
				for i := 0; i < iface.NumMethods(); i++ {
					method := iface.Method(i)
					obj, _, _ := types.LookupFieldOrMethod(types.NewPointer(named), true, method.Pkg(), method.Name())
					addEdge(src, symbols[objKey(src.pkg, obj)], symbols[objKey(src.pkg, method)], "overrides", src.tree)
				}
			}
		}
	}
	output := []*Record{}
	for _, file := range input.Files {
		rec := records[file.File]
		if len(rec.Nodes) == 0 {
			data, _ := os.ReadFile(filepath.Join(input.Root, file.File))
			rec.Nodes = append(rec.Nodes, Node{ID: file.File + "::file", Name: file.File, Kind: "file", File: file.File, Q: file.File, Line: 1, End: strings.Count(string(data), "\n") + 1, Length: len(data), Tags: []string{}})
			rec.Diagnostics = append(rec.Diagnostics, Diagnostic{"warning", "go_build_excluded", "File is excluded by build constraints or package loading failed", 1})
		}
		dep := map[string]bool{}
		for _, d := range rec.Dependencies {
			dep[d] = true
		}
		rec.Dependencies = []string{}
		for d := range dep {
			rec.Dependencies = append(rec.Dependencies, d)
		}
		sort.Strings(rec.Dependencies)
		sort.Slice(rec.Nodes, func(i, j int) bool { return rec.Nodes[i].ID < rec.Nodes[j].ID })
		sort.Slice(rec.Edges, func(i, j int) bool {
			a, _ := json.Marshal(rec.Edges[i])
			b, _ := json.Marshal(rec.Edges[j])
			return string(a) < string(b)
		})
		if input.Options.EmitFiles == nil {
			output = append(output, rec)
		} else {
			for _, emitted := range input.Options.EmitFiles {
				if emitted == rec.File {
					output = append(output, rec)
					break
				}
			}
		}
	}
	return json.NewEncoder(os.Stdout).Encode(output)
}
