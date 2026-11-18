use std::path::Path;
use std::process::Command;

use anyhow::{Context, Result, bail};
use serde::Deserialize;

use crate::types::{AudioInfo, ContainerInfo, VideoInfo};

#[derive(Debug, Deserialize)]
struct FfprobeRaw {
    format: Option<FfprobeFormat>,
    streams: Option<Vec<FfprobeStream>>,
}

#[derive(Debug, Deserialize)]
struct FfprobeFormat {
    format_name: Option<String>,
    duration: Option<String>,
    bit_rate: Option<String>,
}

#[derive(Debug, Deserialize)]
struct FfprobeStream {
    codec_type: Option<String>,
    codec_name: Option<String>,
    width: Option<u32>,
    height: Option<u32>,
    r_frame_rate: Option<String>,
    avg_frame_rate: Option<String>,
    pix_fmt: Option<String>,
    color_space: Option<String>,
    color_primaries: Option<String>,
    color_transfer: Option<String>,
    nb_frames: Option<String>,
    sample_rate: Option<String>,
    channels: Option<u32>,
    duration: Option<String>,
}

pub struct ProbeMetadata {
    pub container: ContainerInfo,
    pub video: VideoInfo,
    pub audio_base: AudioInfo,
}

pub fn parse_rational(raw: Option<&str>) -> f64 {
    let Some(s) = raw else { return 0.0 };
    if let Some((num_s, den_s)) = s.split_once('/') {
        let num = num_s.trim().parse::<f64>().unwrap_or(0.0);
        let den = den_s.trim().parse::<f64>().unwrap_or(1.0);
        if den > 0.0 { num / den } else { 0.0 }
    } else {
        s.trim().parse::<f64>().unwrap_or(0.0)
    }
}

pub fn run_ffprobe(path: &Path) -> Result<ProbeMetadata> {
    let out = Command::new("ffprobe")
        .args([
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
        ])
        .arg(path)
        .output()
        .context("Failed to execute ffprobe")?;

    if !out.status.success() {
        bail!("ffprobe exited with status {}", out.status);
    }

    let raw: FfprobeRaw =
        serde_json::from_slice(&out.stdout).context("Invalid JSON emitted by ffprobe")?;
    let streams = raw.streams.unwrap_or_default();
    let fmt = raw.format.as_ref();

    let vstream = streams
        .iter()
        .find(|s| s.codec_type.as_deref() == Some("video"));
    let astream = streams
        .iter()
        .find(|s| s.codec_type.as_deref() == Some("audio"));

    let duration_s = fmt
        .and_then(|f| f.duration.as_deref())
        .and_then(|d| d.parse::<f64>().ok())
        .or_else(|| {
            vstream
                .and_then(|s| s.duration.as_deref())
                .and_then(|d| d.parse::<f64>().ok())
        })
        .or_else(|| {
            astream
                .and_then(|s| s.duration.as_deref())
                .and_then(|d| d.parse::<f64>().ok())
        })
        .unwrap_or(0.0)
        .max(0.0);

    let container = ContainerInfo {
        format_name: fmt
            .and_then(|f| f.format_name.clone())
            .unwrap_or_else(|| "unknown".to_string()),
        duration_s,
        bit_rate: fmt
            .and_then(|f| f.bit_rate.as_deref())
            .and_then(|b| b.parse::<u64>().ok()),
    };

    let video = if let Some(vs) = vstream {
        let r_fps = parse_rational(vs.r_frame_rate.as_deref());
        let avg_fps = parse_rational(vs.avg_frame_rate.as_deref());
        let fps = if avg_fps > 0.0 { avg_fps } else { r_fps };
        let is_cfr = if r_fps > 0.0 && avg_fps > 0.0 {
            ((r_fps - avg_fps).abs() / r_fps) <= 0.02
        } else {
            true
        };
        let frame_count_est = vs
            .nb_frames
            .as_deref()
            .and_then(|n| n.parse::<u64>().ok())
            .unwrap_or_else(|| (duration_s * fps).round().max(0.0) as u64);

        VideoInfo {
            present: true,
            codec: vs.codec_name.clone(),
            width: vs.width.unwrap_or(0),
            height: vs.height.unwrap_or(0),
            fps: (fps * 1000.0).round() / 1000.0,
            is_cfr,
            pixel_format: vs.pix_fmt.clone(),
            color_space: vs.color_space.clone(),
            color_primaries: vs.color_primaries.clone(),
            color_trc: vs.color_transfer.clone(),
            frame_count_est,
        }
    } else {
        VideoInfo {
            present: false,
            codec: None,
            width: 0,
            height: 0,
            fps: 0.0,
            is_cfr: true,
            pixel_format: None,
            color_space: None,
            color_primaries: None,
            color_trc: None,
            frame_count_est: 0,
        }
    };

    let audio_base = if let Some(aud) = astream {
        AudioInfo {
            present: true,
            codec: aud.codec_name.clone(),
            sample_rate_hz: aud
                .sample_rate
                .as_deref()
                .and_then(|r| r.parse::<u32>().ok()),
            channels: aud.channels,
            integrated_lufs: None,
            lra: None,
            true_peak_dbtp: None,
            silence_intervals: Vec::new(),
            silence_ratio: 0.0,
        }
    } else {
        AudioInfo {
            present: false,
            codec: None,
            sample_rate_hz: None,
            channels: None,
            integrated_lufs: None,
            lra: None,
            true_peak_dbtp: None,
            silence_intervals: Vec::new(),
            silence_ratio: 0.0,
        }
    };

    Ok(ProbeMetadata {
        container,
        video,
        audio_base,
    })
}
