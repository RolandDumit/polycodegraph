package main

import (
	"go/ast"
	"go/token"
	"go/types"
	"strconv"
)

// intentContext retains compiler-bound local identities independently of primitives.
func intentContext(src Source, owners map[ast.Node]string) map[string]any {
	parents := map[ast.Node]ast.Node{}
	stack := []ast.Node{}
	ast.Inspect(src.tree, func(n ast.Node) bool {
		if n == nil {
			stack = stack[:len(stack)-1]
			return true
		}
		if len(stack) > 0 {
			parents[n] = stack[len(stack)-1]
		}
		stack = append(stack, n)
		return true
	})
	owner := func(n ast.Node) string {
		for p := n; p != nil; p = parents[p] {
			if id := owners[p]; id != "" {
				return id
			}
		}
		return src.file + "::file"
	}
	site := func(n ast.Node) map[string]any {
		p := src.pkg.Fset.Position(n.Pos())
		e := src.pkg.Fset.Position(n.End() - 1)
		return map[string]any{"line": p.Line, "end": e.Line, "offset": p.Offset, "end_offset": src.pkg.Fset.Position(n.End()).Offset, "scope": owner(n)}
	}
	statements := []any{}
	bindings := []any{}
	uses := []any{}
	controls := []any{}
	bound := map[types.Object]map[string]any{}
	ast.Inspect(src.tree, func(n ast.Node) bool {
		id, ok := n.(*ast.Ident)
		if !ok {
			return true
		}
		obj, ok := src.pkg.TypesInfo.Defs[id].(*types.Var)
		if !ok || obj.IsField() || owner(id) == src.file+"::file" {
			return true
		}
		b := site(id)
		b["id"] = src.file + "@" + strconv.Itoa(src.pkg.Fset.Position(id.Pos()).Offset)
		b["name"] = id.Name
		b["kind"] = "local"
		if _, ok := parents[id].(*ast.Field); ok {
			b["kind"] = "parameter"
		}
		b["type"] = obj.Type().String()
		bound[obj] = b
		bindings = append(bindings, b)
		return true
	})
	ast.Inspect(src.tree, func(n ast.Node) bool {
		if n == nil {
			return true
		}
		if _, ok := n.(ast.Stmt); ok {
			if block, ok := parents[n].(*ast.BlockStmt); ok {
				s := site(n)
				s["block"] = src.pkg.Fset.Position(block.Pos()).Offset
				statements = append(statements, s)
			}
		}
		kind := ""
		switch v := n.(type) {
		case *ast.ReturnStmt:
			kind = "return"
		case *ast.BranchStmt:
			if v.Tok == token.BREAK {
				kind = "break"
			} else if v.Tok == token.CONTINUE {
				kind = "continue"
			}
		case *ast.GoStmt:
			kind = "go"
		case *ast.DeferStmt:
			kind = "defer"
		}
		if kind != "" {
			s := site(n)
			s["kind"] = kind
			controls = append(controls, s)
		}
		if id, ok := n.(*ast.Ident); ok {
			obj := src.pkg.TypesInfo.Uses[id]
			if b := bound[obj]; b != nil {
				read, write := true, false
				switch p := parents[id].(type) {
				case *ast.AssignStmt:
					for _, lhs := range p.Lhs {
						if lhs == id {
							write = true
							read = p.Tok != token.ASSIGN && p.Tok != token.DEFINE
						}
					}
				case *ast.IncDecStmt:
					write = true
				}
				s := site(n)
				s["binding"] = b["id"]
				s["read"] = read
				s["write"] = write
				uses = append(uses, s)
			}
		}
		return true
	})
	return map[string]any{"capabilities": []string{"region_bindings"}, "ast": map[string]any{"version": 1, "offset_unit": "bytes", "statements": statements, "bindings": bindings, "uses": uses, "controls": controls, "limitations": []string{"No alias/escape, goroutine ordering, panic/defer behavior or hypothetical extracted type-check proof"}}}
}
