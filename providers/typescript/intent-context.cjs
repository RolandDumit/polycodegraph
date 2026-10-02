// AST/binding facts for bounded extraction context. Does not modify graph primitives.
module.exports = function context(ts, checker, sf, file, nodeIds) {
  const ast = { version: 1, offset_unit: "utf16", statements: [], bindings: [], uses: [], controls: [], limitations: ["No alias/lifetime, callback execution, destructuring-assignment or hypothetical type-check proof"] };
  const bound = new Map();
  function owner(node) { for(let n=node;n;n=n.parent) { if(nodeIds.has(n)) return nodeIds.get(n); } return `${file}::file`; }
  function site(node) { const start=node.getStart(sf); return {line:sf.getLineAndCharacterOfPosition(start).line+1,end:sf.getLineAndCharacterOfPosition(Math.max(start,node.end-1)).line+1,offset:start,end_offset:node.end,scope:owner(node)}; }
  function visit(node, callback) { callback(node); ts.forEachChild(node, child=>visit(child,callback)); }
  visit(sf, node => {
    if ((ts.isParameter(node)||ts.isVariableDeclaration(node)||ts.isBindingElement(node)) && node.name && ts.isIdentifier(node.name)) {
      const scope=owner(node); if(scope===`${file}::file`)return;
      const symbol=checker.getSymbolAtLocation(node.name); if(!symbol)return;
      const binding={...site(node.name),id:`${file}@${node.name.getStart(sf)}`,name:node.name.text,kind:ts.isParameter(node)?"parameter":"local",type:checker.typeToString(checker.getTypeAtLocation(node.name))};
      bound.set(symbol,binding);ast.bindings.push(binding);
    }
  });
  visit(sf, node => {
    if (ts.isStatement(node) && (ts.isBlock(node.parent)||ts.isSourceFile(node.parent))) ast.statements.push({...site(node),block:node.parent.getStart(sf)});
    let kind=ts.isReturnStatement(node)?"return":ts.isBreakStatement(node)?"break":ts.isContinueStatement(node)?"continue":ts.isAwaitExpression(node)?"await":ts.isThrowStatement(node)?"throw":ts.isYieldExpression(node)?"yield":undefined;
    if(kind)ast.controls.push({...site(node),kind});
    if(!ts.isIdentifier(node))return;
    const symbol = ts.isShorthandPropertyAssignment(node.parent) ? checker.getShorthandAssignmentValueSymbol(node.parent) : checker.getSymbolAtLocation(node);
    const binding=bound.get(symbol);if(!binding || node.getStart(sf)===binding.offset)return;
    const p=node.parent; let write=false,read=true;
    if(ts.isBinaryExpression(p)&&p.left===node&&p.operatorToken.kind>=ts.SyntaxKind.FirstAssignment&&p.operatorToken.kind<=ts.SyntaxKind.LastAssignment) {write=true;read=p.operatorToken.kind!==ts.SyntaxKind.EqualsToken;}
    if((ts.isPrefixUnaryExpression(p)||ts.isPostfixUnaryExpression(p))&&[ts.SyntaxKind.PlusPlusToken,ts.SyntaxKind.MinusMinusToken].includes(p.operator))write=true;
    ast.uses.push({...site(node),binding:binding.id,read,write});
  });
  return ast;
};
