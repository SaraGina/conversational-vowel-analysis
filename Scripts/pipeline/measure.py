"""Acoustic measurement with parselmouth

The word keeps the start the recogniser gave it. Its end is moved to where the
sound actually stops, by at most WORD_END_EXTENSION, because recognisers tend
to close a word before its last consonant is over.

The vowel is then found inside the recogniser's word the way an annotator
finds it on a spectrogram: start from the loudest voiced moment, which lies
inside the vowel, and widen it to both sides for as long as the sound stays
voiced, stays within VOWEL_RANGE_DB of that peak, and does not turn into a
fricative. Loudness is taken between 300 and 3500 Hz, where the vowel formants
carry their energy, so a following nasal or lateral, which is weak there,
falls outside. A moment counts as a fricative (s, sh, ch, f) when it has more
energy between 4 and 8 kHz, where frication noise lies, than between 250 and
1500 Hz, where a vowel's first formant lies. F1 and F2 are averaged over the
central third of the vowel found.

Each word is assumed to carry a single vowel of interest.
"""
import math
import parselmouth
from parselmouth.praat import call

MARGIN = 0.25

# how much later than the recogniser's end a word may be allowed to end, s
WORD_END_EXTENSION = 0.15

VOWEL_STEP = 0.005
# the band whose loudness is followed to find the vowel, Hz
VOWEL_BAND = (300.0, 3500.0)
# how far below its loudest moment the vowel may fall, dB
VOWEL_RANGE_DB = 9.0
# 4-8 kHz level minus 250-1500 Hz level above which a moment is a fricative,
# dB: 0 means more energy in the frication band than in the vowel band
FRICATIVE_DB = 0.0
# pitch tracking with a low floor and lenient thresholds, so that a soft,
# breathy or creaky vowel still counts as voiced
PITCH_FLOOR = 60.0
SILENCE_THRESHOLD = 0.01
VOICING_THRESHOLD = 0.25


def _band_loudness(snd, lo, hi):
    band = call(snd, "Filter (pass Hann band)", lo, hi, 100)
    return call(band, "To Intensity", 100, 0.0, "yes")


def _find_vowel(snd, start, end):
    """Finds the vowel between start and end. Returns its start, its end, and
    whether it was found on voiced sound."""
    pitch = call(snd, "To Pitch (ac)", 0.0, PITCH_FLOOR, 15, "no",
                 SILENCE_THRESHOLD, VOICING_THRESHOLD, 0.01, 0.35, 0.14,
                 600.0)
    loudness = _band_loudness(snd, *VOWEL_BAND)
    # the fricative test needs the 4-8 kHz band; it is skipped on
    # narrowband audio
    top = min(8000.0, snd.sampling_frequency / 2 - 100)
    hiss = body = None
    if top > 5000:
        hiss = _band_loudness(snd, 4000.0, top)
        body = _band_loudness(snd, 250.0, 1500.0)

    times = [start + i * VOWEL_STEP
             for i in range(int((end - start) / VOWEL_STEP) + 1)]
    level, voiced, vowel_like = [], [], []
    for tk in times:
        db = call(loudness, "Get value at time", tk, "cubic")
        level.append(db)
        f0 = call(pitch, "Get value at time", tk, "Hertz", "linear")
        voiced.append(not math.isnan(f0))
        ok = not math.isnan(db)
        if ok and hiss is not None:
            hi = call(hiss, "Get value at time", tk, "cubic")
            lo = call(body, "Get value at time", tk, "cubic")
            ok = math.isnan(hi) or math.isnan(lo) or hi - lo <= FRICATIVE_DB
        vowel_like.append(ok)

    # anchor on the loudest voiced moment that is not a fricative. If nothing
    # in the word is voiced (whispered, or buried in noise), anchor on the
    # loudest moment that is not a fricative, and report the vowel as not
    # found so that run_measurement flags the row CHECK
    found = True
    usable = [v and w for v, w in zip(voiced, vowel_like)]
    if not any(usable):
        found = False
        usable = vowel_like
    if not any(usable):
        return start, end, False
    k = max((i for i in range(len(times)) if usable[i]),
            key=lambda i: level[i])
    floor = level[k] - VOWEL_RANGE_DB
    a = b = k
    while a > 0 and usable[a - 1] and level[a - 1] >= floor:
        a -= 1
    while b < len(times) - 1 and usable[b + 1] and level[b + 1] >= floor:
        b += 1
    if b == a:
        return start, end, False
    return times[a], times[b], found


def _measure_token(snd_full, t1, t2, max_formant, refine=True):
    """Measures one word: finds where it ends, finds the vowel inside it, and
    takes F1, F2 and the durations.

    With refine off the given boundaries are kept as they are, for a caller
    that brings its own and wants the vowel looked for inside exactly those.
    """
    total = snd_full.get_total_duration()
    e1, e2 = max(0.0, t1 - MARGIN), min(total, t2 + MARGIN)
    snd = snd_full.extract_part(e1, e2, parselmouth.WindowShape.RECTANGULAR,
                                # preserve times
                                1.0, True)
    # channel 1 only
    if snd.n_channels > 1:
        snd = call(snd, "Extract one channel", 1)

    # move the word's end to where its sound stops, found by silence
    # detection: later than the recogniser's end, never earlier, and by at
    # most WORD_END_EXTENSION. The start is kept: in running speech there is
    # rarely a silence before a word, and the sounding stretch around it
    # reaches back into the word before
    onset, offset = t1, t2
    if refine:
        tg = call(snd, "To TextGrid (silences)", 100, 0.0, -25.0, 0.05, 0.05,
                  "", "sound")
        n_int = call(tg, "Get number of intervals", 1)
        tmid0 = (t1 + t2) / 2
        best_ov = 0.0
        sound_end = t2
        for k in range(1, n_int + 1):
            if call(tg, "Get label of interval", 1, k) != "sound":
                continue
            ks = call(tg, "Get start time of interval", 1, k)
            ke = call(tg, "Get end time of interval", 1, k)
            ov = min(ke, t2) - max(ks, t1)
            if ks <= tmid0 <= ke:
                ov += 10
            if ov > best_ov:
                best_ov, sound_end = ov, ke
        offset = max(t2, min(sound_end, t2 + WORD_END_EXTENSION))

    fm = call(snd, "To Formant (burg)", 0.0, 5.0, float(max_formant),
              0.025, 50.0)
    # the vowel is looked for inside the word as given, not in the extension
    v1, v2, vowel_ok = _find_vowel(snd, t1, t2)

    # formants over the central third of the vowel
    ta = v1 + (v2 - v1) / 3
    tb = v2 - (v2 - v1) / 3
    f1 = call(fm, "Get mean", 1, ta, tb, "hertz")
    f2 = call(fm, "Get mean", 2, ta, tb, "hertz")
    return dict(Onset=onset, Offset=offset, WordDuration=offset - onset,
                VowelStart=v1, VowelEnd=v2, VowelDuration=v2 - v1,
                VowelFound=vowel_ok,
                F1=None if math.isnan(f1) else f1,
                F2=None if math.isnan(f2) else f2)


def run_measurement(instances, max_formant_by_speaker, refine=True):
    """Measures every word, each one on the microphone it was assigned to.

    The formant ceiling comes from the row when the pair declared one, and
    from the speaker otherwise; the value used is written to the row either
    way. Adds the measurements to each row, and marks with CHECK the ones
    that look unreliable - a word or vowel too short, formants that could
    not be found, or no voiced vowel in the word.

    With refine off the boundaries given on each row are kept as they are.
    """
    by_audio = {}
    for r in instances:
        by_audio.setdefault(r["AudioFile"], []).append(r)
    print(f"Measuring {len(instances)} instance(s) with parselmouth...")
    total = len(instances)
    done = 0
    for audio, rows in by_audio.items():
        import os
        print(f"  loading audio: {os.path.basename(audio)}", flush=True)
        snd_full = parselmouth.Sound(audio)
        for r in rows:
            # a pair may carry its own ceiling; otherwise the speaker's
            mf = r.get("MaxFormant") or max_formant_by_speaker[str(r["Speaker"])]
            r["MaxFormant"] = float(mf)
            r.update(_measure_token(snd_full, r["tStart"], r["tEnd"], mf,
                                    refine))
            done += 1
            if done % 20 == 0 or done == total:
                print(f"  measured {done}/{total} tokens", flush=True)
    n_chk = 0
    for r in instances:
        suspicious = (r["WordDuration"] < 0.12 or r["VowelDuration"] < 0.04
                      or r["F1"] is None or r["F2"] is None
                      or not r.get("VowelFound", True))
        r["Check"] = "CHECK" if suspicious else ""
        n_chk += suspicious
    if n_chk:
        print(f'{n_chk} instance(s) flagged "CHECK" (very short word/vowel, '
              "missing formants or no voiced vowel) - verify those manually.")
    print("Acoustic measurement done.")
    return instances
