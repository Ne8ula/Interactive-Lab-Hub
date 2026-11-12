# Part B audio

Three ElevenLabs voice clips recorded for the reminders on November 10, 2026.
Source filenames identify the voice as Theo Silk - British Deep Sleep & Meditation.
The original MP3s are preserved; WAV copies are used for Pi playback.

| Order | Playback file | Duration |
|---|---|---:|
| 1 | [reminder-01.wav](reminder-01.wav) | 3.00 s |
| 2 | [reminder-02.wav](reminder-02.wav) | 2.35 s |
| 3 | [reminder-03.wav](reminder-03.wav) | 2.27 s |

Voice reminders play 1, 2, 3, then repeat, without overlap. A new run starts at 1.
[beep.wav](beep.wav) contains three 0.3-second tones with 0.15-second gaps,
about 6 dB louder than the original beep. Beep mode triggers after five seconds
of qualifying VIDEO and repeats without cooldown or overlapping playback.
[Source names, conversion details, and hashes](receipt.json).

The Leviathan V2 was used for the recorded beep and voice experiments.
[Phone videos and playback logs](../../README.md#part-b-shelf-watcher-interaction). [Transfer, playback test, and experiment commands](../../docs/part-b-run.md).
