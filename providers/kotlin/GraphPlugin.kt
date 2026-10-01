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

class Registrar : CompilerPluginRegistrar() {
    override val supportsK2 = true
    override val pluginId = "polycodegraph"

    override fun ExtensionStorage.registerExtensions(configuration: CompilerConfiguration) {
        IrGenerationExtension.registerExtension(Extractor())
    }
}

private fun json(value: Any?): String =
    when (value) {
        null -> "null"
        is String ->
            "\"" +
                value
                    .flatMap {
                        when (it) {
                            '\\' -> "\\\\"
                            '"' -> "\\\""
                            '\n' -> "\\n"
                            '\r' -> "\\r"
                            '\t' -> "\\t"
                            else -> if (it.code < 32) "\\u%04x".format(it.code) else it.toString()
                        }.toList()
                    }
                    .joinToString("") +
                "\""
        is Number,
        is Boolean -> value.toString()
        is Map<*, *> ->
            value.entries.joinToString(",", "{", "}") {
                json(it.key.toString()) + ":" + json(it.value)
            }
        is Iterable<*> -> value.joinToString(",", "[", "]") { json(it) }
        else -> json(value.toString())
    }

class Extractor : IrGenerationExtension {
    override fun generate(moduleFragment: IrModuleFragment, pluginContext: IrPluginContext) {
        val ids = IdentityHashMap<IrSymbol, String>()
        val rows = mutableListOf<Map<String, Any?>>()
        val edges = mutableListOf<Map<String, Any?>>()
        var file = ""
        var owner = ""
        fun key(symbol: IrSymbol): String = ids.getOrPut(symbol) { "s${ids.size}" }
        fun qualified(declaration: IrDeclaration): String {
            if (declaration is IrConstructor)
                return qualified(declaration.parent as IrDeclaration) +
                    ".<init>(" +
                    declaration.parameters
                        .filter { it.kind != IrParameterKind.DispatchReceiver }
                        .joinToString(",") { it.type.render() } +
                    ")"
            val prefix =
                when (val parent = declaration.parent) {
                    is IrDeclaration -> qualified(parent) + "."
                    else -> ""
                }
            val name = (declaration as? IrDeclarationWithName)?.name?.asString() ?: "anonymous"
            return prefix +
                name +
                if (declaration is IrSimpleFunction)
                    "(" +
                        declaration.parameters
                            .filter { it.kind != IrParameterKind.DispatchReceiver }
                            .joinToString(",") { it.type.render() } +
                        ")"
                else ""
        }
        fun kind(declaration: IrDeclaration): String? =
            when (declaration) {
                is IrClass ->
                    when (declaration.kind.toString()) {
                        "INTERFACE" -> "interface"
                        "ENUM_CLASS" -> "enum"
                        else -> "class"
                    }
                is IrConstructor -> "constructor"
                is IrSimpleFunction ->
                    if (declaration.correspondingPropertySymbol != null) "accessor"
                    else if (declaration.parent is IrClass) "method" else "function"
                is IrProperty -> "field"
                is IrField -> null
                is IrEnumEntry -> "enumConstant"
                is IrTypeAlias -> "typedef"
                else -> null
            }
        moduleFragment.acceptVoid(
            object : IrVisitorVoid() {
                override fun visitElement(element: IrElement) {
                    element.acceptChildrenVoid(this)
                }

                override fun visitFile(declaration: IrFile) {
                    file = declaration.fileEntry.name
                    owner = ""
                    super.visitFile(declaration)
                }

                override fun visitDeclaration(declaration: IrDeclarationBase) {
                    val type = kind(declaration)
                    val previous = owner
                    if (
                        type != null && declaration.startOffset >= 0 && !declaration.isFakeOverride
                    ) {
                        val id = key(declaration.symbol)
                        rows +=
                            mapOf(
                                "key" to id,
                                "file" to file,
                                "name" to
                                    ((declaration as? IrDeclarationWithName)?.name?.asString()
                                        ?: "<init>"),
                                "qualified" to qualified(declaration),
                                "kind" to type,
                                "start" to declaration.startOffset,
                                "end" to declaration.endOffset,
                                "parent" to owner,
                                "tags" to
                                    listOfNotNull(
                                        if (
                                            declaration is IrSimpleFunction && declaration.isSuspend
                                        )
                                            "suspend"
                                        else null,
                                        if (declaration is IrClass && declaration.isData) "data"
                                        else null,
                                    ),
                            )
                        if (declaration is IrProperty)
                            declaration.backingField?.let { ids[it.symbol] = id }
                        owner = id
                    }
                    declaration.acceptChildrenVoid(this)
                    owner = previous
                }
            }
        )
        moduleFragment.acceptVoid(
            object : IrVisitorVoid() {
                override fun visitElement(element: IrElement) {
                    element.acceptChildrenVoid(this)
                }

                override fun visitFile(declaration: IrFile) {
                    file = declaration.fileEntry.name
                    owner = ""
                    super.visitFile(declaration)
                }

                override fun visitDeclaration(declaration: IrDeclarationBase) {
                    val previous = owner
                    ids[declaration.symbol]?.let { owner = it }
                    if (ids.containsKey(declaration.symbol) && declaration is IrClass)
                        for (type in declaration.superTypes) type.classOrNull?.let {
                            edge("inherits", it, declaration.startOffset)
                        }
                    if (ids.containsKey(declaration.symbol) && declaration is IrSimpleFunction)
                        for (symbol in declaration.overriddenSymbols) edge(
                            "overrides",
                            symbol,
                            declaration.startOffset,
                        )
                    declaration.acceptChildrenVoid(this)
                    owner = previous
                }

                fun edge(kind: String, target: IrSymbol, start: Int) {
                    edges +=
                        mapOf(
                            "file" to file,
                            "source" to owner,
                            "target" to key(target),
                            "kind" to kind,
                            "start" to start,
                        )
                }

                override fun visitCall(expression: IrCall) {
                    val resolved = expression.symbol.owner.resolveFakeOverrideOrSelf()
                    val receiver =
                        (resolved.parent as? IrClass)?.fqNameWhenAvailable?.asString().orEmpty()
                    val dynamic =
                        resolved.name.asString() == "invoke" &&
                            (receiver.startsWith("kotlin.Function") ||
                                receiver.startsWith("kotlin.coroutines.SuspendFunction"))
                    edge(
                        if (dynamic) "dynamicCall" else "calls",
                        resolved.symbol,
                        expression.startOffset,
                    )
                    super.visitCall(expression)
                }

                override fun visitConstructorCall(expression: IrConstructorCall) {
                    edge("calls", expression.symbol, expression.startOffset)
                    super.visitConstructorCall(expression)
                }

                override fun visitGetField(expression: IrGetField) {
                    edge("references", expression.symbol, expression.startOffset)
                    super.visitGetField(expression)
                }

                override fun visitSetField(expression: IrSetField) {
                    edge("references", expression.symbol, expression.startOffset)
                    super.visitSetField(expression)
                }

                override fun visitFunctionReference(expression: IrFunctionReference) {
                    edge("references", expression.symbol, expression.startOffset)
                    super.visitFunctionReference(expression)
                }

                override fun visitGetObjectValue(expression: IrGetObjectValue) {
                    edge("references", expression.symbol, expression.startOffset)
                    super.visitGetObjectValue(expression)
                }
            }
        )
        File(System.getenv("POLYCODEGRAPH_KOTLIN_OUTPUT") ?: error("Missing output"))
            .writeText(json(mapOf("nodes" to rows, "edges" to edges)))
    }
}
