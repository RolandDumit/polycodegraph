@file:OptIn(
    org.jetbrains.kotlin.compiler.plugin.ExperimentalCompilerApi::class,
    org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class,
)

package polycodegraph

import java.io.File
import java.util.IdentityHashMap
import org.jetbrains.kotlin.backend.common.extensions.IrGenerationExtension
import org.jetbrains.kotlin.backend.common.extensions.IrPluginContext
import org.jetbrains.kotlin.compiler.plugin.CompilerPluginRegistrar
import org.jetbrains.kotlin.config.CompilerConfiguration
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

/** Intent-only PSI regions and K2 local bindings; public graph IDs stay unchanged. */
fun intentContext(moduleFragment: IrModuleFragment, ids: Map<IrSymbol, String>): List<Map<String, Any?>> {
    // Local IR symbol identities are independent of public graph declarations.
    val contexts = mutableListOf<Map<String, Any?>>()
    var file = ""
    var owner = ""
    val localKeys = IdentityHashMap<IrSymbol, String>()
    moduleFragment.acceptVoid(object : IrVisitorVoid() {
        override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
        override fun visitFile(declaration: IrFile) {
            file = declaration.fileEntry.name; owner = ""
            super.visitFile(declaration)
        }
        override fun visitDeclaration(declaration: IrDeclarationBase) {
            val previous = owner
            if (declaration is IrFunction) ids[declaration.symbol]?.let { owner = it }
            if ((declaration is IrVariable || declaration is IrValueParameter) && declaration.startOffset >= 0) {
                val binding = "$file@${declaration.startOffset}"
                localKeys[declaration.symbol] = binding
                contexts += mapOf("section" to "bindings", "file" to file, "scope" to owner, "start" to declaration.startOffset, "end" to declaration.endOffset, "id" to binding, "name" to (declaration as IrDeclarationWithName).name.asString(), "kind" to if (declaration is IrValueParameter) "parameter" else "local", "type" to if (declaration is IrVariable) declaration.type.render() else (declaration as IrValueParameter).type.render())
            }
            declaration.acceptChildrenVoid(this); owner = previous
        }
        fun use(expression: IrValueAccessExpression, read: Boolean, write: Boolean) {
            if (expression.startOffset >= 0) contexts += mapOf("section" to "uses", "file" to file, "scope" to owner, "start" to expression.startOffset, "end" to expression.endOffset, "binding" to localKeys[expression.symbol], "read" to read, "write" to write)
        }
        override fun visitGetValue(expression: IrGetValue) { use(expression, true, false); super.visitGetValue(expression) }
        override fun visitSetValue(expression: IrSetValue) { use(expression, false, true); super.visitSetValue(expression) }
    })
    // Parse source blocks rather than treating lowered IR expressions as AST boundaries.
    val disposable = com.intellij.openapi.util.Disposer.newDisposable()
    try {
        val environment = org.jetbrains.kotlin.cli.jvm.compiler.KotlinCoreEnvironment.createForProduction(disposable, CompilerConfiguration(), org.jetbrains.kotlin.cli.jvm.compiler.EnvironmentConfigFiles.JVM_CONFIG_FILES)
        val factory = org.jetbrains.kotlin.psi.KtPsiFactory(environment.project, false)
        for (irFile in moduleFragment.files) {
            val sourceFile = File(irFile.fileEntry.name)
            val psi = factory.createFile(sourceFile.name, sourceFile.readText())
            psi.accept(object : org.jetbrains.kotlin.psi.KtTreeVisitorVoid() {
                override fun visitBlockExpression(expression: org.jetbrains.kotlin.psi.KtBlockExpression) {
                    for (statement in expression.statements) contexts += mapOf("section" to "statements", "file" to sourceFile.path, "start" to statement.textRange.startOffset, "end" to statement.textRange.endOffset, "block" to expression.textRange.startOffset)
                    super.visitBlockExpression(expression)
                }
                override fun visitExpression(expression: org.jetbrains.kotlin.psi.KtExpression) {
                    val control = when(expression) { is org.jetbrains.kotlin.psi.KtReturnExpression -> "return"; is org.jetbrains.kotlin.psi.KtBreakExpression -> "break"; is org.jetbrains.kotlin.psi.KtContinueExpression -> "continue"; is org.jetbrains.kotlin.psi.KtThrowExpression -> "throw"; else -> null }
                    if (control != null) contexts += mapOf("section" to "controls", "file" to sourceFile.path, "start" to expression.textRange.startOffset, "end" to expression.textRange.endOffset, "kind" to control)
                    super.visitExpression(expression)
                }
            })
        }
    } finally { com.intellij.openapi.util.Disposer.dispose(disposable) }
    return contexts
}
