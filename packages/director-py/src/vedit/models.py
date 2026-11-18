"""Typed Pydantic v2 models mirroring cross-runtime JSON Schema contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class PlatformTarget(StrictModel):
    platform_id: str = Field(min_length=1)
    display_name: str | None = None
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:5"]
    width: int = Field(ge=360, le=7680)
    height: int = Field(ge=360, le=7680)
    fps: float
    purpose: Literal["long_form", "short_form", "social_square", "archive_master"] | None = None
    video: VideoMasteringSpec
    audio: AudioMasteringSpec
    safe_zone: SafeZoneMargins
    notes: str | None = None


class TranscriptWord(StrictModel):
    text: str
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)
    speaker: str | int | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_filler: bool = False


class NormalizedTranscript(StrictModel):
    source_hash: str = Field(min_length=8)
    provider: str = Field(min_length=1)
    model: str | None = None
    language: str = Field(min_length=2)
    duration_s: float = Field(ge=0.0)
    text: str
    words: list[TranscriptWord]


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


class TypographyTokens(StrictModel):
    display_family: str
    body_family: str
    caption_case: Literal["sentence", "uppercase", "title", "lowercase"]
    max_words_per_caption_group: int = Field(ge=1, le=12)
    default_caption_band: Literal[
        "lower_third", "center_safe", "upper_safe", "dynamic_away_from_subject"
    ] = "dynamic_away_from_subject"


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
    description: str | None = None
    safe_band: Literal[
        "lower_third", "upper_safe", "center_safe", "dynamic_away_from_subject"
    ] | None = None
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


class AssetRef(StrictModel):
    asset_id: str
    sha256: str = Field(min_length=16)
    kind: Literal["video", "audio_speech", "audio_bgm", "audio_sfx", "image", "font"]
    path: str
    duration_s: float | None = Field(default=None, ge=0.0)
    has_audio: bool = False


class VideoClipOp(StrictModel):
    clip_id: str
    asset_id: str
    timeline_start_s: float = Field(ge=0.0)
    timeline_duration_s: float = Field(gt=0.0)
    source_start_s: float = Field(ge=0.0)
    role: Literal["a_roll", "b_roll", "screen_recording", "cutaway"]
    reframed_to_target: bool = True
    scale: float = Field(ge=0.1, le=4.0, default=1.0)
    transition_in: str | None = None
    subject_safe_boxes: list[BoundingBox] = Field(default_factory=list)


class OverlayCompositionOp(StrictModel):
    overlay_id: str
    kind: Literal[
        "caption_rail", "kinetic_callout", "lower_third", "data_card", "title_scene", "full_scene"
    ]
    timeline_start_s: float = Field(ge=0.0)
    timeline_duration_s: float = Field(gt=0.0)
    transparent: bool = True
    safe_band: Literal[
        "lower_third", "upper_safe", "left_rail", "right_rail", "center_safe", "fullscreen"
    ] = "lower_third"
    template_id: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    props: dict[str, Any] = Field(default_factory=dict)


class AudioTrackOp(StrictModel):
    track_id: str
    asset_id: str
    audio_group: Literal["voiceover", "music", "sfx"]
    timeline_start_s: float = Field(ge=0.0)
    timeline_duration_s: float = Field(gt=0.0)
    source_start_s: float = Field(ge=0.0)
    gain_db: float = Field(ge=-60.0, le=24.0, default=0.0)
    carve_against_group: str | None = None
    carve_strength: float = Field(ge=0.0, le=1.0, default=0.8)
    cleaned_speech_stem: bool = False


class EditPlan(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    job_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    brand_id: str = Field(min_length=1)
    platform_target_id: str = Field(min_length=1)
    render_strategy: Literal["hybrid", "full_hf"]
    duration_s: float = Field(gt=0.0)
    fps: float = Field(gt=0.0)
    width: int = Field(ge=360)
    height: int = Field(ge=360)
    assets: list[AssetRef]
    video_tracks: list[VideoClipOp]
    overlay_compositions: list[OverlayCompositionOp]
    audio_tracks: list[AudioTrackOp]
    verifier_passed: bool = False


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
