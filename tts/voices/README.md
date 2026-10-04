# Reference voices

Chatterbox clones the timbre and accent of a short reference recording. One file per language: `<lang>.wav`
(10–15 s of clean, calm speech, mono). Without a file the model's default English speaker is used.
`pl.wav` is a copy of `candidates/glys.wav`; to switch voices copy another candidate over it (no restart needed).

| File | Reader | Source (LibriVox, 128 kbps) | Licence |
| --- | --- | --- | --- |
| `candidates/glys.wav` (= `pl.wav`) | Glys | *W nieznane światy* (W. Umiński), ch. 1, 1:28.5–1:42.1 — https://archive.org/details/wnieznaneswiaty_2608_librivox | Public Domain Mark 1.0 |
| `candidates/nina_brown.wav` | Nina Brown | *Rękopis znaleziony w Saragossie* (J. Potocki), ch. 1, 1:13.9–1:27.1 — https://archive.org/details/rkopis_znaleziony_saragossie_1501_librivox | Public Domain Mark 1.0 |
| `candidates/nela_reinfuss.wav` | Nela Reinfuss | *Balladyna* (J. Słowacki), ch. 1, 1:13.2–1:26.6 — https://archive.org/details/balladyna_2012_librivox | Public Domain Mark 1.0 |
| `candidates/piotr_nater.wav` | Piotr Nater | *Mój stosunek do Kościoła* (J. Baudouin de Courtenay), 64 kbps — https://archive.org/details/mojstosunekdokosciola_2511_librivox | Public Domain Mark 1.0 |

Chosen by measurement over 3 minutes of each reader (noise floor in pauses, speech-to-noise ratio, syllable
rate, pitch spread): Glys had a clean recording (noise floor -75 dB vs -57 dB for the first sample), a
moderate pace and natural, not monotone intonation (pitch spread 4.1 semitones). Clips were cut pause to
pause, high-passed (70 Hz) and loudness-normalised (-18 LUFS).
