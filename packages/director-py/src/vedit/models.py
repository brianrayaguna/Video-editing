"""Typed Pydantic v2 models mirroring cross-runtime JSON Schema contracts."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

_SAFE_SLUG_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
_HEX_SHA_PATTERN = r"^[0-9a-fA-F]{16,64}$"
_WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _validate_safe_relative_path(value: str) -> str:
    if not value or value.startswith(("/", "\\", "~")) or _WIN_DRIVE_RE.match(value):
        raise ValueError(f"Expected a relative path without leading root/drive, got {value!r}")
    parts = re.split(r"[\\/]", value)
    if ".." in parts:
        raise ValueError(f"Relative path cannot contain parent traversal ('..'): {value!r}")
    return value


SafeRelativePath = Annotated[str, AfterValidator(_validate_safe_relative_path)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoMasteringSpec(StrictModel):
    container: Literal["mp4", "mov"]
    codec: Literal["h264", "hevc", "prores"]
    profile: str
    pixel_format: Literal["yuv420p", "yuv422p10le", "yuva444p10le"]
    color_space: Literal["bt709", "bt2020nc"]
    color_primaries: Literal["bt709", "bt2020"]
    color_trc: Literal["bt709", "smpte2084"]
    target_bitrate_mbps: float = Field(gt=0)
    max_bitrate_mbps: float = Field(gt=0)
    high_fps_target_bitrate_mbps: float | None = Field(default=None, gt=0)
    gop_seconds: float = Field(gt=0)
    faststart: bool = True


class AudioMasteringSpec(StrictModel):
    codec: Literal["aac"] = "aac"
    sample_rate_hz: Literal[48000] = 48000
    channels: Literal[1, 2] = 2
    bitrate_kbps: int = Field(ge=128, le=512)
    target_lufs: float = Field(ge=-24.0, le=-8.0, default=-14.0)
    lufs_tolerance: float = Field(ge=0.1, le=2.0, default=0.5)
    max_true_peak_dbtp: float = Field(ge=-3.0, le=-0.5, default=-1.0)
    target_lra: float = Field(ge=2.0, le=15.0, default=7.0)


class SafeZoneMargins(StrictModel):
    top_pct: float = Field(ge=0.0, le=0.4)
    bottom_pct: float = Field(ge=0.0, le=0.45)
    left_pct: float = Field(ge=0.0, le=0.3)
    right_pct: float = Field(ge=0.0, le=0.35)


class TimebaseSpec(StrictModel):
    num: int = Field(ge=1)
    den: int = Field(ge=1, default=1)


_ALLOWED_PLATFORM_FPS: tuple[float, ...] = (
    23.976,
    24.0,
    25.0,
    29.97,
    30.0,
    48.0,
    50.0,
    59.94,
    60.0,
)


class PlatformTarget(StrictModel):
    platform_id: str = Field(min_length=1)
    display_name: str | None = None
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:5"]
    width: int = Field(ge=360, le=7680)
    height: int = Field(ge=360, le=7680)
    fps: float
    timebase: TimebaseSpec | None = None
    purpose: Literal["long_form", "short_form", "social_square", "archive_master"] | None = None
    video: VideoMasteringSpec
    audio: AudioMasteringSpec
    safe_zone: SafeZoneMargins
    notes: str | None = None

    @field_validator("fps")
    @classmethod
    def _validate_supported_fps(cls, value: float) -> float:
        for allowed in _ALLOWED_PLATFORM_FPS:
            if abs(float(value) - allowed) < 1e-4:
                return int(allowed) if allowed.is_integer() else allowed
        raise ValueError(
            f"Unsupported platform fps {value!r}; expected one of {_ALLOWED_PLATFORM_FPS}"
        )


class TranscriptWord(StrictModel):
    text: str
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)
    speaker: str | int | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_filler: bool = False


class TranscriptSegment(StrictModel):
    id: int | str | None = None
    start: float | None = Field(default=None, ge=0.0)
    end: float | None = Field(default=None, ge=0.0)
    start_s: float | None = Field(default=None, ge=0.0)
    end_s: float | None = Field(default=None, ge=0.0)
    text: str
    speaker: str | int | None = None


class NormalizedTranscript(StrictModel):
    source_hash: str = Field(min_length=8)
    provider: str = Field(min_length=1)
    model: str | None = None
    language: str = Field(min_length=2)
    duration_s: float = Field(ge=0.0)
    text: str
    words: list[TranscriptWord]
    segments: list[TranscriptSegment] | None = None


class TemporalSectionPrior(StrictModel):
    section: Literal["hook", "setup", "body", "escalation", "climax", "outro"]
    asl_p25_s: float = Field(gt=0)
    asl_p50_s: float = Field(gt=0)
    asl_p75_s: float = Field(gt=0)
    cuts_per_min_range: list[float] = Field(min_length=2, max_length=2)
    energy_target: float = Field(ge=0.0, le=1.0)
    preferred_transitions: list[str] = Field(default_factory=list)


class PaletteRoles(StrictModel):
    ground: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    ink: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_accent: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    hydro_accent: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    comparison_accent: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    surface_elevated: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    muted_ink: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class TypeScaleStep(StrictModel):
    size_px_9x16: int = Field(ge=12, le=240)
    size_px_16x9: int = Field(ge=12, le=240)
    weight: int = Field(ge=100, le=900)
    line_height: float = Field(ge=0.8, le=2.2)
    letter_spacing_em: float = Field(ge=-0.08, le=0.35)
    family_role: Literal["display", "title", "body", "caption", "mono", "serif"]
    min_wcag_contrast: float | None = Field(default=None, ge=3.0, le=21.0)


class TypeScaleTokens(StrictModel):
    hero: TypeScaleStep | None = None
    display: TypeScaleStep | None = None
    title: TypeScaleStep | None = None
    caption: TypeScaleStep | None = None
    telemetry: TypeScaleStep | None = None
    body: TypeScaleStep | None = None
    micro: TypeScaleStep | None = None


class TypographyTokens(StrictModel):
    display_family: str
    body_family: str
    title_family: str | None = None
    serif_family: str | None = None
    mono_family: str | None = None
    base_rem_px: float | None = Field(default=None, ge=8.0, le=32.0)
    caption_case: Literal["sentence", "uppercase", "title", "lowercase"]
    caption_style: Literal["plain", "chip", "bar"] | None = None
    caption_transition_ms: int | None = Field(default=None, ge=0, le=200)
    caption_fade_in_ms: int | None = Field(default=None, ge=0, le=200)
    caption_fade_out_ms: int | None = Field(default=None, ge=0, le=200)
    caption_gap_ms: int | None = Field(default=None, ge=0, le=250)
    caption_letter_spacing_em: float | None = Field(default=None, ge=-0.05, le=0.25)
    max_words_per_caption_group: int = Field(ge=1, le=12)
    default_caption_band: Literal[
        "lower_third", "center_safe", "upper_safe", "dynamic_away_from_subject"
    ] = "dynamic_away_from_subject"
    caption_font_family: str | None = None
    caption_font_px_9x16: int | None = Field(default=None, ge=20, le=120)
    caption_margin_v_px_9x16: int | None = Field(default=None, ge=0, le=960)
    caption_band_y_pct_9x16: list[float] | None = Field(default=None, min_length=2, max_length=2)
    type_scale: TypeScaleTokens | None = None


class MotionStyleTokens(StrictModel):
    easing_feel: Literal[
        "snappy_ease_out", "smooth_editorial", "energetic_pop", "minimal_static"
    ]
    entrance_ms_range: list[int] = Field(min_length=2, max_length=2)
    punch_in_scale_range: list[float] | None = Field(default=None, min_length=2, max_length=2)


class VisualTokens(StrictModel):
    palette_roles: PaletteRoles
    typography: TypographyTokens
    motion_style: MotionStyleTokens


class AudioStyleTokens(StrictModel):
    bgm_moods: list[str]
    bpm_range: list[float] | None = Field(default=None, min_length=2, max_length=2)
    ducking_strength: float = Field(ge=0.0, le=1.0)
    sfx_policy: Literal["none", "selective_transitions", "kinetic_accents"]


class SoftPriors(StrictModel):
    temporal_curve: list[TemporalSectionPrior] = Field(min_length=1)
    visual_tokens: VisualTokens
    audio_style: AudioStyleTokens


class GrammarTrigger(StrictModel):
    trigger_id: str
    condition: str
    action: str
    weight: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class HardGuardrails(StrictModel):
    min_shot_duration_s: float = Field(ge=0.2)
    max_uninterrupted_hold_s: float = Field(ge=1.0)
    no_cut_within_keyword_ms: int = Field(ge=0, le=1000)
    never_overlap_subject_boxes: bool = True
    min_wcag_contrast: float = Field(ge=3.0, default=4.5)
    min_wcag_contrast_small_text: float = Field(ge=4.5, le=21.0, default=7.0)
    banned_transitions: list[str] = Field(default_factory=list)
    banned_patterns: list[str] = Field(default_factory=list)
    avoid_heavy_css_blur: bool = True


class StyleExemplar(StrictModel):
    exemplar_id: str
    source_video_id: str
    role: Literal["hook", "setup", "proof", "data_callout", "broll_bridge", "climax", "outro"]
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)
    keyframe_path: str | None = None
    hyperframes_pattern: str | None = None
    measured_metrics: dict[str, Any] = Field(default_factory=dict)
    notes: str


class StyleCalibration(StrictModel):
    accepted_overrides: int = Field(ge=0, default=0)
    rejected_patterns: list[str] = Field(default_factory=list)
    last_calibrated_at: str | None = None


class BrandProvenance(StrictModel):
    reference_video_count: int = Field(ge=1)
    reference_hashes: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: str | None = None


class BrandFormatOverride(StrictModel):
    format_name: str | None = None
    min_shot_duration_s: float | None = Field(default=None, ge=0.2)
    max_uninterrupted_hold_s: float | None = Field(default=None, ge=1.0)
    default_caption_band: (
        Literal["lower_third", "center_safe", "upper_safe", "dynamic_away_from_subject"] | None
    ) = None
    watermark_default: bool | None = None
    temporal_curve: list[TemporalSectionPrior] | None = Field(default=None, min_length=1)


class BrandStylePolicy(StrictModel):
    """Runtime brand policy for planner/verifier.

    Advisory grammar triggers and exemplars belong in `EditorialPlaybook`, not
    on this runtime object.
    """

    schema_version: Literal["1.0"] = "1.0"
    brand_id: str = Field(min_length=1)
    display_name: str | None = None
    editorial_identity: str | None = None
    soft_priors: SoftPriors
    hard_guardrails: HardGuardrails
    format_overrides: dict[str, BrandFormatOverride] | None = None
    provenance: BrandProvenance
    calibration: StyleCalibration | None = None


class EditorialPlaybook(StrictModel):
    """Advisory directing playbook. Not executed by planner/verifier/compile."""

    schema_version: Literal["1.0"] = "1.0"
    brand_id: str = Field(min_length=1)
    schema_note: str | None = None
    grammar_triggers: list[GrammarTrigger] = Field(default_factory=list)
    exemplar_bank: list[StyleExemplar] = Field(default_factory=list)


class BrandTemplateVariable(StrictModel):
    id: str = Field(min_length=1)
    type: Literal["string", "number", "boolean", "color", "image", "enum"]
    label: str | None = None
    default: Any | None = None
    enum_values: list[str] | None = None
    min: float | None = None
    max: float | None = None
    token_ref: str | None = None


class BrandTemplateEntry(StrictModel):
    template_id: str = Field(min_length=1)
    composition_path: str = Field(min_length=1)
    overlay_kind: (
        Literal[
            "caption_rail",
            "kinetic_callout",
            "lower_third",
            "data_card",
            "title_scene",
            "full_scene",
        ]
        | None
    ) = None
    supported_aspects: list[Literal["9:16", "16:9", "1:1", "4:5"]] | None = None
    render_mode: Literal["parameterized_html", "static_copy"] | None = None
    description: str | None = None
    safe_band: (
        Literal["lower_third", "upper_safe", "center_safe", "dynamic_away_from_subject"] | None
    ) = None
    variables: list[BrandTemplateVariable] = Field(default_factory=list)


class BrandTemplateCatalog(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    brand_id: str = Field(min_length=1)
    templates: list[BrandTemplateEntry] = Field(min_length=1)


class BoundingBox(StrictModel):
    top: float = Field(ge=0.0, le=1.0)
    bottom: float = Field(ge=0.0, le=1.0)
    left: float = Field(ge=0.0, le=1.0)
    right: float = Field(ge=0.0, le=1.0)
    label: str | None = None

    @model_validator(mode="after")
    def _validate_ordered_bounds(self) -> BoundingBox:
        if self.top >= self.bottom:
            raise ValueError(f"BoundingBox requires top < bottom, got {self.top} >= {self.bottom}")
        if self.left >= self.right:
            raise ValueError(f"BoundingBox requires left < right, got {self.left} >= {self.right}")
        return self


class AssetRef(StrictModel):
    asset_id: str
    sha256: str = Field(min_length=16, max_length=64, pattern=_HEX_SHA_PATTERN)
    kind: Literal[
        "video", "audio_speech", "audio_bgm", "audio_sfx", "audio_ambience", "image", "font"
    ]
    path: str
    duration_s: float | None = Field(default=None, ge=0.0)
    has_audio: bool = False


class ColorCorrectionSpec(StrictModel):
    exposure_ev: float = Field(default=0.0, ge=-2.0, le=2.0)
    contrast: float = Field(default=1.0, ge=0.5, le=1.8)
    saturation: float = Field(default=1.0, ge=0.0, le=2.0)
    temperature: float = Field(default=0.0, ge=-1.0, le=1.0)
    tint: float = Field(default=0.0, ge=-1.0, le=1.0)
    gamma: float = Field(default=1.0, ge=0.5, le=2.0)
    lift: float | None = Field(default=None, ge=-0.5, le=0.5)
    gain: float | None = Field(default=None, ge=-0.5, le=0.5)


class ColorGradeSpec(StrictModel):
    preset: (
        Literal[
            "neutral",
            "catastrophe_warm",
            "dread_dim_vignette",
            "anomaly_desat",
            "archival_sepia",
            "cool_investigative",
        ]
        | None
    ) = None
    lut_path: str | None = None
    vignette_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    intensity: float = Field(default=1.0, ge=0.0, le=1.0)


class VideoClipOp(StrictModel):
    clip_id: str
    asset_id: str
    timeline_start_s: float = Field(ge=0.0)
    timeline_duration_s: float = Field(gt=0.0)
    source_start_s: float = Field(ge=0.0)
    start_frame: int | None = Field(default=None, ge=0)
    duration_frames: int | None = Field(default=None, ge=1)
    source_start_frame: int | None = Field(default=None, ge=0)
    role: Literal["a_roll", "b_roll", "screen_recording", "cutaway"]
    content_type: Literal["live_action", "map", "landscape", "diagram", "archival"] | None = None
    visual_beat_count: int = Field(ge=0, default=0)
    reframed_to_target: bool = True
    scale: float = Field(ge=0.1, le=4.0, default=1.0)
    transition_in: str | None = None
    j_cut_lead_s: float | None = Field(default=None, ge=0.0, le=4.0)
    l_cut_trail_s: float | None = Field(default=None, ge=0.0, le=4.0)
    shot_scale: Literal["ews", "ws", "ms", "mcu", "cu", "ecu"] | None = None
    camera_angle: Literal["eye_level", "low_angle", "high_angle", "birds_eye", "dutch"] | None = (
        None
    )
    motion_direction: (
        Literal["static", "left_to_right", "right_to_left", "push_in", "pull_out", "up", "down"]
        | None
    ) = None
    focal_length_mm: float | None = Field(default=None, ge=12.0, le=600.0)
    lighting_key: Literal["high_key", "normal_key", "low_key", "chiaroscuro"] | None = None
    color_correction: ColorCorrectionSpec | None = None
    color_grade: ColorGradeSpec | None = None
    subject_safe_boxes: list[BoundingBox] = Field(default_factory=list)


class OverlayTrackKeyframe(StrictModel):
    t_s: float = Field(ge=0.0)
    x_pct: float
    y_pct: float
    scale: float | None = Field(default=None, gt=0.0)
    rotation_deg: float | None = None
    rotateX_deg: float | None = Field(default=None, ge=-75.0, le=75.0)
    perspective_px: float | None = Field(default=None, gt=0.0)
    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    curve: Literal["linear", "arc_up", "arc_down", "ease_out", "ease_in_out"] | None = None
    arc_height_px: float | None = Field(default=None, ge=-400.0, le=400.0)


class OverlayCompositionOp(StrictModel):
    overlay_id: str
    kind: Literal[
        "caption_rail", "kinetic_callout", "lower_third", "data_card", "title_scene", "full_scene"
    ]
    timeline_start_s: float = Field(ge=0.0)
    timeline_duration_s: float = Field(gt=0.0)
    start_frame: int | None = Field(default=None, ge=0)
    duration_frames: int | None = Field(default=None, ge=1)
    transparent: bool = True
    safe_band: Literal[
        "lower_third", "upper_safe", "left_rail", "right_rail", "center_safe", "fullscreen"
    ] = "lower_third"
    blend_mode: Literal["normal", "screen", "multiply", "overlay", "lighten"] | None = None
    matte_mode: Literal["none", "alpha_matte", "luma_matte", "inverted_alpha"] | None = None
    parent_overlay_id: str | None = None
    motion_register: Literal["documentary", "wry", "comic"] | None = None
    anticipation_ms: int | None = Field(default=None, ge=0, le=250)
    overlap_stagger_ms: int | None = Field(default=None, ge=0, le=250)
    template_id: str | None = Field(default=None, min_length=1)
    variables: dict[str, Any] = Field(default_factory=dict)
    track_keyframes: list[OverlayTrackKeyframe] = Field(default_factory=list)
    props: dict[str, Any] = Field(default_factory=dict)


class AudioTrackOp(StrictModel):
    track_id: str
    asset_id: str
    audio_group: Literal[
        "voiceover", "music", "sfx", "ambience", "room_tone", "program_mix"
    ]
    timeline_start_s: float = Field(ge=0.0)
    timeline_duration_s: float = Field(gt=0.0)
    source_start_s: float = Field(ge=0.0)
    start_frame: int | None = Field(default=None, ge=0)
    duration_frames: int | None = Field(default=None, ge=1)
    source_start_frame: int | None = Field(default=None, ge=0)
    gain_db: float = Field(ge=-60.0, le=24.0, default=0.0)
    carve_against_group: str | None = None
    carve_strength: float = Field(ge=0.0, le=1.0, default=0.8)
    cleaned_speech_stem: bool = False
    diegetic: bool | None = None
    layer_role: (
        Literal["sub", "body", "detail", "tail", "riser", "drone", "pulse", "stinger", "hit"]
        | None
    ) = None
    pan: float | None = Field(default=None, ge=-1.0, le=1.0)
    reverb_preset: Literal["dry", "close", "medium", "wide"] | None = None
    fade_in_s: float | None = Field(default=None, ge=0.0)
    fade_out_s: float | None = Field(default=None, ge=0.0)
    highpass_hz: float | None = Field(default=None, ge=20.0, le=2000.0)
    lowpass_hz: float | None = Field(default=None, ge=80.0, le=20000.0)
    split_edit_role: Literal["j_cut", "l_cut"] | None = None
    split_edit_offset_s: float | None = Field(default=None, ge=-5.0, le=5.0)
    haas_delay_ms: float | None = Field(default=None, ge=0.0, le=25.0)
    reverb_pan: float | None = Field(default=None, ge=-1.0, le=1.0)


class EditPlan(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    job_id: str = Field(min_length=1, pattern=_SAFE_SLUG_PATTERN)
    project_id: str = Field(min_length=1)
    brand_id: str = Field(min_length=1)
    platform_target_id: str = Field(min_length=1)
    render_strategy: Literal["hybrid", "full_hf"]
    duration_s: float = Field(gt=0.0)
    fps: float = Field(gt=0.0)
    timebase: TimebaseSpec | None = None
    width: int = Field(ge=360)
    height: int = Field(ge=360)
    assets: list[AssetRef]
    video_tracks: list[VideoClipOp]
    overlay_compositions: list[OverlayCompositionOp]
    audio_tracks: list[AudioTrackOp]
    verifier_passed: bool = False

    @model_validator(mode="after")
    def _validate_rational_frame_fields(self) -> EditPlan:
        from vedit.timebase import Timebase

        tb = (
            Timebase(self.timebase.num, self.timebase.den)
            if self.timebase is not None
            else Timebase.from_fps(self.fps)
        )
        if self.timebase is not None and abs(self.fps - tb.fps_float) > 0.01:
            raise ValueError(
                f"EditPlan fps={self.fps} conflicts with timebase="
                f"{tb.num}/{tb.den} ({tb.fps_float:.4f})"
            )

        rate = tb.fps_float
        tol = 0.5001

        def _check_frame(
            item_label: str, field_name: str, frame_val: int | None, sec_val: float
        ) -> None:
            if frame_val is None:
                return
            expected = sec_val * rate
            if abs(frame_val - expected) > tol:
                raise ValueError(
                    f"{item_label}.{field_name}={frame_val} conflicts with "
                    f"{sec_val}s at {tb.ffmpeg_rate_str} fps (expected ~{expected:.2f} frames)"
                )

        for clip in self.video_tracks:
            lbl = f"video_tracks[{clip.clip_id}]"
            _check_frame(lbl, "start_frame", clip.start_frame, clip.timeline_start_s)
            _check_frame(lbl, "duration_frames", clip.duration_frames, clip.timeline_duration_s)
            _check_frame(lbl, "source_start_frame", clip.source_start_frame, clip.source_start_s)

        for ov in self.overlay_compositions:
            lbl = f"overlay_compositions[{ov.overlay_id}]"
            _check_frame(lbl, "start_frame", ov.start_frame, ov.timeline_start_s)
            _check_frame(lbl, "duration_frames", ov.duration_frames, ov.timeline_duration_s)

        for trk in self.audio_tracks:
            lbl = f"audio_tracks[{trk.track_id}]"
            _check_frame(lbl, "start_frame", trk.start_frame, trk.timeline_start_s)
            _check_frame(lbl, "duration_frames", trk.duration_frames, trk.timeline_duration_s)
            _check_frame(lbl, "source_start_frame", trk.source_start_frame, trk.source_start_s)

        return self


class TimeInterval(StrictModel):
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)
    duration_s: float = Field(ge=0.0)


class ProbeContainerInfo(StrictModel):
    format_name: str
    duration_s: float = Field(ge=0.0)
    bit_rate: int | None = Field(default=None, ge=0)


class ProbeVideoInfo(StrictModel):
    present: bool
    codec: str | None = None
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    fps: float = Field(ge=0.0)
    is_cfr: bool
    pixel_format: str | None = None
    color_space: str | None = None
    color_primaries: str | None = None
    color_trc: str | None = None
    frame_count_est: int = Field(default=0, ge=0)


class ProbeAudioInfo(StrictModel):
    present: bool
    codec: str | None = None
    sample_rate_hz: int | None = Field(default=None, ge=0)
    channels: int | None = Field(default=None, ge=0)
    integrated_lufs: float | None = None
    lra: float | None = Field(default=None, ge=0.0)
    true_peak_dbtp: float | None = None
    silence_intervals: list[TimeInterval]
    silence_ratio: float = Field(ge=0.0, le=1.0)


class ProbeShotSegment(StrictModel):
    shot_index: int = Field(ge=0)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)
    duration_s: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)


class ProbeShotStats(StrictModel):
    count: int = Field(ge=0)
    asl_p25_s: float = Field(ge=0.0)
    asl_p50_s: float = Field(ge=0.0)
    asl_p75_s: float = Field(ge=0.0)
    cuts_per_min: float = Field(ge=0.0)


class ProbePaletteColor(StrictModel):
    hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    share: float = Field(ge=0.0, le=1.0)
    lab_l: float
    lab_a: float
    lab_b: float


class ProbeBandLuminance(StrictModel):
    upper: float = Field(ge=0.0, le=255.0)
    center: float = Field(ge=0.0, le=255.0)
    lower_third: float = Field(ge=0.0, le=255.0)


class ProbeKeyframeInfo(StrictModel):
    timestamp_s: float = Field(ge=0.0)
    shot_index: int = Field(ge=0)
    path: str
    luma_lower_third: float = Field(ge=0.0, le=255.0)
    sharpness: float = Field(ge=0.0)


class ProbeVisualInfo(StrictModel):
    sampled_frames: int = Field(ge=0)
    palette: list[ProbePaletteColor]
    palette_entropy: float = Field(ge=0.0)
    mean_luminance: float = Field(ge=0.0, le=255.0)
    band_luminance: ProbeBandLuminance
    mean_sharpness: float = Field(ge=0.0)
    black_intervals: list[TimeInterval]
    keyframes: list[ProbeKeyframeInfo]


class ProbeTimingBreakdown(StrictModel):
    hash_ms: int = Field(ge=0)
    ffprobe_ms: int = Field(ge=0)
    stream_analyze_ms: int = Field(ge=0)
    total_ms: int = Field(ge=0)


class MediaProbeResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    path: str
    sha256: str = Field(min_length=64, max_length=64)
    file_bytes: int = Field(ge=0)
    container: ProbeContainerInfo
    video: ProbeVideoInfo
    audio: ProbeAudioInfo
    shots: list[ProbeShotSegment]
    shot_stats: ProbeShotStats
    visual: ProbeVisualInfo
    timing_ms: ProbeTimingBreakdown


class BreakdownShot(StrictModel):
    shot_index: int = Field(ge=0)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)
    duration_s: float = Field(ge=0.0)
    transition_in: Literal[
        "start", "cut", "jump", "fade", "dissolve", "wipe", "flash", "other"
    ] = "cut"
    transition_duration_s: float | None = Field(default=None, ge=0.0)
    production_label: str = Field(min_length=1)
    production_confidence: float = Field(ge=0.0, le=1.0)
    narrative_role: (
        Literal["hook", "context", "info", "proof", "turn", "payoff", "cta", "mood"] | None
    ) = None
    narrative_point: str | None = None
    description: str | None = None
    beats_s: list[float] = Field(default_factory=list)
    drawn_palette_hex: list[str] = Field(default_factory=list)
    has_embedded_real_assets: bool = False
    low_confidence_flag: bool = False
    sheet_path: str | None = None


class BreakdownEditingMetrics(StrictModel):
    cuts_per_min: float = Field(ge=0.0)
    avg_shot_s: float = Field(ge=0.0)
    camera_positions: int | None = Field(default=None, ge=0)
    jump_cuts: int = Field(default=0, ge=0)
    punch_ins: int = Field(default=0, ge=0)
    punch_in_scale_ratios: list[float] = Field(default_factory=list)
    cuts_in_pauses_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    insert_share: float | None = Field(default=None, ge=0.0, le=1.0)
    beat_synced_edit: bool = False


class BreakdownPackagingMetrics(StrictModel):
    subtitle_count: int = Field(default=0, ge=0)
    caption_case_observed: Literal["sentence", "uppercase", "title", "lowercase"] | None = None
    caption_style_observed: Literal["plain", "chip", "bar"] | None = None
    caption_band_observed: Literal["lower_third", "center_safe", "upper_safe"] | None = None
    caption_words_p50: float | None = Field(default=None, ge=0.0)
    caption_words_p75: float | None = Field(default=None, ge=0.0)
    caption_entrance_animations: list[str] = Field(default_factory=list)
    caption_entrance_ms_median: int | None = Field(default=None, ge=0)
    caption_fill_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_stroke_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_box_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    persistent_watermark_detected: bool = False
    styled_text_count: int = Field(default=0, ge=0)
    sticker_count: int = Field(default=0, ge=0)
    overlay_text_samples: list[str] = Field(default_factory=list)


class BreakdownAudioMetrics(StrictModel):
    has_audio: bool = False
    has_voice: bool = False
    has_music: bool = False
    tempo_bpm: float | None = Field(default=None, ge=20.0, le=260.0)
    beat_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    no_beat: bool = True
    key_tonic: str | None = None
    key_mode: Literal["major", "minor"] | None = None
    vocal_style: Literal["speech", "singing", "rap_or_rhythmic"] | None = None
    sfx_count: int = Field(default=0, ge=0)
    sfx_types: list[str] = Field(default_factory=list)
    sfx_aligned_to_visual_count: int = Field(default=0, ge=0)
    music_section_changes_s: list[float] = Field(default_factory=list)


class BreakdownGradeMetrics(StrictModel):
    look: str | None = None
    saturation: float | None = Field(default=None, ge=0.0, le=1.0)
    contrast: float | None = Field(default=None, ge=0.0, le=1.0)
    black_level: float | None = Field(default=None, ge=0.0, le=100.0)
    white_level: float | None = Field(default=None, ge=0.0, le=100.0)
    shadow_b: float | None = None
    highlight_b: float | None = None
    mean_l: float | None = Field(default=None, ge=0.0, le=100.0)
    tone: Literal["warm", "cool", "neutral"] | None = None


class VideoBreakdownResult(StrictModel):
    """Normalized forensic reference-video breakdown produced by `VideoBreakdownPort`."""

    schema_version: Literal["1.0"] = "1.0"
    provider: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_sha256: str | None = Field(default=None, min_length=8)
    duration_s: float = Field(ge=0.0)
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    fps: float = Field(ge=0.0)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:5", "other"] = "other"
    output_dir: str | None = None
    videomd_path: str | None = None
    storyboard_path: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reviewed_by: list[str] = Field(default_factory=list)
    verdict: str | None = None
    generative_reference_warning: bool = False
    production_mix: dict[str, float] = Field(default_factory=dict)
    shots: list[BreakdownShot] = Field(default_factory=list)
    editing: BreakdownEditingMetrics
    packaging: BreakdownPackagingMetrics
    audio: BreakdownAudioMetrics
    grade: BreakdownGradeMetrics


class ProjectDirectories(StrictModel):
    inputs: SafeRelativePath = "inputs"
    probes: SafeRelativePath = "analysis/probes"
    breakdowns: SafeRelativePath = "analysis/breakdowns"
    transcripts: SafeRelativePath = "analysis/transcripts"
    decisions: SafeRelativePath = "analysis/decisions"
    maps: SafeRelativePath = "media/maps"
    broll: SafeRelativePath = "media/broll"
    audio: SafeRelativePath = "media/audio"
    plan: SafeRelativePath = "plan"
    build: SafeRelativePath = "build"
    output: SafeRelativePath = "output"


class ProjectArtifacts(StrictModel):
    brief: SafeRelativePath = "brief.md"
    edit_plan: SafeRelativePath = "plan/edit_plan.json"
    verification: SafeRelativePath = "plan/verification.json"
    master: SafeRelativePath = "output/master.mp4"
    audit: SafeRelativePath = "output/audit.json"
    otio: SafeRelativePath = "output/timeline.otio"
    benchmark: SafeRelativePath = "output/benchmark.json"


class ProjectManifest(StrictModel):
    """Self-contained external editing project manifest using relative paths only."""

    schema_version: Literal["1.0"] = "1.0"
    project_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    brand_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    platform_target_id: str = Field(min_length=1)
    title: str | None = None
    created_at: str = Field(min_length=1)
    directories: ProjectDirectories = Field(default_factory=ProjectDirectories)
    artifacts: ProjectArtifacts = Field(default_factory=ProjectArtifacts)
    notes: str | None = None


class SpatialGridSummary(StrictModel):
    inferred_columns: int = Field(ge=1)
    margin_left_pct: float = Field(ge=0.0, le=1.0)
    margin_right_pct: float = Field(ge=0.0, le=1.0)
    margin_top_pct: float = Field(ge=0.0, le=1.0)
    margin_bottom_pct: float = Field(ge=0.0, le=1.0)
    alignment_snap_score: float = Field(ge=0.0, le=1.0)
    dominant_alignment: Literal["left", "center", "right", "mixed", "none"] = "none"
    structural_dividers_detected: int = Field(default=0, ge=0)


class SpatialTypographySummary(StrictModel):
    text_block_count: int = Field(ge=0)
    display_height_pct_p50: float | None = Field(default=None, ge=0.0, le=1.0)
    body_height_pct_p50: float | None = Field(default=None, ge=0.0, le=1.0)
    caption_height_pct_p50: float | None = Field(default=None, ge=0.0, le=1.0)
    display_to_caption_ratio: float | None = Field(default=None, ge=0.0)
    median_wcag_contrast: float | None = Field(default=None, ge=1.0, le=21.0)
    min_wcag_contrast: float | None = Field(default=None, ge=1.0, le=21.0)
    small_text_min_wcag_contrast: float | None = Field(default=None, ge=1.0, le=21.0)
    aaa_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    estimated_line_height_ratio: float | None = Field(default=None, ge=0.5, le=4.0)
    max_text_width_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    tilted_text_count: int = Field(ge=0)
    boxed_text_ratio: float = Field(ge=0.0, le=1.0)


class SpatialHierarchySummary(StrictModel):
    mean_competing_signals: float = Field(ge=0.0)
    mean_whitespace_ratio: float = Field(ge=0.0, le=1.0)
    focal_centroid_norm: tuple[float, float]
    safe_zone_violation_rate: float = Field(ge=0.0, le=1.0)
    face_present_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    median_eye_line_y_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_figure_ground_luma_delta: float | None = Field(default=None, ge=0.0, le=255.0)
    dominant_shot_scale: (
        Literal["ews", "ws", "ms", "mcu", "cu", "ecu", "graphic"] | None
    ) = None
    mean_rule_of_thirds_score: float | None = Field(default=None, ge=0.0, le=1.0)
    dominant_lighting_key: (
        Literal["high_key", "normal_key", "low_key", "chiaroscuro"] | None
    ) = None


class SpatialMotionSummary(StrictModel):
    dominant_camera_regime: Literal["static", "slow_drift", "pan", "zoom", "complex"] = "static"
    median_entrance_ms: int | None = Field(default=None, ge=0)
    dominant_easing_class: Literal[
        "snappy_ease_out", "smooth_editorial", "linear", "overshoot", "hard_cut", "unknown"
    ] = "unknown"
    idle_drift_detected: bool = False


class SpatialSummary(StrictModel):
    grid: SpatialGridSummary
    typography: SpatialTypographySummary
    hierarchy: SpatialHierarchySummary
    motion: SpatialMotionSummary


class SpatialElement(StrictModel):
    element_id: str = Field(min_length=1)
    kind: Literal["text", "graphic_container", "subject_foreground", "face"]
    bbox_px: tuple[int, int, int, int]
    bbox_norm: tuple[float, float, float, float]
    hierarchy_tier: int = Field(ge=1, le=3)
    visual_weight: float = Field(ge=0.0, le=1.0)
    text: str | None = None
    text_role: Literal["display", "body", "caption", "micro"] | None = None
    container_style: Literal["boxless", "chip", "card"] | None = None
    tilt_deg: float | None = None
    wcag_contrast: float | None = Field(default=None, ge=1.0, le=21.0)
    fg_hex: str | None = None
    bg_hex: str | None = None
    safe_zone_violation: bool = False


class SpatialFrameAnalysis(StrictModel):
    frame_index: int = Field(ge=0)
    shot_index: int | None = Field(default=None, ge=0)
    timestamp_s: float = Field(ge=0.0)
    blueprint_path: str | None = None
    saliency_centroid_norm: tuple[float, float]
    whitespace_ratio: float = Field(ge=0.0, le=1.0)
    competing_signals: int = Field(default=0, ge=0)
    eye_line_y_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    shot_scale_est: Literal["ews", "ws", "ms", "mcu", "cu", "ecu", "graphic"] | None = None
    headroom_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    figure_ground_luma_delta: float | None = Field(default=None, ge=0.0, le=255.0)
    lighting_key: Literal["high_key", "normal_key", "low_key", "chiaroscuro"] | None = None
    rule_of_thirds_score: float | None = Field(default=None, ge=0.0, le=1.0)
    symmetry_index: float | None = Field(default=None, ge=0.0, le=1.0)
    warm_cool_balance: float | None = Field(default=None, ge=-1.0, le=1.0)
    grid_lines_x_norm: list[float] = Field(default_factory=list)
    grid_lines_y_norm: list[float] = Field(default_factory=list)
    safe_zone_violations: list[str] = Field(default_factory=list)
    elements: list[SpatialElement] = Field(default_factory=list)


class SpatialEntranceTrack(StrictModel):
    track_id: int = Field(ge=0)
    text: str | None = None
    duration_ms: int = Field(ge=0)
    vector: Literal[
        "slide_up", "slide_down", "slide_left", "slide_right", "scale_in", "static_pop"
    ]
    easing_class: Literal[
        "snappy_ease_out", "smooth_editorial", "linear", "overshoot", "hard_cut", "unknown"
    ]
    landed_drift_px: float = Field(ge=0.0)


class SpatialMotionWindow(StrictModel):
    window_index: int = Field(ge=0)
    shot_index: int | None = Field(default=None, ge=0)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)
    camera_regime: Literal["static", "slow_drift", "pan", "zoom", "complex"]
    camera_pan_px_s: float = Field(ge=0.0)
    camera_zoom_pct_s: float
    entrances: list[SpatialEntranceTrack] = Field(default_factory=list)


class SpatialForensicsResult(StrictModel):
    """Contract-validated spatial, structural, typography, hierarchy, and motion forensics."""

    schema_version: Literal["1.0"] = "1.0"
    source_path: str = Field(min_length=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    fps: float = Field(ge=0.0)
    duration_s: float = Field(ge=0.0)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:5", "other"] = "other"
    platform_target_id: str | None = None
    output_dir: str | None = None
    structure_md_path: str | None = None
    summary: SpatialSummary
    frames: list[SpatialFrameAnalysis] = Field(default_factory=list)
    motion_windows: list[SpatialMotionWindow] = Field(default_factory=list)
