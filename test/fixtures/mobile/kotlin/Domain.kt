package demo
interface Repository { fun fetch(): String }
open class MemoryRepository(val prefix: String): Repository {
    override fun fetch() = prefix
    fun overloaded(value: String) = value
    fun overloaded(value: Int) = value.toString()
}
class ChildRepository: MemoryRepository("child")
class Unrelated { fun fetch() = "other" }
data class Record(val value: String)
enum class State { Ready, Waiting }
typealias Label = String
object Registry { val active = true }
fun MemoryRepository.reload() = fetch()
