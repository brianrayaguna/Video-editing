/**
 * TypeScript contract types mirrored from `contracts/edit_plan.schema.json`
 * and `contracts/platform_target.schema.json`.
 */

export type RenderStrategy = "hybrid" | "full_hf";
export type AssetKind = "video" | "audio_speech" | "audio_bgm" | "audio_sfx" | "image" | "font";
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

export interface VideoClipOp {
  clip_id: string;
  asset_id: string;
  timeline_start_s: number;
  timeline_duration_s: number;
  source_start_s: number;
  role: ClipRole;
  reframed_to_target?: boolean;
  scale?: number;
  transition_in?: string | null;
  subject_safe_boxes?: BoundingBox[];
}

export interface OverlayCompositionOp {
  overlay_id: string;
  kind: OverlayKind;
  timeline_start_s: number;
  timeline_duration_s: number;
  transparent: boolean;
  safe_band?: SafeBand;
  props: Record<string, unknown>;
}

export interface AudioTrackOp {
  track_id: string;
  asset_id: string;
  audio_group: "voiceover" | "music" | "sfx";
  timeline_start_s: number;
  timeline_duration_s: number;
  source_start_s: number;
  gain_db?: number;
  carve_against_group?: string | null;
  carve_strength?: number;
  cleaned_speech_stem?: boolean;
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
