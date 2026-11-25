/**
 * TypeScript contract types mirrored from `contracts/edit_plan.schema.json`
 * and `contracts/platform_target.schema.json`.
 */

export type RenderStrategy = "hybrid" | "full_hf";
export type AssetKind =
  | "video"
  | "audio_speech"
  | "audio_bgm"
  | "audio_sfx"
  | "audio_ambience"
  | "image"
  | "font";
export type ClipRole = "a_roll" | "b_roll" | "screen_recording" | "cutaway";
export type OverlayKind =
  | "caption_rail"
  | "kinetic_callout"
  | "lower_third"
  | "data_card"
  | "title_scene"
  | "full_scene";
export type SafeBand =
  | "lower_third"
  | "upper_safe"
  | "left_rail"
  | "right_rail"
  | "center_safe"
  | "fullscreen";

export interface BoundingBox {
  top: number;
  bottom: number;
  left: number;
  right: number;
  label?: string;
}

export interface SafeZoneMargins {
  top_pct: number;
  bottom_pct: number;
  left_pct: number;
  right_pct: number;
}

export interface PlatformTarget {
  platform_id: string;
  display_name?: string;
  aspect_ratio: "16:9" | "9:16" | "1:1" | "4:5";
  width: number;
  height: number;
  fps: number;
  safe_zone: SafeZoneMargins;
}

export interface AssetRef {
  asset_id: string;
  sha256: string;
  kind: AssetKind;
  path: string;
  duration_s?: number;
  has_audio?: boolean;
}

export interface ColorCorrectionSpec {
  exposure_ev?: number;
  contrast?: number;
  saturation?: number;
  temperature?: number;
  tint?: number;
  gamma?: number;
  lift?: number | null;
  gain?: number | null;
}

export interface ColorGradeSpec {
  preset?:
    | "neutral"
    | "catastrophe_warm"
    | "dread_dim_vignette"
    | "anomaly_desat"
    | "archival_sepia"
    | "cool_investigative"
    | null;
  lut_path?: string | null;
  vignette_strength?: number | null;
  intensity?: number;
}

export interface VideoClipOp {
  clip_id: string;
  asset_id: string;
  timeline_start_s: number;
  timeline_duration_s: number;
  source_start_s: number;
  role: ClipRole;
  content_type?: "live_action" | "map" | "landscape" | "diagram" | "archival";
  visual_beat_count?: number;
  reframed_to_target?: boolean;
  scale?: number;
  transition_in?: string | null;
  j_cut_lead_s?: number | null;
  l_cut_trail_s?: number | null;
  shot_scale?: "ews" | "ws" | "ms" | "mcu" | "cu" | "ecu" | null;
  camera_angle?: "eye_level" | "low_angle" | "high_angle" | "birds_eye" | "dutch" | null;
  motion_direction?:
    | "static"
    | "left_to_right"
    | "right_to_left"
    | "push_in"
    | "pull_out"
    | "up"
    | "down"
    | null;
  focal_length_mm?: number | null;
  lighting_key?: "high_key" | "normal_key" | "low_key" | "chiaroscuro" | null;
  color_correction?: ColorCorrectionSpec | null;
  color_grade?: ColorGradeSpec | null;
  subject_safe_boxes?: BoundingBox[];
}

export interface OverlayTrackKeyframe {
  t_s: number;
  x_pct: number;
  y_pct: number;
  scale?: number;
  rotation_deg?: number;
  rotateX_deg?: number;
  perspective_px?: number;
  opacity?: number;
  curve?: "linear" | "arc_up" | "arc_down" | "ease_out" | "ease_in_out" | null;
  arc_height_px?: number | null;
}

export interface OverlayCompositionOp {
  overlay_id: string;
  kind: OverlayKind;
  timeline_start_s: number;
  timeline_duration_s: number;
  transparent: boolean;
  safe_band?: SafeBand;
  blend_mode?: "normal" | "screen" | "multiply" | "overlay" | "lighten" | null;
  matte_mode?: "none" | "alpha_matte" | "luma_matte" | "inverted_alpha" | null;
  parent_overlay_id?: string | null;
  motion_register?: "documentary" | "wry" | "comic" | null;
  anticipation_ms?: number | null;
  overlap_stagger_ms?: number | null;
  template_id?: string;
  variables?: Record<string, unknown>;
  track_keyframes?: OverlayTrackKeyframe[];
  props: Record<string, unknown>;
}

export interface AudioTrackOp {
  track_id: string;
  asset_id: string;
  audio_group: "voiceover" | "music" | "sfx" | "ambience" | "room_tone" | "program_mix";
  timeline_start_s: number;
  timeline_duration_s: number;
  source_start_s: number;
  gain_db?: number;
  carve_against_group?: string | null;
  carve_strength?: number;
  cleaned_speech_stem?: boolean;
  diegetic?: boolean;
  layer_role?:
    | "sub"
    | "body"
    | "detail"
    | "tail"
    | "riser"
    | "drone"
    | "pulse"
    | "stinger"
    | "hit"
    | null;
  pan?: number | null;
  reverb_preset?: "dry" | "close" | "medium" | "wide" | null;
  fade_in_s?: number;
  fade_out_s?: number;
  highpass_hz?: number | null;
  lowpass_hz?: number | null;
  split_edit_role?: "j_cut" | "l_cut" | null;
  split_edit_offset_s?: number | null;
  haas_delay_ms?: number | null;
  reverb_pan?: number | null;
}

export interface EditPlan {
  schema_version: "1.0";
  job_id: string;
  project_id: string;
  brand_id: string;
  platform_target_id: string;
  render_strategy: RenderStrategy;
  duration_s: number;
  fps: number;
  width: number;
  height: number;
  assets: AssetRef[];
  video_tracks: VideoClipOp[];
  overlay_compositions: OverlayCompositionOp[];
  audio_tracks: AudioTrackOp[];
  verifier_passed?: boolean;
}
