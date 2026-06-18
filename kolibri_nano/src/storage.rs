use std::path::PathBuf;
use std::fs;
use serde::{Deserialize, Serialize};
use anyhow::Result;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StorageConfig {
    pub data_dir: PathBuf,
}

impl Default for StorageConfig {
    fn default() -> Self {
        Self {
            data_dir: PathBuf::from("/opt/kolibri-ai/data/nano"),
        }
    }
}

pub struct Storage {
    config: StorageConfig,
}

impl Storage {
    pub fn new(config: StorageConfig) -> Self {
        Self { config }
    }

    pub fn init(&self) -> Result<()> {
        fs::create_dir_all(&self.config.data_dir)?;
        fs::create_dir_all(self.config.data_dir.join("traces"))?;
        fs::create_dir_all(self.config.data_dir.join("memory"))?;
        fs::create_dir_all(self.config.data_dir.join("estimates"))?;
        Ok(())
    }

    pub fn save_json<T: Serialize>(&self, subdir: &str, name: &str, data: &T) -> Result<()> {
        let path = self.config.data_dir.join(subdir).join(format!("{}.json", name));
        let json = serde_json::to_string_pretty(data)?;
        fs::write(path, json)?;
        Ok(())
    }

    pub fn load_json<T: for<'de> Deserialize<'de>>(&self, subdir: &str, name: &str) -> Result<T> {
        let path = self.config.data_dir.join(subdir).join(format!("{}.json", name));
        let json = fs::read_to_string(path)?;
        let data = serde_json::from_str(&json)?;
        Ok(data)
    }

    pub fn exists(&self, subdir: &str, name: &str) -> bool {
        self.config.data_dir.join(subdir).join(format!("{}.json", name)).exists()
    }

    pub fn list_files(&self, subdir: &str) -> Vec<String> {
        let dir = self.config.data_dir.join(subdir);
        if !dir.exists() {
            return Vec::new();
        }
        fs::read_dir(dir)
            .ok()
            .into_iter()
            .flatten()
            .filter_map(|e| e.ok())
            .filter(|e| e.path().extension().map(|ext| ext == "json").unwrap_or(false))
            .filter_map(|e| e.path().file_stem().map(|s| s.to_string_lossy().to_string()))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn test_storage() -> (Storage, TempDir) {
        let tmp = TempDir::new().unwrap();
        let config = StorageConfig { data_dir: tmp.path().to_path_buf() };
        let storage = Storage::new(config);
        storage.init().unwrap();
        (storage, tmp)
    }

    #[test]
    fn test_save_load() {
        let (storage, _tmp) = test_storage();
        let data = vec!["hello", "world"];
        storage.save_json("memory", "test", &data).unwrap();
        let loaded: Vec<String> = storage.load_json("memory", "test").unwrap();
        assert_eq!(loaded, data);
    }

    #[test]
    fn test_exists_and_list() {
        let (storage, _tmp) = test_storage();
        assert!(!storage.exists("traces", "abc"));
        storage.save_json("traces", "abc", &"value").unwrap();
        assert!(storage.exists("traces", "abc"));
        let files = storage.list_files("traces");
        assert!(files.contains(&"abc".to_string()));
    }
}
