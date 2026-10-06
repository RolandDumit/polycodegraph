//! Counters collected during existing hash reads, without a second inventory scan.
#[derive(Default, Debug, Clone, serde::Serialize)]
pub struct HashVolume {
    pub files: u64,
    pub bytes: u64,
}
impl HashVolume {
    pub fn record(&mut self, bytes: usize) {
        self.files += 1;
        self.bytes += bytes as u64;
    }
}
#[derive(Default, Debug, Clone, serde::Serialize)]
pub struct HashWork {
    pub source: HashVolume,
    pub dependency: HashVolume,
    pub provider_asset: HashVolume,
}
impl HashWork {
    pub fn add(&mut self, other: &Self) {
        self.source.files += other.source.files;
        self.source.bytes += other.source.bytes;
        self.dependency.files += other.dependency.files;
        self.dependency.bytes += other.dependency.bytes;
        self.provider_asset.files += other.provider_asset.files;
        self.provider_asset.bytes += other.provider_asset.bytes;
    }
}
