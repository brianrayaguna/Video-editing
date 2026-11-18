use std::fs::File;
use std::io::{BufReader, Read};
use std::path::Path;
use std::time::Instant;

use anyhow::{Context, Result};
use sha2::{Digest, Sha256};

use crate::types::HashReport;

const BUFFER_SIZE: usize = 64 * 1024;

pub fn hash_file(path: &Path) -> Result<HashReport> {
    let start = Instant::now();
    let file = File::open(path).with_context(|| format!("Failed to open {}", path.display()))?;
    let file_bytes = file.metadata()?.len();
    let mut reader = BufReader::with_capacity(BUFFER_SIZE, file);
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; BUFFER_SIZE];

    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }

    let digest = hasher.finalize();
    let sha256 = digest.iter().map(|b| format!("{b:02x}")).collect::<String>();
    Ok(HashReport {
        path: path.to_string_lossy().into_owned(),
        sha256,
        file_bytes,
        elapsed_ms: start.elapsed().as_millis() as u64,
    })
}
