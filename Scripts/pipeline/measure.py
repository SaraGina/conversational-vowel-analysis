"""Acoustic measurement with parselmouth

Word boundaries are refined by silence detection. The vowel is then delimited
spectrally, the way an annotator does it by eye on a spectrogram: the longest
stretch inside the word where F2 is a well-defined resonance (its -3 dB
bandwidth narrower than 400 Hz(=F2_BANDWIDTH_MAX)). F1 and F2 are averaged over the central third
of that stretch.

Each word is assumed to carry a single vowel of interest.
"""
import math
import parselmouth
from parselmouth.praat import call

MARGIN = 0.25

F2_BANDWIDTH_MAX = 400.0
VOWEL_STEP = 0.005


def _measure_token(snd_full, t1, t2, max_formant):
    """Measures one word: finds where it starts and ends, finds the vowel
    inside it, and takes F1, F2 and the durations."""
    total = snd_full.get_total_duration()
    e1, e2 = max(0.0, t1 - MARGIN), min(total, t2 + MARGIN)
    snd = snd_full.extract_part(e1, e2, parselmouth.WindowShape.RECTANGULAR,
                                # preserve times
                                1.0, True)
    # channel 1 only
    if snd.n_channels > 1:
        snd = call(snd, "Extract one channel", 1)

    # refine word boundaries by silence detection
    tg = call(snd, "To TextGrid (silences)", 100, 0.0, -25.0, 0.05, 0.05,
              "", "sound")
    n_int = call(tg, "Get number of intervals", 1)
    tmid0 = (t1 + t2) / 2
    onset, offset, best_ov = t1, t2, 0.0
    for k in range(1, n_int + 1):
        if call(tg, "Get label of interval", 1, k) != "sound":
            continue
        ks = call(tg, "Get start time of interval", 1, k)
        ke = call(tg, "Get end time of interval", 1, k)
        ov = min(ke, t2) - max(ks, t1)
        if ks <= tmid0 <= ke:
            ov += 10
        if ov > best_ov:
            best_ov, onset, offset = ov, ks, ke

    fm = call(snd, "To Formant (burg)", 0.0, 5.0, float(max_formant),
              0.025, 50.0)

    # longest run of frames with a pitch, inside the word
    pitch = call(snd, "To Pitch", 0.0, 75.0, 500.0)
    nfr = call(pitch, "Get number of frames")
    best_len = cur_len = 0
    v1, v2, cur_start = onset, offset, 0.0
    for k in range(1, nfr + 1):
        tk = call(pitch, "Get time from frame number", k)
        f0 = call(pitch, "Get value in frame", k, "Hertz")
        if onset <= tk <= offset and not math.isnan(f0):
            if cur_len == 0:
                cur_start = tk
            cur_len += 1
            if cur_len > best_len:
                best_len, v1, v2 = cur_len, cur_start, tk
        else:
            cur_len = 0

    # shrink that run to where F2's bandwidth stays under F2_BANDWIDTH_MAX;
    # if there is none, keep the voiced run (run_measurement flags it CHECK)
    vowel_ok = False
    if v2 > v1:
        times = [v1 + i * VOWEL_STEP
                 for i in range(int((v2 - v1) / VOWEL_STEP) + 1)]
        best_len = cur_len = 0
        w1 = w2 = cur_start = None
        for tk in times:
            b2_t = call(fm, "Get bandwidth at time", 2, tk, "hertz", "linear")
            good = not math.isnan(b2_t) and b2_t < F2_BANDWIDTH_MAX
            if good:
                if cur_len == 0:
                    cur_start = tk
                cur_len += 1
                if cur_len > best_len:
                    best_len, w1, w2 = cur_len, cur_start, tk
            else:
                cur_len = 0
        if w1 is not None and w2 > w1:
            v1, v2, vowel_ok = w1, w2, True

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


def run_measurement(instances, max_formant_by_speaker):
    """Measures every word, each one on the microphone it was assigned to.

    The formant ceiling comes from the row when the pair declared one, and
    from the speaker otherwise; the value used is written to the row either
    way. Adds the measurements to each row, and marks with CHECK the ones
    that look unreliable - a word or vowel too short, or formants that could
    not be found.
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
            r.update(_measure_token(snd_full, r["tStart"], r["tEnd"], mf))
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
        print(f'{n_chk} instance(s) flagged "CHECK" (very short word/vowel or '
              "missing formants) - verify those manually.")
    print("Acoustic measurement done.")
    return instances
