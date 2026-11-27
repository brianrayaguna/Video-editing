use std::collections::BTreeMap;
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
    tags: Option<BTreeMap<String, String>>,
}

#[derive(Debug, Deserialize)]
struct FfprobeDisposition {
    attached_pic: Option<u8>,
}

#[derive(Debug, Deserialize)]
struct FfprobeSideData {
    rotation: Option<i32>,
}

#[derive(Debug, Deserialize)]
struct FfprobeStream {
    index: Option<usize>,
    codec_type: Option<String>,
    codec_name: Option<String>,
    disposition: Option<FfprobeDisposition>,
    side_data_list: Option<Vec<FfprobeSideData>>,
    tags: Option<BTreeMap<String, String>>,
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
    pub video_stream_index: Option<usize>,
    pub audio_stream_index: Option<usize>,
}

fn parse_hms_duration(raw: &str) -> Option<f64> {
    let mut parts = raw.trim().split(':');
    let h = parts.next()?.parse::<f64>().ok()?;
    let m = parts.next()?.parse::<f64>().ok()?;
    let s = parts.next()?.parse::<f64>().ok()?;
    if parts.next().is_some() || !h.is_finite() || !m.is_finite() || !s.is_finite() {
        return None;
    }
    let total = h * 3600.0 + m * 60.0 + s;
    (total.is_finite() && total >= 0.0).then_some(total)
}

fn tag_duration_s(tags: Option<&BTreeMap<String, String>>) -> Option<f64> {
    let tags = tags?;
    tags.iter()
        .find(|(k, _)| k.eq_ignore_ascii_case("DURATION"))
        .and_then(|(_, v)| parse_hms_duration(v))
}

fn stream_rotation_deg(vs: &FfprobeStream) -> i32 {
    if let Some(rot) = vs
        .side_data_list
        .as_ref()
        .and_then(|list| list.iter().find_map(|sd| sd.rotation))
    {
        return rot;
    }
    vs.tags
        .as_ref()
        .and_then(|t| {
            t.iter()
                .find(|(k, _)| k.eq_ignore_ascii_case("rotate"))
                .and_then(|(_, v)| v.trim().parse::<i32>().ok())
        })
        .unwrap_or(0)
}

pub fn parse_rational(raw: Option<&str>) -> f64 {
    let Some(s) = raw else { return 0.0 };
    if let Some((num_s, den_s)) = s.split_once('/') {
        let Ok(num) = num_s.trim().parse::<f64>() else {
            return 0.0;
        };
        let Ok(den) = den_s.trim().parse::<f64>() else {
            return 0.0;
        };
        if num.is_finite() && den.is_finite() && num >= 0.0 && den > 0.0 {
            let q = num / den;
            if q.is_finite() { q } else { 0.0 }
        } else {
            0.0
        }
    } else {
        s.trim()
            .parse::<f64>()
            .ok()
            .filter(|v| v.is_finite() && *v >= 0.0)
            .unwrap_or(0.0)
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

    let vstream = streams.iter().find(|s| {
        s.codec_type.as_deref() == Some("video")
            && s.disposition.as_ref().and_then(|d| d.attached_pic).unwrap_or(0) == 0
    });
    let astream = streams
        .iter()
        .find(|s| s.codec_type.as_deref() == Some("audio"));

    let duration_s = fmt
        .and_then(|f| f.duration.as_deref())
        .and_then(|d| d.parse::<f64>().ok())
        .filter(|d| d.is_finite() && *d >= 0.0)
        .or_else(|| {
            vstream
                .and_then(|s| s.duration.as_deref())
                .and_then(|d| d.parse::<f64>().ok())
                .filter(|d| d.is_finite() && *d >= 0.0)
        })
        .or_else(|| {
            astream
                .and_then(|s| s.duration.as_deref())
                .and_then(|d| d.parse::<f64>().ok())
                .filter(|d| d.is_finite() && *d >= 0.0)
        })
        .or_else(|| tag_duration_s(fmt.and_then(|f| f.tags.as_ref())))
        .or_else(|| tag_duration_s(vstream.and_then(|s| s.tags.as_ref())))
        .or_else(|| tag_duration_s(astream.and_then(|s| s.tags.as_ref())))
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
        let raw_w = vs.width.unwrap_or(0);
        let raw_h = vs.height.unwrap_or(0);
        let (disp_w, disp_h) = if stream_rotation_deg(vs).abs() % 180 == 90 {
            (raw_h, raw_w)
        } else {
            (raw_w, raw_h)
        };

        VideoInfo {
            present: true,
            codec: vs.codec_name.clone(),
            width: disp_w,
            height: disp_h,
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
        video_stream_index: vstream.and_then(|s| s.index),
        audio_stream_index: astream.and_then(|s| s.index),
    })
}

#[cfg(test)]
mod tests {
    use super::parse_rational;

    #[test]
    fn parses_valid_rationals_and_rejects_invalid_or_negative() {
        assert!((parse_rational(Some("30000/1001")) - 29.97002997).abs() < 1e-4);
        assert_eq!(parse_rational(Some("0/0")), 0.0);
        assert_eq!(parse_rational(Some("-30/1")), 0.0);
        assert_eq!(parse_rational(Some("30/abc")), 0.0);
        assert_eq!(parse_rational(Some("NaN")), 0.0);
        assert_eq!(parse_rational(Some("inf")), 0.0);
        assert_eq!(parse_rational(Some("1e308/1e-308")), 0.0);
        assert_eq!(parse_rational(None), 0.0);
    }
}
