protocol Repository { func fetch() -> String }
class MemoryRepository: Repository {
    let prefix: String
    init(prefix: String) { self.prefix = prefix }
    func fetch() -> String { prefix }
}
class Unrelated { func fetch() -> String { "other" } }
struct Record { let value: String }
enum State { case ready, waiting }
typealias Label = String
extension MemoryRepository { func reload() -> String { fetch() } }
class ChildRepository: MemoryRepository { override func fetch() -> String { super.fetch() } }
