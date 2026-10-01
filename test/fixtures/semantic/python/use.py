from .domain import MemoryRepository as Store, Repository


def load(repository: Repository) -> str:
    return repository.fetch()


def concrete() -> str:
    return Store().fetch()


async def load_async(repository: Repository) -> str:
    return repository.fetch()


def dynamic(callback) -> str:
    return callback()
