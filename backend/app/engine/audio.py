"""Audio decoding and frame-level measurement.

Everything the Tier-0 engine knows comes from here, and all of it is genuinely
measured: no provider in this build infers a number it cannot compute from the
samples in front of it.

The client uploads 16 kHz mono 16-bit WAV. That is a deliberate choice for
development — it is exactly what the Tier-1 models want and it needs no codec
on the server — and a deliberate debt: at roughly 32 KB/s it is far too heavy
for a hostel 3G connection (ACC-02/ACC-04). The fix is Opus upload with a
decode at ingest, and it belongs with the Tier-1 work rather than here.
"""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass

import numpy as np

# Frame geometry used by every measurement below. 20 ms windows at a 10 ms hop
# is the standard compromise: short enough to catch a stop consonant, long
# enough that the energy estimate is not noise.
FRAME_MS = 20
HOP_MS = 10

# Digital silence has no dB value. Everything below this is reported as this.
FLOOR_DBFS = -90.0


@dataclass(frozen=True)
class Waveform:
    """Mono float samples in [-1, 1], plus the rate they were taken at."""

    samples: np.ndarray
    sample_rate: int

    @property
    def duration_ms(self) -> int:
        if self.sample_rate <= 0:
            return 0
        return int(round(1000 * len(self.samples) / self.sample_rate))

    def __len__(self) -> int:
        return len(self.samples)


class AudioDecodeError(ValueError):
    """The upload was not audio we can read."""


def decode_wav(data: bytes) -> Waveform:
    """Decode a WAV upload to mono float samples.

    Accepts 8/16/32-bit PCM and 32-bit float, mono or multi-channel. Anything
    else is refused rather than guessed at — a silently misread sample width
    produces plausible numbers from noise, which is the worst failure mode a
    scoring pipeline can have.
    """
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as exc:
        raise AudioDecodeError(f"not a readable WAV file: {exc}") from exc

    if rate <= 0:
        raise AudioDecodeError("WAV declares a sample rate of zero")

    dtype_for = {1: np.uint8, 2: np.int16, 4: np.int32}
    if width not in dtype_for:
        raise AudioDecodeError(f"unsupported sample width: {width * 8}-bit")

    raw = np.frombuffer(frames, dtype=dtype_for[width])
    if raw.size == 0:
        raise AudioDecodeError("WAV contains no audio")

    if width == 1:
        # 8-bit WAV is unsigned, centred on 128.
        samples = (raw.astype(np.float32) - 128.0) / 128.0
    else:
        samples = raw.astype(np.float32) / float(2 ** (8 * width - 1))

    if channels > 1:
        usable = (samples.size // channels) * channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)

    return Waveform(samples=samples.astype(np.float32), sample_rate=rate)


def resample_to(wave_in: Waveform, target_rate: int) -> Waveform:
    """Linear resample. Adequate for envelope measurement, not for a model.

    Tier 1 will want a proper polyphase resampler; every measurement in this
    module works on the energy envelope, which linear interpolation does not
    meaningfully distort.
    """
    if wave_in.sample_rate == target_rate or len(wave_in) == 0:
        return wave_in
    duration = len(wave_in) / wave_in.sample_rate
    n_out = max(1, int(round(duration * target_rate)))
    x_old = np.linspace(0.0, duration, num=len(wave_in), endpoint=False)
    x_new = np.linspace(0.0, duration, num=n_out, endpoint=False)
    return Waveform(
        samples=np.interp(x_new, x_old, wave_in.samples).astype(np.float32),
        sample_rate=target_rate,
    )


def frame_rms_dbfs(wave_in: Waveform) -> tuple[np.ndarray, np.ndarray]:
    """Per-frame loudness in dBFS, and the start time of each frame in ms."""
    frame = max(1, int(wave_in.sample_rate * FRAME_MS / 1000))
    hop = max(1, int(wave_in.sample_rate * HOP_MS / 1000))
    n = len(wave_in)
    if n < frame:
        return np.array([0.0]), np.array([_to_dbfs(_rms(wave_in.samples))])

    starts = np.arange(0, n - frame + 1, hop)
    # One strided view rather than a Python loop — a 40-second response is
    # 4000 frames, and this runs inside a 5-second scoring budget.
    windows = np.lib.stride_tricks.sliding_window_view(wave_in.samples, frame)[::hop]
    rms = np.sqrt(np.maximum(np.mean(windows.astype(np.float64) ** 2, axis=1), 0.0))
    return starts * 1000.0 / wave_in.sample_rate, _to_dbfs_array(rms)


def _rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))


def _to_dbfs(value: float) -> float:
    return FLOOR_DBFS if value <= 1e-9 else max(FLOOR_DBFS, 20.0 * np.log10(value))


def _to_dbfs_array(values: np.ndarray) -> np.ndarray:
    out = np.full(values.shape, FLOOR_DBFS, dtype=np.float64)
    audible = values > 1e-9
    out[audible] = 20.0 * np.log10(values[audible])
    return np.maximum(out, FLOOR_DBFS)


@dataclass(frozen=True)
class SignalQuality:
    """What the recording was like, separately from what was said.

    This exists so the product can tell a student "your microphone cost you
    points, not your English" when that is actually true (DIAG-07) — and,
    just as importantly, so it never says it when it is not.
    """

    peak_dbfs: float
    noise_floor_dbfs: float
    speech_dbfs: float
    snr_db: float
    clipped_ratio: float
    clipped: bool
    silent: bool

    @property
    def usable(self) -> bool:
        return not self.silent and not self.clipped and self.snr_db >= 10.0

    @property
    def verdict(self) -> str:
        if self.silent:
            return "no_speech"
        if self.clipped:
            return "clipped"
        if self.snr_db < 6.0:
            return "very_noisy"
        if self.snr_db < 10.0:
            return "noisy"
        if self.speech_dbfs < -34.0:
            return "quiet"
        return "good"


def signal_quality(wave_in: Waveform) -> SignalQuality:
    _, db = frame_rms_dbfs(wave_in)
    if db.size == 0:
        return SignalQuality(FLOOR_DBFS, FLOOR_DBFS, FLOOR_DBFS, 0.0, 0.0, False, True)

    peak = float(np.max(np.abs(wave_in.samples))) if len(wave_in) else 0.0
    # The quietest tenth of frames is the room; the loudest quarter is the
    # speaker. Percentiles rather than min/max, because one door slam should
    # not redefine the noise floor.
    noise_floor = float(np.percentile(db, 10))
    speech = float(np.percentile(db, 90))
    snr = max(0.0, speech - noise_floor)

    clipped_ratio = float(np.mean(np.abs(wave_in.samples) >= 0.995)) if len(wave_in) else 0.0

    return SignalQuality(
        peak_dbfs=_to_dbfs(peak),
        noise_floor_dbfs=noise_floor,
        speech_dbfs=speech,
        snr_db=snr,
        clipped_ratio=clipped_ratio,
        # A stray sample at full scale is not clipping; a thousandth of the
        # recording pinned to the rail is.
        clipped=clipped_ratio > 0.001,
        silent=speech <= FLOOR_DBFS + 5 or snr < 3.0,
    )


def syllable_nuclei(wave_in: Waveform, speech_floor_dbfs: float) -> list[int]:
    """Approximate syllable positions, in ms.

    Peak-picking on the smoothed energy envelope — the classic De Jong &
    Wempe approach. It is an approximation and is treated as one: it drives a
    speech-rate estimate, never a pronunciation judgement.
    """
    times, db = frame_rms_dbfs(wave_in)
    if db.size < 3:
        return []

    # ~50 ms smoothing: enough to stop a single noisy frame reading as a
    # syllable, short enough to keep two fast ones apart.
    span = max(1, int(50 / HOP_MS))
    kernel = np.ones(span) / span
    smooth = np.convolve(db, kernel, mode="same")

    threshold = speech_floor_dbfs
    min_gap_frames = max(1, int(120 / HOP_MS))
    dip_db = 2.0

    peaks: list[int] = []
    last_index = -min_gap_frames
    for i in range(1, len(smooth) - 1):
        if smooth[i] < threshold:
            continue
        if not (smooth[i] >= smooth[i - 1] and smooth[i] > smooth[i + 1]):
            continue
        if i - last_index < min_gap_frames:
            continue
        # Require a real valley since the previous nucleus, or a plateau reads
        # as several syllables.
        if peaks:
            valley = float(np.min(smooth[last_index:i + 1]))
            if smooth[i] - valley < dip_db:
                continue
        peaks.append(int(times[i]))
        last_index = i

    return peaks
