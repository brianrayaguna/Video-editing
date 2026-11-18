use std::fs;
use std::io::Read;
use std::path::Path;
use std::process::{Command, Stdio};
use std::thread;
use std::time::Instant;

use anyhow::{Context, Result, bail};
use image::{RgbImage, codecs::jpeg::JpegEncoder};

use crate::ffmpeg_parse::{build_shots_and_stats, parse_ffmpeg_stderr, round3};
use crate::ffprobe::run_ffprobe;
use crate::hash::hash_file;
use crate::types::{
    KeyframeInfo, MediaProbeReport, ShotStats, TimingBreakdown, VisualInfo,
};
use crate::vision::{
    FrameVisionMetrics, aggregate_palette_and_visual, analyze_rgb24_frame,
};

pub struct AnalyzeOptions {
    pub scene_threshold: f64,
    pub min_scene_s: f64,
    pub silence_db: f64,
    pub silence_min_s: f64,
    pub analysis_fps: f64,
    pub analysis_width: u32,
    pub true_peak: bool,
    pub extract_keyframes_dir: Option<std::path::PathBuf>,
}

impl Default for AnalyzeOptions {
    fn default() -> Self {
        Self {
            scene_threshold: 12.0,
            min_scene_s: 0.4,
            silence_db: -35.0,
            silence_min_s: 0.30,
            analysis_fps: 1.0,
            analysis_width: 320,
            true_peak: false,
            extract_keyframes_dir: None,
        }
    }
}

fn even_scaled_height(src_w: u32, src_h: u32, target_w: u32) -> u32 {
    if src_w == 0 || src_h == 0 {
        return 180;
    }
    let raw = ((src_h as f64) * (target_w as f64) / (src_w as f64)).round() as u32;
    let even = (raw / 2) * 2;
    even.max(16)
}

fn encode_jpeg_bytes(rgb: &[u8], w: u32, h: u32) -> Result<Vec<u8>> {
    let mut out = Vec::new();
    let img = RgbImage::from_raw(w, h, rgb.to_vec())
        .context("Frame byte count did not match target RGB24 dimensions")?;
    let mut encoder = JpegEncoder::new_with_quality(&mut out, 85);
    encoder.encode_image(&img)?;
    Ok(out)
}

pub fn analyze_media(path: &Path, opts: &AnalyzeOptions) -> Result<MediaProbeReport> {
    if !path.is_file() {
        bail!("Media file does not exist: {}", path.display());
    }

    let total_t0 = Instant::now();

    // Run file SHA-256 hashing and ffprobe metadata extraction concurrently.
    let (hash_res, probe_res, hash_ms, ffprobe_ms) = thread::scope(|s| {
        let h_handle = s.spawn(|| {
            let t = Instant::now();
            let res = hash_file(path);
            (res, t.elapsed().as_millis() as u64)
        });
        let p_handle = s.spawn(|| {
            let t = Instant::now();
            let res = run_ffprobe(path);
            (res, t.elapsed().as_millis() as u64)
        });
        let (h_res, h_ms) = h_handle.join().expect("hash thread panicked");
        let (p_res, p_ms) = p_handle.join().expect("ffprobe thread panicked");
        (h_res, p_res, h_ms, p_ms)
    });

    let hash_report = hash_res?;
    let meta = probe_res?;
    let duration_s = meta.container.duration_s;

    let stream_t0 = Instant::now();
    let mut audio = meta.audio_base;
    let video = meta.video;

    let mut frame_metrics: Vec<FrameVisionMetrics> = Vec::new();
    let mut compressed_frames: Vec<(f64, Vec<u8>, f64, f64)> = Vec::new();
    let stderr_text: String;

    if video.present {
        let target_w = if opts.extract_keyframes_dir.is_some() && opts.analysis_width < 480 {
            480
        } else {
            opts.analysis_width.max(64)
        };
        let target_h = even_scaled_height(video.width, video.height, target_w);
        let frame_bytes = (target_w as usize) * (target_h as usize) * 3;
        let effective_fps = if opts.extract_keyframes_dir.is_some() && opts.analysis_fps < 2.0 {
            2.0
        } else {
            opts.analysis_fps.max(0.2)
        };

        let ebur_filter = if opts.true_peak {
            "ebur128=peak=true"
        } else {
            "ebur128"
        };

        let filter_complex = if audio.present {
            format!(
                "[0:v]scale={target_w}:{target_h}:flags=fast_bilinear,\
                 scdet=threshold={thr}:sc_pass=0,\
                 blackdetect=d=0.2:pix_th=0.10,\
                 fps={effective_fps},format=rgb24[vout];\
                 [0:a]silencedetect=n={sil_db}dB:d={sil_d},{ebur_filter}[aout]",
                thr = opts.scene_threshold,
                sil_db = opts.silence_db,
                sil_d = opts.silence_min_s,
            )
        } else {
            format!(
                "[0:v]scale={target_w}:{target_h}:flags=fast_bilinear,\
                 scdet=threshold={thr}:sc_pass=0,\
                 blackdetect=d=0.2:pix_th=0.10,\
                 fps={effective_fps},format=rgb24[vout]",
                thr = opts.scene_threshold,
            )
        };

        let mut cmd = Command::new("ffmpeg");
        cmd.args(["-hide_banner", "-nostdin", "-i"])
            .arg(path)
            .args(["-filter_complex", &filter_complex, "-map", "[vout]", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]);
        if audio.present {
            cmd.args(["-map", "[aout]", "-f", "null", "-"]);
        }
        cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

        let mut child = cmd.spawn().context("Failed to spawn ffmpeg analysis process")?;
        let mut stdout = child.stdout.take().context("Missing ffmpeg stdout pipe")?;
        let mut stderr = child.stderr.take().context("Missing ffmpeg stderr pipe")?;

        // Drain stdout and stderr concurrently to guarantee zero pipe deadlock.
        let (stderr_out, read_res) = thread::scope(|s| {
            let err_handle = s.spawn(move || {
                let mut err_buf = String::new();
                let _ = stderr.read_to_string(&mut err_buf);
                err_buf
            });

            let mut buf = vec![0u8; frame_bytes];
            let mut idx = 0usize;
            let keep_jpegs = opts.extract_keyframes_dir.is_some();

            let res: Result<()> = loop {
                match stdout.read_exact(&mut buf) {
                    Ok(()) => {
                        let m = analyze_rgb24_frame(&buf, target_w as usize, target_h as usize);
                        if keep_jpegs {
                            let ts = (idx as f64) / effective_fps;
                            let jpg = match encode_jpeg_bytes(&buf, target_w, target_h) {
                                Ok(j) => j,
                                Err(e) => break Err(e),
                            };
                            compressed_frames.push((ts, jpg, m.lower_third_luma, m.sharpness));
                        }
                        frame_metrics.push(m);
                        idx += 1;
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::UnexpectedEof => break Ok(()),
                    Err(e) => break Err(e.into()),
                }
            };
            let err_str = err_handle.join().unwrap_or_default();
            (err_str, res)
        });

        read_res?;
        let status = child.wait()?;
        if !status.success() {
            bail!("ffmpeg exited with status {status}: {stderr_out}");
        }
        stderr_text = stderr_out;
    } else if audio.present {
        let ebur_filter = if opts.true_peak {
            "ebur128=peak=true"
        } else {
            "ebur128"
        };
        let af = format!(
            "silencedetect=n={}dB:d={},{}",
            opts.silence_db, opts.silence_min_s, ebur_filter
        );
        let out = Command::new("ffmpeg")
            .args(["-hide_banner", "-nostdin", "-i"])
            .arg(path)
            .args(["-af", &af, "-f", "null", "-"])
            .output()
            .context("Failed to execute ffmpeg audio probe")?;
        if !out.status.success() {
            bail!("ffmpeg audio probe failed: {}", String::from_utf8_lossy(&out.stderr));
        }
        stderr_text = String::from_utf8_lossy(&out.stderr).into_owned();
    } else {
        stderr_text = String::new();
    }

    let parsed = parse_ffmpeg_stderr(&stderr_text, duration_s);

    if audio.present {
        let silence_sum: f64 = parsed.silence_intervals.iter().map(|i| i.duration_s).sum();
        audio.integrated_lufs = parsed.integrated_lufs;
        audio.lra = parsed.lra;
        audio.true_peak_dbtp = parsed.true_peak_dbtp;
        audio.silence_intervals = parsed.silence_intervals;
        audio.silence_ratio = if duration_s > 0.0 {
            round3((silence_sum / duration_s).clamp(0.0, 1.0))
        } else {
            0.0
        };
    }

    let (shots, shot_stats) = if video.present {
        build_shots_and_stats(&parsed.cut_times_s, duration_s, opts.min_scene_s)
    } else {
        (
            Vec::new(),
            ShotStats {
                count: 0,
                asl_p25_s: 0.0,
                asl_p50_s: 0.0,
                asl_p75_s: 0.0,
                cuts_per_min: 0.0,
            },
        )
    };

    let (palette, palette_entropy, mean_luma, band_luma, mean_sharpness) =
        aggregate_palette_and_visual(&frame_metrics, 5);

    let mut keyframes = Vec::new();
    if let Some(ref kf_dir) = opts.extract_keyframes_dir
        && !compressed_frames.is_empty()
        && !shots.is_empty()
    {
        fs::create_dir_all(kf_dir)?;
        for shot in &shots {
            let midpoint = (shot.start_s + shot.end_s) / 2.0;
            if let Some((ts, jpg, luma_low, sharp)) = compressed_frames
                .iter()
                .min_by(|a, b| (a.0 - midpoint).abs().total_cmp(&(b.0 - midpoint).abs()))
            {
                let out_path = kf_dir.join(format!("shot_{:04}.jpg", shot.shot_index));
                fs::write(&out_path, jpg)?;
                keyframes.push(KeyframeInfo {
                    timestamp_s: round3(*ts),
                    shot_index: shot.shot_index,
                    path: out_path.to_string_lossy().into_owned(),
                    luma_lower_third: round3(*luma_low),
                    sharpness: round3(*sharp),
                });
            }
        }
    }

    let stream_analyze_ms = stream_t0.elapsed().as_millis() as u64;
    let total_ms = total_t0.elapsed().as_millis() as u64;

    Ok(MediaProbeReport {
        schema_version: "1.0",
        path: path.to_string_lossy().into_owned(),
        sha256: hash_report.sha256,
        file_bytes: hash_report.file_bytes,
        container: meta.container,
        video,
        audio,
        shots,
        shot_stats,
        visual: VisualInfo {
            sampled_frames: frame_metrics.len(),
            palette,
            palette_entropy,
            mean_luminance: mean_luma,
            band_luminance: band_luma,
            mean_sharpness,
            black_intervals: parsed.black_intervals,
            keyframes,
        },
        timing_ms: TimingBreakdown {
            hash_ms,
            ffprobe_ms,
            stream_analyze_ms,
            total_ms,
        },
    })
}
