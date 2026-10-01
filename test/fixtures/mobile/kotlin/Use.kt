package demo
import demo.MemoryRepository as Store
fun load(repository: Repository) = repository.fetch()
fun make() = Store("data").fetch()
fun inherited(repository: ChildRepository) = repository.fetch()
suspend fun loadAsync(repository: Repository) = repository.fetch()
fun callback(action: () -> String) = action()
