use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, Subcommand};

use vedit_probe::hash::hash_file;
use vedit_probe::pipeline::{AnalyzeOptions, analyze_media};

#[derive(Parser)]
#[command(
    name = "vedit-probe",
    version,
    about = "Fast deterministic media probe, SHA-256 CAS hasher, and CIELAB visual analyzer."
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Compute SHA-256 content hash and byte size of a media asset.
    Hash {
        /// Path to the media file.
        file: PathBuf,
    },
    /// Run single-pass ffprobe + FFmpeg shot/audio probe + parallel CIELAB visual analysis.
    Analyze {
        /// Path to the media file.
        file: PathBuf,
        /// FFmpeg scdet threshold (0..100).
        #[arg(long, default_value_t = 12.0)]
        scene_threshold: f64,
        /// Minimum duration (seconds) between distinct cuts.
        #[arg(long, default_value_t = 0.4)]
        min_scene_s: f64,
        /// Silence detection threshold in dBFS.
        #[arg(long, default_value_t = -35.0, allow_hyphen_values = true)]
        silence_db: f64,
        /// Minimum silence duration in seconds.
        #[arg(long, default_value_t = 0.30)]
        silence_min_s: f64,
        /// Frame sampling rate for CIELAB palette, luma bands, and sharpness.
        #[arg(long, default_value_t = 1.0)]
        analysis_fps: f64,
        /// Downscaled analysis frame width in pixels.
        #[arg(long, default_value_t = 320)]
        analysis_width: u32,
        /// Enable oversampled true-peak measurement during ebur128 (slower; use for final QC).
        #[arg(long, default_value_t = false)]
        true_peak: bool,
        /// Optional directory to save JPEG keyframes at shot midpoints.
        #[arg(long)]
        extract_keyframes: Option<PathBuf>,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Hash { file } => {
            let report = hash_file(&file)?;
            println!("{}", serde_json::to_string_pretty(&report)?);
        }
        Commands::Analyze {
            file,
            scene_threshold,
            min_scene_s,
            silence_db,
            silence_min_s,
            analysis_fps,
            analysis_width,
            true_peak,
            extract_keyframes,
        } => {
            let opts = AnalyzeOptions {
                scene_threshold,
                min_scene_s,
                silence_db,
                silence_min_s,
                analysis_fps,
                analysis_width,
                true_peak,
                extract_keyframes_dir: extract_keyframes,
            };
            let report = analyze_media(&file, &opts)?;
            println!("{}", serde_json::to_string_pretty(&report)?);
        }
    }
    Ok(())
}
