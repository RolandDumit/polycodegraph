func load(_ repository: any Repository) -> String { repository.fetch() }
func make() -> String { MemoryRepository(prefix: "data").fetch() }
func callback(_ action: () -> String) -> String { action() }
