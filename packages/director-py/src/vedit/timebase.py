"""Exact rational timebase arithmetic aligned with broadcast NTSC and OpenTimelineIO."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

_STANDARD_NTSC_RATES: tuple[tuple[float, int, int], ...] = (
    (23.976, 24000, 1001),
    (29.97, 30000, 1001),
    (47.952, 48000, 1001),
    (59.94, 60000, 1001),
    (119.88, 120000, 1001),
)


@dataclass(frozen=True, slots=True)
class Timebase:
    """Exact rational frame rate (`num / den` frames per second)."""

    num: int
    den: int = 1

    def __post_init__(self) -> None:
        if self.num <= 0 or self.den <= 0:
            raise ValueError(
                f"Timebase num/den must be positive integers, got {self.num}/{self.den}"
            )

    @classmethod
    def from_fps(cls, fps: float | int | Fraction) -> Timebase:
        """Resolve an integer or standard NTSC drop-rate FPS into an exact rational Timebase."""
        if isinstance(fps, Fraction):
            return cls(fps.numerator, fps.denominator)
        fps_f = float(fps)
        if fps_f <= 0:
            raise ValueError(f"FPS must be positive, got {fps}")
        nearest_int = round(fps_f)
        if abs(fps_f - nearest_int) < 1e-4 and nearest_int > 0:
            return cls(int(nearest_int), 1)
        for approx, num, den in _STANDARD_NTSC_RATES:
            if abs(fps_f - approx) < 0.005:
                return cls(num, den)
        frac = Fraction(fps_f).limit_denominator(1001)
        return cls(frac.numerator, frac.denominator)

    @property
    def as_fraction(self) -> Fraction:
        return Fraction(self.num, self.den)

    @property
    def fps_float(self) -> float:
        return self.num / self.den

    @property
    def ffmpeg_rate_str(self) -> str:
        return f"{self.num}/{self.den}"

    @property
    def ffmpeg_timebase_str(self) -> str:
        return f"{self.den}/{self.num}"


@dataclass(frozen=True, slots=True)
class RationalTime:
    """Exact frame-indexed editorial timestamp (`value` frames at `timebase`)."""

    value: int
    timebase: Timebase

    @classmethod
    def from_seconds(cls, seconds: float, timebase: Timebase) -> RationalTime:
        frames = round(Fraction(str(round(seconds, 9))) * timebase.as_fraction)
        return cls(int(frames), timebase)

    def to_fraction(self) -> Fraction:
        return Fraction(self.value, 1) / self.timebase.as_fraction

    def to_seconds(self) -> float:
        return float(self.to_fraction())

    def rescaled_to(self, target: Timebase) -> RationalTime:
        if target == self.timebase:
            return self
        scaled = round(self.to_fraction() * target.as_fraction)
        return RationalTime(int(scaled), target)

    def __add__(self, other: RationalTime) -> RationalTime:
        if self.timebase == other.timebase:
            return RationalTime(self.value + other.value, self.timebase)
        return RationalTime(self.value + other.rescaled_to(self.timebase).value, self.timebase)

    def __sub__(self, other: RationalTime) -> RationalTime:
        if self.timebase == other.timebase:
            return RationalTime(self.value - other.value, self.timebase)
        return RationalTime(self.value - other.rescaled_to(self.timebase).value, self.timebase)


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Exact editorial range `(start, duration)` in rational frames."""

    start: RationalTime
    duration: RationalTime

    @property
    def end(self) -> RationalTime:
        return self.start + self.duration
