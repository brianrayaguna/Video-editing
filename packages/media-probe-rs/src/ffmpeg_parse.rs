use crate::types::{ShotSegment, ShotStats, TimeInterval};

#[derive(Debug, Default)]
pub struct ParsedFfmpegStderr {
    pub cut_times_s: Vec<(f64, f64)>, // (timestamp_s, normalized_confidence)
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
    token.parse::<f64>().ok()
}

/// Parse single-pass FFmpeg stderr output for `scdet`, `blackdetect`, `silencedetect`, and `ebur128`.
pub fn parse_ffmpeg_stderr(stderr: &str, duration_s: f64) -> ParsedFfmpegStderr {
    let mut parsed = ParsedFfmpegStderr::default();
    let mut pending_silence_start: Option<f64> = None;
    let mut in_ebur_summary = false;
    let mut ebur_section = "";

    for line in stderr.lines() {
        let trimmed = line.trim();

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
                let dur = parse_key_value_f64(trimmed, "black_duration:")
                    .unwrap_or_else(|| (end - start).max(0.0));
                parsed.black_intervals.push(TimeInterval {
                    start_s: start.max(0.0),
                    end_s: end.max(start),
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

    parsed
}

pub fn build_shots_and_stats(
    cuts: &[(f64, f64)],
    duration_s: f64,
    min_scene_s: f64,
) -> (Vec<ShotSegment>, ShotStats) {
    if duration_s <= 0.0 {
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
}
