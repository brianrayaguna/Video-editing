//! End-to-end cut detection on synthetic ffmpeg-generated clips.
//! Skipped when `ffmpeg` is not on PATH.

use std::path::{Path, PathBuf};
use std::process::Command;

use vedit_probe::pipeline::{AnalyzeOptions, analyze_media};

fn ffmpeg_available() -> bool {
    Command::new("ffmpeg")
        .arg("-version")
        .output()
        .is_ok_and(|o| o.status.success())
}

fn scratch_dir(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("vedit_probe_cuts_{}_{name}", std::process::id()));
    std::fs::create_dir_all(&dir).expect("create scratch dir");
    dir
}

fn render(out: &Path, filter_complex: &str) {
    let status = Command::new("ffmpeg")
        .args([
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-filter_complex",
            filter_complex,
        ])
        .args([
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        ])
        .arg(out)
        .status()
        .expect("spawn ffmpeg");
    assert!(
        status.success(),
        "ffmpeg failed to render {}",
        out.display()
    );
}

fn shot_starts(path: &Path) -> Vec<f64> {
    let report = analyze_media(path, &AnalyzeOptions::default()).expect("analyze");
    report.shots.iter().map(|s| s.start_s).collect()
}

#[test]
fn low_score_textured_cut_is_one_cut() {
    if !ffmpeg_available() {
        return;
    }
    let dir = scratch_dir("textured");
    let clip = dir.join("textured_cut.mp4");
    render(
        &clip,
        // Neighbouring crops of one pattern with a hue shift: scdet scores this cut ~6.7 (below the
        // unconditional threshold), the frame colour statistics change confirms it.
        "testsrc2=s=1280x568:r=30:d=2,crop=320:568:0:0[a];\
         testsrc2=s=1280x568:r=30:d=2,crop=320:568:80:0,hue=h=90[b];[a][b]concat=n=2:v=1[v]",
    );
    let starts = shot_starts(&clip);
    std::fs::remove_dir_all(&dir).ok();
    assert_eq!(starts.len(), 2, "shot starts: {starts:?}");
    assert!((starts[1] - 2.0).abs() < 0.04, "shot starts: {starts:?}");
}

#[test]
fn abrupt_pan_onset_is_not_a_cut() {
    if !ffmpeg_available() {
        return;
    }
    let dir = scratch_dir("pan");
    let clip = dir.join("pan_onset.mp4");
    render(
        &clip,
        "testsrc2=s=1280x568:r=30:d=4,crop=w=320:h=568:x='if(lt(t,2),0,(t-2)*240)':y=0[v]",
    );
    let starts = shot_starts(&clip);
    std::fs::remove_dir_all(&dir).ok();
    assert_eq!(starts, vec![0.0], "shot starts: {starts:?}");
}

#[test]
fn single_colour_clip_is_one_shot() {
    if !ffmpeg_available() {
        return;
    }
    let dir = scratch_dir("flat");
    let clip = dir.join("flat.mp4");
    render(&clip, "color=c=0x406080:s=320x568:r=30:d=3[v]");
    let starts = shot_starts(&clip);
    std::fs::remove_dir_all(&dir).ok();
    assert_eq!(starts, vec![0.0], "shot starts: {starts:?}");
}

#[test]
fn rotated_portrait_clip_reports_display_dimensions() {
    if !ffmpeg_available() {
        return;
    }
    let dir = scratch_dir("rotated");
    let raw = dir.join("raw.mp4");
    let clip = dir.join("rotated.mp4");
    render(&raw, "color=c=0x406080:s=320x180:r=30:d=1[v]");
    let status = Command::new("ffmpeg")
        .args(["-hide_banner", "-loglevel", "error", "-y", "-display_rotation", "90", "-i"])
        .arg(&raw)
        .args(["-c", "copy"])
        .arg(&clip)
        .status()
        .expect("spawn ffmpeg");
    assert!(status.success());
    let report = analyze_media(&clip, &AnalyzeOptions::default()).expect("analyze");
    std::fs::remove_dir_all(&dir).ok();
    assert_eq!(report.video.width, 180);
    assert_eq!(report.video.height, 320);
}

#[test]
fn ten_bit_modest_exposure_shift_matches_eight_bit_gate() {
    if !ffmpeg_available() {
        return;
    }
    let dir = scratch_dir("tenbit_gate");
    let clip8 = dir.join("shift8.mp4");
    let clip10 = dir.join("shift10.mp4");
    // A modest 8-bit brightness/crop step (~8 units in 8-bit < 15.0, but ~32 units in 10-bit >= 15.0)
    // paired with a textured crop jump scoring between cut_candidate_floor (5) and scene_threshold (12).
    let filter = "testsrc2=s=1280x568:r=30:d=2,crop=320:568:0:0[a];\
                  testsrc2=s=1280x568:r=30:d=2,crop=320:568:80:0,eq=brightness=0.03[b];\
                  [a][b]concat=n=2:v=1[v]";
    render(&clip8, filter);
    let status = Command::new("ffmpeg")
        .args(["-hide_banner", "-loglevel", "error", "-y", "-filter_complex", filter])
        .args(["-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p10le", "-r", "30"])
        .arg(&clip10)
        .status()
        .expect("spawn ffmpeg");
    if !status.success() {
        std::fs::remove_dir_all(&dir).ok();
        return;
    }
    let starts8 = shot_starts(&clip8);
    let starts10 = shot_starts(&clip10);
    std::fs::remove_dir_all(&dir).ok();
    assert_eq!(starts10, starts8, "10-bit ({starts10:?}) diverged from 8-bit ({starts8:?})");
}
