use std::collections::HashMap;

use rayon::prelude::*;

use crate::ffmpeg_parse::round3;
use crate::types::{BandLuminance, PaletteColor};

#[derive(Debug, Clone)]
pub struct FrameVisionMetrics {
    pub mean_luma: f64,
    pub upper_luma: f64,
    pub center_luma: f64,
    pub lower_third_luma: f64,
    pub sharpness: f64,
    pub lab_bins: HashMap<(i32, i32, i32), LabBinAcc>,
}

#[derive(Debug, Clone, Default)]
pub struct LabBinAcc {
    pub count: u64,
    pub sum_l: f64,
    pub sum_a: f64,
    pub sum_b: f64,
}

#[inline]
fn srgb_channel_to_linear(c: u8) -> f64 {
    let v = c as f64 / 255.0;
    if v <= 0.04045 {
        v / 12.92
    } else {
        ((v + 0.055) / 1.055).powf(2.4)
    }
}

#[inline]
fn linear_channel_to_srgb(v: f64) -> u8 {
    let clamped = v.clamp(0.0, 1.0);
    let s = if clamped <= 0.0031308 {
        12.92 * clamped
    } else {
        1.055 * clamped.powf(1.0 / 2.4) - 0.055
    };
    (s * 255.0).round().clamp(0.0, 255.0) as u8
}

#[inline]
fn lab_f(t: f64) -> f64 {
    const DELTA: f64 = 6.0 / 29.0;
    if t > DELTA * DELTA * DELTA {
        t.cbrt()
    } else {
        t / (3.0 * DELTA * DELTA) + 4.0 / 29.0
    }
}

#[inline]
fn lab_inv_f(t: f64) -> f64 {
    const DELTA: f64 = 6.0 / 29.0;
    if t > DELTA {
        t * t * t
    } else {
        3.0 * DELTA * DELTA * (t - 4.0 / 29.0)
    }
}

/// Convert sRGB (0..255) to D65 CIELAB.
pub fn srgb_to_lab(r: u8, g: u8, b: u8) -> (f64, f64, f64) {
    let rl = srgb_channel_to_linear(r);
    let gl = srgb_channel_to_linear(g);
    let bl = srgb_channel_to_linear(b);

    let x = (0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl) / 0.95047;
    let y = 0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl;
    let z = (0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl) / 1.08883;

    let fx = lab_f(x);
    let fy = lab_f(y);
    let fz = lab_f(z);

    let l = 116.0 * fy - 16.0;
    let a = 500.0 * (fx - fy);
    let b_lab = 200.0 * (fy - fz);
    (l, a, b_lab)
}

/// Convert D65 CIELAB back to `#RRGGBB` hex string.
pub fn lab_to_hex(l: f64, a: f64, b_lab: f64) -> String {
    let fy = (l + 16.0) / 116.0;
    let fx = a / 500.0 + fy;
    let fz = fy - b_lab / 200.0;

    let x = 0.95047 * lab_inv_f(fx);
    let y = lab_inv_f(fy);
    let z = 1.08883 * lab_inv_f(fz);

    let rl = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z;
    let gl = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z;
    let bl = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z;

    let r = linear_channel_to_srgb(rl);
    let g = linear_channel_to_srgb(gl);
    let b = linear_channel_to_srgb(bl);
    format!("#{r:02X}{g:02X}{b:02X}")
}

/// Analyze one RGB24 frame in-memory using parallel row processing via `rayon`.
pub fn analyze_rgb24_frame(rgb: &[u8], width: usize, height: usize) -> FrameVisionMetrics {
    if width < 3 || height < 3 || rgb.len() < width * height * 3 {
        return FrameVisionMetrics {
            mean_luma: 0.0,
            upper_luma: 0.0,
            center_luma: 0.0,
            lower_third_luma: 0.0,
            sharpness: 0.0,
            lab_bins: HashMap::new(),
        };
    }

    let stride = width * 3;
    let upper_end = height / 4;
    let lower_start = (height * 72) / 100;

    // Parallel luminance & CIELAB histogram accumulation per row.
    type RowLumaLab = (f64, usize, f64, usize, f64, usize, HashMap<(i32, i32, i32), LabBinAcc>);
    let row_results: Vec<RowLumaLab> =
        (0..height)
            .into_par_iter()
            .map(|y| {
                let row = &rgb[y * stride..(y + 1) * stride];
                let mut row_luma_sum = 0.0;
                let mut bins: HashMap<(i32, i32, i32), LabBinAcc> = HashMap::new();

                // Sample every pixel for luma; stride by 2 on x/y for Lab quantization speed.
                let sample_lab_row = y % 2 == 0;
                for x in 0..width {
                    let off = x * 3;
                    let r = row[off];
                    let g = row[off + 1];
                    let b = row[off + 2];
                    let luma = 0.2126 * r as f64 + 0.7152 * g as f64 + 0.0722 * b as f64;
                    row_luma_sum += luma;

                    if sample_lab_row && x % 2 == 0 {
                        let (l, a, b_lab) = srgb_to_lab(r, g, b);
                        let key = (
                            (l / 10.0).round() as i32,
                            (a / 14.0).round() as i32,
                            (b_lab / 14.0).round() as i32,
                        );
                        let acc = bins.entry(key).or_default();
                        acc.count += 1;
                        acc.sum_l += l;
                        acc.sum_a += a;
                        acc.sum_b += b_lab;
                    }
                }

                let (up, up_n, ctr, ctr_n, low, low_n) = if y < upper_end {
                    (row_luma_sum, width, 0.0, 0, 0.0, 0)
                } else if y < lower_start {
                    (0.0, 0, row_luma_sum, width, 0.0, 0)
                } else {
                    (0.0, 0, 0.0, 0, row_luma_sum, width)
                };
                (up, up_n, ctr, ctr_n, low, low_n, bins)
            })
            .collect();

    let mut up_sum = 0.0;
    let mut up_cnt = 0usize;
    let mut ctr_sum = 0.0;
    let mut ctr_cnt = 0usize;
    let mut low_sum = 0.0;
    let mut low_cnt = 0usize;
    let mut merged_bins: HashMap<(i32, i32, i32), LabBinAcc> = HashMap::new();

    for (up, up_n, ctr, ctr_n, low, low_n, bins) in row_results {
        up_sum += up;
        up_cnt += up_n;
        ctr_sum += ctr;
        ctr_cnt += ctr_n;
        low_sum += low;
        low_cnt += low_n;
        for (k, v) in bins {
            let acc = merged_bins.entry(k).or_default();
            acc.count += v.count;
            acc.sum_l += v.sum_l;
            acc.sum_a += v.sum_a;
            acc.sum_b += v.sum_b;
        }
    }

    // Parallel Sobel gradient magnitude mean as sharpness estimator.
    let grad_sum: f64 = (1..(height - 1))
        .into_par_iter()
        .map(|y| {
            let prev = &rgb[(y - 1) * stride..y * stride];
            let curr = &rgb[y * stride..(y + 1) * stride];
            let next = &rgb[(y + 1) * stride..(y + 2) * stride];
            let mut sum = 0.0;
            for x in 1..(width - 1) {
                let luma_at = |row: &[u8], ix: usize| -> f64 {
                    let o = ix * 3;
                    0.2126 * row[o] as f64 + 0.7152 * row[o + 1] as f64 + 0.0722 * row[o + 2] as f64
                };
                let gx = -luma_at(prev, x - 1)
                    + luma_at(prev, x + 1)
                    - 2.0 * luma_at(curr, x - 1)
                    + 2.0 * luma_at(curr, x + 1)
                    - luma_at(next, x - 1)
                    + luma_at(next, x + 1);
                let gy = -luma_at(prev, x - 1) - 2.0 * luma_at(prev, x) - luma_at(prev, x + 1)
                    + luma_at(next, x - 1)
                    + 2.0 * luma_at(next, x)
                    + luma_at(next, x + 1);
                sum += (gx * gx + gy * gy).sqrt();
            }
            sum
        })
        .sum();

    let total_cnt = (up_cnt + ctr_cnt + low_cnt).max(1) as f64;
    let interior_px = ((width - 2) * (height - 2)).max(1) as f64;

    FrameVisionMetrics {
        mean_luma: (up_sum + ctr_sum + low_sum) / total_cnt,
        upper_luma: up_sum / up_cnt.max(1) as f64,
        center_luma: ctr_sum / ctr_cnt.max(1) as f64,
        lower_third_luma: low_sum / low_cnt.max(1) as f64,
        sharpness: grad_sum / interior_px,
        lab_bins: merged_bins,
    }
}

pub fn aggregate_palette_and_visual(
    frames: &[FrameVisionMetrics],
    top_k: usize,
) -> (Vec<PaletteColor>, f64, f64, BandLuminance, f64) {
    if frames.is_empty() {
        return (
            Vec::new(),
            0.0,
            0.0,
            BandLuminance {
                upper: 0.0,
                center: 0.0,
                lower_third: 0.0,
            },
            0.0,
        );
    }

    let n = frames.len() as f64;
    let mean_luma = frames.iter().map(|f| f.mean_luma).sum::<f64>() / n;
    let upper = frames.iter().map(|f| f.upper_luma).sum::<f64>() / n;
    let center = frames.iter().map(|f| f.center_luma).sum::<f64>() / n;
    let lower_third = frames.iter().map(|f| f.lower_third_luma).sum::<f64>() / n;
    let mean_sharpness = frames.iter().map(|f| f.sharpness).sum::<f64>() / n;

    let mut global_bins: HashMap<(i32, i32, i32), LabBinAcc> = HashMap::new();
    let mut total_samples: u64 = 0;

    for f in frames {
        for (k, v) in &f.lab_bins {
            total_samples += v.count;
            let acc = global_bins.entry(*k).or_default();
            acc.count += v.count;
            acc.sum_l += v.sum_l;
            acc.sum_a += v.sum_a;
            acc.sum_b += v.sum_b;
        }
    }

    let total_f = total_samples.max(1) as f64;
    let mut entropy = 0.0;
    for acc in global_bins.values() {
        let p = acc.count as f64 / total_f;
        if p > 0.0 {
            entropy -= p * p.log2();
        }
    }

    let mut buckets: Vec<LabBinAcc> = global_bins.into_values().collect();
    buckets.sort_by_key(|b| std::cmp::Reverse(b.count));

    let palette = buckets
        .into_iter()
        .take(top_k)
        .filter(|b| b.count > 0)
        .map(|b| {
            let c = b.count as f64;
            let l = b.sum_l / c;
            let a = b.sum_a / c;
            let b_lab = b.sum_b / c;
            PaletteColor {
                hex: lab_to_hex(l, a, b_lab),
                share: round3(c / total_f),
                lab_l: round3(l),
                lab_a: round3(a),
                lab_b: round3(b_lab),
            }
        })
        .collect();

    (
        palette,
        round3(entropy),
        round3(mean_luma),
        BandLuminance {
            upper: round3(upper),
            center: round3(center),
            lower_third: round3(lower_third),
        },
        round3(mean_sharpness),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lab_round_trip_preserves_primary_colors() {
        let (l, a, b) = srgb_to_lab(59, 130, 246);
        assert!(l > 40.0 && l < 70.0);
        let hex = lab_to_hex(l, a, b);
        assert_eq!(hex, "#3B82F6");
    }

    #[test]
    fn analyzes_split_brightness_bands_and_sharpness() {
        let w = 20;
        let h = 20;
        let mut rgb = vec![0u8; w * h * 3];
        // Make lower third bright white (255), upper dark (0), and add vertical edge stripe.
        for y in 0..h {
            for x in 0..w {
                let idx = (y * w + x) * 3;
                let val = if y >= (h * 72) / 100 {
                    240
                } else if x % 2 == 0 {
                    120
                } else {
                    20
                };
                rgb[idx] = val;
                rgb[idx + 1] = val;
                rgb[idx + 2] = val;
            }
        }
        let metrics = analyze_rgb24_frame(&rgb, w, h);
        assert!(metrics.lower_third_luma > 235.0);
        assert!(metrics.upper_luma < 80.0);
        assert!(metrics.sharpness > 50.0);
    }
}
