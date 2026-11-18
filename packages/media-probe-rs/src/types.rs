use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct HashReport {
    pub path: String,
    pub sha256: String,
    pub file_bytes: u64,
    pub elapsed_ms: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ContainerInfo {
    pub format_name: String,
    pub duration_s: f64,
    pub bit_rate: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct VideoInfo {
    pub present: bool,
    pub codec: Option<String>,
    pub width: u32,
    pub height: u32,
    pub fps: f64,
    pub is_cfr: bool,
    pub pixel_format: Option<String>,
    pub color_space: Option<String>,
    pub color_primaries: Option<String>,
    pub color_trc: Option<String>,
    pub frame_count_est: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct TimeInterval {
    pub start_s: f64,
    pub end_s: f64,
    pub duration_s: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct AudioInfo {
    pub present: bool,
    pub codec: Option<String>,
    pub sample_rate_hz: Option<u32>,
    pub channels: Option<u32>,
    pub integrated_lufs: Option<f64>,
    pub lra: Option<f64>,
    pub true_peak_dbtp: Option<f64>,
    pub silence_intervals: Vec<TimeInterval>,
    pub silence_ratio: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ShotSegment {
    pub shot_index: usize,
    pub start_s: f64,
    pub end_s: f64,
    pub duration_s: f64,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ShotStats {
    pub count: usize,
    pub asl_p25_s: f64,
    pub asl_p50_s: f64,
    pub asl_p75_s: f64,
    pub cuts_per_min: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct PaletteColor {
    pub hex: String,
    pub share: f64,
    pub lab_l: f64,
    pub lab_a: f64,
    pub lab_b: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct BandLuminance {
    pub upper: f64,
    pub center: f64,
    pub lower_third: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct KeyframeInfo {
    pub timestamp_s: f64,
    pub shot_index: usize,
    pub path: String,
    pub luma_lower_third: f64,
    pub sharpness: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct VisualInfo {
    pub sampled_frames: usize,
    pub palette: Vec<PaletteColor>,
    pub palette_entropy: f64,
    pub mean_luminance: f64,
    pub band_luminance: BandLuminance,
    pub mean_sharpness: f64,
    pub black_intervals: Vec<TimeInterval>,
    pub keyframes: Vec<KeyframeInfo>,
}

#[derive(Debug, Clone, Serialize)]
pub struct TimingBreakdown {
    pub hash_ms: u64,
    pub ffprobe_ms: u64,
    pub stream_analyze_ms: u64,
    pub total_ms: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct MediaProbeReport {
    pub schema_version: &'static str,
    pub path: String,
    pub sha256: String,
    pub file_bytes: u64,
    pub container: ContainerInfo,
    pub video: VideoInfo,
    pub audio: AudioInfo,
    pub shots: Vec<ShotSegment>,
    pub shot_stats: ShotStats,
    pub visual: VisualInfo,
    pub timing_ms: TimingBreakdown,
}
