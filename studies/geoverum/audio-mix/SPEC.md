# Geoverum Component Study — Audio Mix & EBU R128 Mastering

## Purpose
Verify the complete audio-first directing and mastering DAG on the `15.567s` opening Sulawesi documentary sequence (`1080x1920`, `30fps` CFR, `bt709`):

1. **Speech Hygiene Before STT:** Denoise extracted `48 kHz` voiceover stem (`ffmpeg` highpass + FFT denoise -> `sulawesi_vo_clean.wav`) before word-level transcription (`XaiTranscriptionProvider`, `grok-voice-transcribe-2.0`, Indonesian word timestamps).
2. **Licensed Catalog Integration:** Search and fetch lossless high-rate `WAV` documentary BGM (`c273725d-3f35-3506-9275-d1f6a00011bb`, *"Potential Redemption"*, `90 BPM`, no vocals) and transition/impact SFX (`36d506f7-b031-4bf5-8b50-cad859dde276` whip whoosh peaking at `0.840s`; `d0ba83c3-79f2-4fd0-aa3b-6bf95f741f2a` sub-thud peaking at `1.960s`) via `EpidemicAudioCatalogProvider`.
3. **Speech-Aligned Cut Seams & Synced SFX:** Cut cleanly at `10.167s` inside the `[9.983s, 10.343s]` inter-word silence gap, aligning the optical radial zoom-blur whip midpoint and the `sfx_whip_seam` peak (`10.167s`) on the exact same frame.
4. **Spectral Carving & Two-Pass Mastering:** Attenuate the `2200 Hz` speech presence band (`equalizer` notch + `sidechaincompress` triggered by the voiceover bus), master via two-pass FFmpeg `loudnorm` to **`-14.0 ± 0.5 LUFS`** and **`<= -1.0 dBTP`**, and verify deterministically through `vedit audit`.
