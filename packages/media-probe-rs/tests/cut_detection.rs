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
