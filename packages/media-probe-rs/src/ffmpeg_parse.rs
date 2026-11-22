use std::collections::BTreeMap;

use crate::types::{ShotSegment, ShotStats, TimeInterval};

/// Per-frame colour statistics keys printed by `signalstats` + `metadata=print`, in storage order.
pub const FRAME_STAT_KEYS: [&str; 4] = ["YAVG", "UAVG", "VAVG", "SATAVG"];

#[derive(Debug, Default)]
pub struct ParsedFfmpegStderr {
    /// `scdet` candidates above the candidate floor: (timestamp_s, normalized_confidence = score / 100).
    pub cut_times_s: Vec<(f64, f64)>,
    /// Per-frame (pts_time_s, [YAVG, UAVG, VAVG, SATAVG]) sorted by time.
    pub frame_stats: Vec<(f64, [f64; 4])>,
    pub black_intervals: Vec<TimeInterval>,
    pub silence_intervals: Vec<TimeInterval>,
    pub integrated_lufs: Option<f64>,
    pub lra: Option<f64>,
    pub true_peak_dbtp: Option<f64>,
}

fn parse_key_value_f64(line: &str, key: &str) -> Option<f64> {
    let idx = line.find(key)?;
    let rest = line[idx + key.len()..].trim_start();
    let token = rest
        .split(|c: char| c.is_whitespace() || c == ',' || c == '|')
        .next()?;
    token.parse::<f64>().ok().filter(|v| v.is_finite())
}

/// Parse single-pass FFmpeg stderr output for `scdet`, `blackdetect`, `silencedetect`, and `ebur128`.
pub fn parse_ffmpeg_stderr(stderr: &str, duration_s: f64) -> ParsedFfmpegStderr {
    let mut parsed = ParsedFfmpegStderr::default();
    let mut pending_silence_start: Option<f64> = None;
    let mut in_ebur_summary = false;
    let mut ebur_section = "";
    let mut current_pts_us: Option<i64> = None;
    let mut stats_by_pts: BTreeMap<i64, [f64; 4]> = BTreeMap::new();

    for line in stderr.lines() {
        let trimmed = line.trim();

        if trimmed.contains("pts_time:") {
            current_pts_us =
                parse_key_value_f64(trimmed, "pts_time:").map(|t| (t * 1e6).round() as i64);
            continue;
        }

        if let Some(idx) = trimmed.find("lavfi.signalstats.") {
            let rest = &trimmed[idx + "lavfi.signalstats.".len()..];
            if let (Some(pts_us), Some((key, value))) = (current_pts_us, rest.split_once('='))
                && let (Some(slot), Ok(v)) = (
                    FRAME_STAT_KEYS.iter().position(|k| *k == key),
                    value.trim().parse::<f64>(),
                )
            {
                stats_by_pts.entry(pts_us).or_insert([f64::NAN; 4])[slot] = v;
            }
            continue;
        }

        if trimmed.contains("lavfi.scd.score:") && trimmed.contains("lavfi.scd.time:") {
            if let (Some(score), Some(t)) = (
                parse_key_value_f64(trimmed, "lavfi.scd.score:"),
                parse_key_value_f64(trimmed, "lavfi.scd.time:"),
            ) {
                let conf = (score / 100.0).clamp(0.0, 1.0);
                parsed.cut_times_s.push((t.max(0.0), conf));
            }
            continue;
        }

        if trimmed.contains("black_start:") && trimmed.contains("black_end:") {
            if let (Some(start), Some(end)) = (
                parse_key_value_f64(trimmed, "black_start:"),
                parse_key_value_f64(trimmed, "black_end:"),
            ) {
                let start_clamped = start.max(0.0);
                let end_clamped = end.max(start_clamped);
                let dur = parse_key_value_f64(trimmed, "black_duration:")
                    .unwrap_or_else(|| (end_clamped - start_clamped).max(0.0));
                parsed.black_intervals.push(TimeInterval {
                    start_s: start_clamped,
                    end_s: end_clamped,
                    duration_s: dur.max(0.0),
                });
            }
            continue;
        }

        if trimmed.contains("silence_start:") {
            if let Some(s) = parse_key_value_f64(trimmed, "silence_start:") {
                pending_silence_start = Some(s.max(0.0));
            }
            continue;
        }

        if trimmed.contains("silence_end:") {
            if let Some(end) = parse_key_value_f64(trimmed, "silence_end:") {
                let start = pending_silence_start.take().unwrap_or(0.0);
                let dur = parse_key_value_f64(trimmed, "silence_duration:")
                    .unwrap_or_else(|| (end - start).max(0.0));
                parsed.silence_intervals.push(TimeInterval {
                    start_s: start,
                    end_s: end.max(start),
                    duration_s: dur.max(0.0),
                });
            }
            continue;
        }

        if trimmed.ends_with("Summary:") && trimmed.contains("ebur128") {
            in_ebur_summary = true;
            ebur_section = "";
            continue;
        }

        if in_ebur_summary {
            if trimmed.starts_with("Integrated loudness:") {
                ebur_section = "integrated";
            } else if trimmed.starts_with("Loudness range:") {
                ebur_section = "lra";
            } else if trimmed.starts_with("True peak:") {
                ebur_section = "peak";
            } else if ebur_section == "integrated" && trimmed.starts_with("I:") {
                parsed.integrated_lufs = parse_key_value_f64(trimmed, "I:");
            } else if ebur_section == "lra" && trimmed.starts_with("LRA:") {
                parsed.lra = parse_key_value_f64(trimmed, "LRA:");
            } else if ebur_section == "peak" && trimmed.starts_with("Peak:") {
                parsed.true_peak_dbtp = parse_key_value_f64(trimmed, "Peak:");
                in_ebur_summary = false;
            }
        }
    }

    if let Some(open_start) = pending_silence_start {
        let end = duration_s.max(open_start);
        parsed.silence_intervals.push(TimeInterval {
            start_s: open_start,
            end_s: end,
            duration_s: (end - open_start).max(0.0),
        });
    }

    parsed.frame_stats = stats_by_pts
        .into_iter()
        .map(|(pts_us, vals)| (pts_us as f64 / 1e6, vals))
        .collect();
    parsed
}

/// Sum of absolute per-key changes between the frame at `t` and the frame before it.
/// `None` when either frame is missing or incomplete.
fn stats_change_at(frame_stats: &[(f64, [f64; 4])], t: f64) -> Option<f64> {
    let idx = frame_stats
        .iter()
        .position(|(ft, _)| (ft - t).abs() < 2e-3)?;
    if idx == 0 {
        return None;
    }
    let (cur, prev) = (frame_stats[idx].1, frame_stats[idx - 1].1);
    let delta: f64 = cur
        .iter()
        .zip(prev.iter())
        .map(|(a, b)| (a - b).abs())
        .sum();
    delta.is_finite().then_some(delta)
}

/// Keep `scdet` candidates that are hard cuts.
///
/// `scdet` also spikes on the first frame of an abrupt camera move, and same-palette cuts can score
/// low, so the score alone cannot separate them. A candidate is a cut when its score reaches
/// `scene_threshold`, or when the frame's mean colour statistics change by at least
/// `stats_change_min` (sum of |dYAVG| + |dUAVG| + |dVAVG| + |dSATAVG|, 8-bit units).
pub fn gate_cut_candidates(
    candidates: &[(f64, f64)],
    frame_stats: &[(f64, [f64; 4])],
    scene_threshold: f64,
    stats_change_min: f64,
) -> Vec<(f64, f64)> {
    candidates
        .iter()
        .copied()
        .filter(|(t, conf)| {
            conf * 100.0 >= scene_threshold
                || stats_change_at(frame_stats, *t).is_some_and(|d| d >= stats_change_min)
        })
        .collect()
}

pub fn build_shots_and_stats(
    cuts: &[(f64, f64)],
    duration_s: f64,
    min_scene_s: f64,
) -> (Vec<ShotSegment>, ShotStats) {
    if !duration_s.is_finite() || duration_s <= 0.0 {
        return (
            Vec::new(),
            ShotStats {
                count: 0,
                asl_p25_s: 0.0,
                asl_p50_s: 0.0,
                asl_p75_s: 0.0,
                cuts_per_min: 0.0,
            },
        );
    }

    let mut sorted_cuts = cuts.to_vec();
    sorted_cuts.sort_by(|a, b| a.0.total_cmp(&b.0));

    let mut boundaries: Vec<(f64, f64)> = Vec::new();
    let mut prev_t = 0.0;
    for (t, conf) in sorted_cuts {
        if t <= 0.0 || t >= duration_s - 0.05 {
            continue;
        }
        if t - prev_t >= min_scene_s {
            boundaries.push((t, conf));
            prev_t = t;
        }
    }

    let mut shots = Vec::with_capacity(boundaries.len() + 1);
    let mut cursor = 0.0;
    let mut cursor_conf = 1.0;

    for (idx, (cut_t, cut_conf)) in boundaries.iter().enumerate() {
        let dur = (*cut_t - cursor).max(0.0);
        shots.push(ShotSegment {
            shot_index: idx,
            start_s: round3(cursor),
            end_s: round3(*cut_t),
            duration_s: round3(dur),
            confidence: round3(cursor_conf),
        });
        cursor = *cut_t;
        cursor_conf = *cut_conf;
    }

    shots.push(ShotSegment {
        shot_index: shots.len(),
        start_s: round3(cursor),
        end_s: round3(duration_s),
        duration_s: round3((duration_s - cursor).max(0.0)),
        confidence: round3(cursor_conf),
    });

    let mut durations: Vec<f64> = shots.iter().map(|s| s.duration_s).collect();
    durations.sort_by(|a, b| a.total_cmp(b));

    let cuts_per_min = if duration_s > 0.0 {
        (boundaries.len() as f64) * 60.0 / duration_s
    } else {
        0.0
    };

    let stats = ShotStats {
        count: shots.len(),
        asl_p25_s: round3(percentile_sorted(&durations, 0.25)),
        asl_p50_s: round3(percentile_sorted(&durations, 0.50)),
        asl_p75_s: round3(percentile_sorted(&durations, 0.75)),
        cuts_per_min: round3(cuts_per_min),
    };

    (shots, stats)
}

pub fn percentile_sorted(sorted: &[f64], p: f64) -> f64 {
    if sorted.is_empty() {
        return 0.0;
    }
    if sorted.len() == 1 {
        return sorted[0];
    }
    let pos = p.clamp(0.0, 1.0) * (sorted.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = pos.ceil() as usize;
    let frac = pos - lo as f64;
    sorted[lo] * (1.0 - frac) + sorted[hi] * frac
}

pub fn round3(v: f64) -> f64 {
    let r = (v * 1000.0).round() / 1000.0;
    if r == 0.0 { 0.0 } else { r }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_scdet_silence_black_and_ebur128() {
        let sample = "\
[Parsed_scdet_1 @ 0x1] lavfi.scd.score: 24.5, lavfi.scd.time: 1.5
[Parsed_silencedetect_5 @ 0x2] silence_start: 1.45
[Parsed_silencedetect_5 @ 0x2] silence_end: 2.8 | silence_duration: 1.35
[Parsed_blackdetect_2 @ 0x3] black_start:2.0 black_end:2.95 black_duration:0.95
[Parsed_ebur128_6 @ 0x4] Summary:
  Integrated loudness:
    I:         -14.2 LUFS
    Threshold: -24.5 LUFS
  Loudness range:
    LRA:         6.4 LU
  True peak:
    Peak:       -1.3 dBFS
";
        let parsed = parse_ffmpeg_stderr(sample, 3.0);
        assert_eq!(parsed.cut_times_s.len(), 1);
        assert!((parsed.cut_times_s[0].0 - 1.5).abs() < 1e-6);
        assert!((parsed.cut_times_s[0].1 - 0.245).abs() < 1e-6);
        assert_eq!(parsed.black_intervals.len(), 1);
        assert_eq!(parsed.silence_intervals.len(), 1);
        assert_eq!(parsed.integrated_lufs, Some(-14.2));
        assert_eq!(parsed.lra, Some(6.4));
        assert_eq!(parsed.true_peak_dbtp, Some(-1.3));
    }

    fn stats_stderr(frames: &[(f64, [f64; 4])], candidates: &[(f64, f64)]) -> String {
        let keys = ["YAVG", "UAVG", "VAVG", "SATAVG"];
        let mut out = String::new();
        for (idx, (t, vals)) in frames.iter().enumerate() {
            for (key, v) in keys.iter().zip(vals.iter()) {
                out.push_str(&format!(
                    "[Parsed_metadata_2 @ 0x1] frame:{idx}    pts:{idx}       pts_time:{t}\n"
                ));
                out.push_str(&format!(
                    "[Parsed_metadata_2 @ 0x1] lavfi.signalstats.{key}={v}\n"
                ));
            }
        }
        for (score, t) in candidates {
            out.push_str(&format!(
                "[Parsed_scdet_6 @ 0x2] lavfi.scd.score: {score}, lavfi.scd.time: {t}\n"
            ));
        }
        out
    }

    #[test]
    fn parses_signalstats_per_frame() {
        let stderr = stats_stderr(
            &[
                (0.0, [120.0, 101.5, 126.7, 30.0]),
                (0.033333, [121.0, 101.0, 127.0, 31.0]),
            ],
            &[],
        );
        let parsed = parse_ffmpeg_stderr(&stderr, 1.0);
        assert_eq!(parsed.frame_stats.len(), 2);
        assert!((parsed.frame_stats[1].0 - 0.033333).abs() < 1e-9);
        assert_eq!(parsed.frame_stats[0].1, [120.0, 101.5, 126.7, 30.0]);
    }

    #[test]
    fn rejects_scd_spike_without_stats_change() {
        // Camera-move onset: high-ish scdet score, colour statistics nearly unchanged (sum 7.5).
        let stderr = stats_stderr(
            &[
                (17.733333, [130.0, 110.0, 140.0, 40.0]),
                (17.766667, [132.0, 111.5, 138.0, 42.0]),
            ],
            &[(9.17, 17.766667)],
        );
        let parsed = parse_ffmpeg_stderr(&stderr, 24.0);
        let cuts = gate_cut_candidates(&parsed.cut_times_s, &parsed.frame_stats, 12.0, 15.0);
        assert!(cuts.is_empty());
    }

    #[test]
    fn accepts_low_score_cut_with_stats_change() {
        // Same-palette hard cut: modest scdet score, colour statistics shift by 24.5.
        let stderr = stats_stderr(
            &[
                (4.966667, [100.0, 120.0, 130.0, 50.0]),
                (5.0, [110.0, 114.0, 135.0, 46.5]),
            ],
            &[(7.67, 5.0)],
        );
        let parsed = parse_ffmpeg_stderr(&stderr, 24.0);
        let cuts = gate_cut_candidates(&parsed.cut_times_s, &parsed.frame_stats, 12.0, 15.0);
        assert_eq!(cuts.len(), 1);
        assert!((cuts[0].0 - 5.0).abs() < 1e-9);
    }

    #[test]
    fn accepts_high_score_cut_unconditionally() {
        let stderr = stats_stderr(
            &[
                (2.966667, [100.0, 120.0, 130.0, 50.0]),
                (3.0, [100.5, 120.5, 130.5, 50.5]),
            ],
            &[(14.2, 3.0)],
        );
        let parsed = parse_ffmpeg_stderr(&stderr, 24.0);
        let cuts = gate_cut_candidates(&parsed.cut_times_s, &parsed.frame_stats, 12.0, 15.0);
        assert_eq!(cuts.len(), 1);
    }

    #[test]
    fn builds_shots_with_min_scene_dedup() {
        let (shots, stats) = build_shots_and_stats(&[(1.5, 0.4), (1.6, 0.2), (4.0, 0.7)], 6.0, 0.4);
        assert_eq!(shots.len(), 3);
        assert_eq!(shots[0].start_s, 0.0);
        assert_eq!(shots[0].end_s, 1.5);
        assert_eq!(shots[1].start_s, 1.5);
        assert_eq!(shots[1].end_s, 4.0);
        assert_eq!(shots[2].start_s, 4.0);
        assert_eq!(shots[2].end_s, 6.0);
        assert_eq!(stats.count, 3);
        assert!((stats.asl_p50_s - 2.0).abs() < 1e-6);
    }

    #[test]
    fn rejects_non_finite_loudness_and_clamps_negative_black_intervals() {
        let sample = "\
[blackdetect @ 0x1] black_start:-0.5 black_end:-0.1 black_duration:0.4
[Parsed_ebur128_0 @ 0x2] Summary:
  Integrated loudness:
    I:         -inf LUFS
  True peak:
    Peak:      -inf dBFS
";
        let parsed = parse_ffmpeg_stderr(sample, 3.0);
        assert_eq!(parsed.integrated_lufs, None);
        assert_eq!(parsed.true_peak_dbtp, None);
        assert_eq!(parsed.black_intervals.len(), 1);
        assert_eq!(parsed.black_intervals[0].start_s, 0.0);
        assert_eq!(parsed.black_intervals[0].end_s, 0.0);

        let (shots, stats) = build_shots_and_stats(&[(1.0, 0.5)], f64::NAN, 0.4);
        assert!(shots.is_empty());
        assert_eq!(stats.count, 0);
    }
}
