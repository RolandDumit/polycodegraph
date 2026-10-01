use crate::domain::{MemoryRepository as Store, Repository};

pub fn load(repository: &dyn Repository) -> u32 {
    repository.fetch()
}

pub fn concrete() -> u32 {
    let repository = Store { prefix: 1 };
    repository.fetch()
}
