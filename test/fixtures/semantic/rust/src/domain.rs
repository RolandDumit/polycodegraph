pub trait Repository {
    fn fetch(&self) -> u32;
}

pub struct MemoryRepository {
    pub prefix: u32,
}

impl Repository for MemoryRepository {
    fn fetch(&self) -> u32 {
        self.prefix
    }
}

pub struct Unrelated;

impl Unrelated {
    pub fn fetch(&self) -> u32 {
        999
    }
}

pub enum LoadState {
    Idle,
    Loaded,
}

pub type Identifier = u32;
pub const DEFAULT_ID: Identifier = 1;
