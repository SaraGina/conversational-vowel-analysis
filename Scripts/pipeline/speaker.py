"""Determines which speaker said each word, from the sound alone.

Each speaker wears their own microphone, but both microphones pick up both
speakers. A word is therefore assigned to whichever recording it sounds
louder in.

How it is done:
  1. Measure how loud each recording is, every 50 ms (first channel only).
  2. Keep the moments where someone is speaking - loud enough to stand out
     from that recording's own background - and look at the difference in
     loudness between the two microphones across all of them. Those
     differences fall into two groups, one per speaker; the boundary between
     the groups becomes the threshold for this session.
  3. Assign each word by its own average difference against that threshold.
  4. A word caught by both microphones appears twice. When the two copies
     overlap in time, keep one: the copy from the speaker's own microphone
     if both transcripts agree on the word, or a single row carrying both
     spellings and a DISAGREE flag if they do not.
  5. If the same word comes from both speakers less than a second apart, flag
     both with ECHO? - it may be a genuine repetition, or one utterance whose
     two copies were split between the speakers.
"""
import math
import numpy as np
import soundfile as sf

from .words import clean

FRAME_DUR = 0.050
PAD = 0.05
# double-precision epsilon
EPS = 2.220446049250313e-16


def _loudness_over_time(path, frame_dur=FRAME_DUR):
    """How loud the recording is, moment by moment, in decibels.
    Only the first channel is read, and the file is processed in chunks so
    that a long recording does not have to fit in memory at once.
    """
    info = sf.info(path)
    fs = info.samplerate
    frame = round(frame_dur * fs)
    n_frames = info.frames // frame
    L = np.empty(n_frames)
    block_frames = max(1, round(60 / frame_dur))
    f = 0
    with sf.SoundFile(path) as snd:
        while f < n_frames:
            f_end = min(f + block_frames, n_frames)
            snd.seek(f * frame)
            x = snd.read((f_end - f) * frame, dtype="float64", always_2d=True)[:, 0]
            x = x.reshape(f_end - f, frame)
            L[f:f_end] = 10 * np.log10((x ** 2).mean(axis=1) + EPS)
            f = f_end
    tF = (np.arange(n_frames) + 0.5) * frame_dur
    return L, tF


def _percentile(x, q):
    x = np.sort(x)
    k = max(1, min(len(x), round(q / 100 * len(x))))
    return x[k - 1]


def _split_into_two_groups(d):
    c1, c2 = _percentile(d, 10), _percentile(d, 90)
    for _ in range(100):
        to1 = np.abs(d - c1) < np.abs(d - c2)
        n1, n2 = d[to1].mean(), d[~to1].mean()
        if abs(n1 - c1) < 1e-6 and abs(n2 - c2) < 1e-6:
            break
        c1, c2 = n1, n2
    return (c1, c2) if c1 <= c2 else (c2, c1)


def assign_speaker(matches, audio_a, audio_b, speaker_a, speaker_b):
    import os
    print(f"Analyzing microphone levels: {os.path.basename(audio_a)} ...",
          flush=True)
    LA, tF = _loudness_over_time(audio_a)
    print(f"Analyzing microphone levels: {os.path.basename(audio_b)} ...",
          flush=True)
    LB, _ = _loudness_over_time(audio_b)
    n = min(len(LA), len(LB))
    LA, LB, tF = LA[:n], LB[:n], tF[:n]

    # A - synchronization check: the two mics must share the same clock
    # Cross-correlate the two envelopes (downsampled to 0.5 s) within +/-60 s.
    # Both mics hear both voices, so synchronized recordings peak at lag 0.
    # 10 x 50 ms = 0.5 s steps
    ds = 10
    m = (n // ds) * ds
    a = LA[:m].reshape(-1, ds).mean(axis=1)
    b = LB[:m].reshape(-1, ds).mean(axis=1)
    a = a - a.mean()
    b = b - b.mean()
    # +/-60 s
    max_lag = min(120, len(a) - 1)
    denom = math.sqrt(float((a * a).sum()) * float((b * b).sum())) or 1.0
    corr = np.correlate(a, b, "full") / denom
    mid = len(b) - 1
    window = corr[mid - max_lag: mid + max_lag + 1]
    lag_s = (int(np.argmax(window)) - max_lag) * ds * FRAME_DUR
    peak_corr = float(window.max())
    if abs(lag_s) > 1.0 and peak_corr >= 0.3:
        print(f"WARNING: the two recordings appear to start about "
              f"{lag_s:+.1f} seconds apart. Everything here assumes they "
              "share one timeline, so trim or re-align the two wav files "
              "before trusting the results.")
    if peak_corr < 0.3:
        print(f"WARNING: the two recordings do not sound like the same "
              f"conversation. The speaker assignment cannot be trusted.")

    active = (LA > _percentile(LA, 5) + 10) | (LB > _percentile(LB, 5) + 10)
    d = LA[active] - LB[active]
    if len(d) < 20:
        raise RuntimeError("Too little speech detected to estimate the speaker threshold.")
    c1, c2 = _split_into_two_groups(d)
    thr = (c1 + c2) / 2
    print(f"Speaker separation: cluster centres at {c1:+.1f} and {c2:+.1f} dB "
          f"(threshold {thr:+.1f} dB).")
    if c2 - c1 < 6:
        print(f"WARNING: the two level clusters are only {c2 - c1:.1f} dB apart - "
              "speaker assignment may be unreliable.")

    # B - can the level threshold be trusted? 
    # If not, the fallback below is used instead.
    healthy = peak_corr >= 0.3 and (c2 - c1) >= 6

    # The fallback. It assigns a word by which transcript picked it up, and
    # by levels compared against a 30-second local average of each channel.
    win = max(1, int(30 / FRAME_DUR))
    kern = np.ones(win) / win
    cnt = np.convolve(np.ones(n), kern, "same")
    la = LA - np.convolve(LA, kern, "same") / cnt
    lb = LB - np.convolve(LB, kern, "same") / cnt
    # did the other transcript pick up the same word within a second?
    from collections import defaultdict
    by_word = defaultdict(list)
    for m in matches:
        by_word[clean(m["word"])].append((m["tStart"], m["speaker"]))

    def has_counterpart(m):
        for t, org in by_word[clean(m["word"])]:
            if org != m["speaker"] and abs(t - m["tStart"]) < 1.0:
                return True
        return False

    def classify(use_fallback):
        rows = []
        for m in matches:
            w1, w2 = m["tStart"] - PAD, m["tEnd"] + PAD
            sel = (tF >= w1) & (tF <= w2)
            if not sel.any():
                sel = np.zeros_like(tF, dtype=bool)
                sel[np.argmin(np.abs(tF - m["tStart"]))] = True
            if not use_fallback:
                di = LA[sel].mean() - LB[sel].mean()
                is_a = di > thr
                conf = abs(di - thr)
            elif has_counterpart(m):
                dl = la[sel].mean() - lb[sel].mean()
                is_a = dl > 0
                conf = abs(dl)
            # only one mic's ASR heard it -> its owner
            else:
                is_a = m["speaker"] == speaker_a
                conf = abs(la[sel].mean() - lb[sel].mean())
            rows.append({
                "Speaker": speaker_a if is_a else speaker_b,
                "Word": m["word"], "tStart": m["tStart"], "tEnd": m["tEnd"],
                "AudioFile": audio_a if is_a else audio_b,
                "LevelDiff_dB": conf,
                "HeardAs": m.get("heard_as", ""),
                "fromOwn": m["speaker"] == (speaker_a if is_a else speaker_b),
            })
        return rows

    if not healthy:
        print("NOTE: the two microphone levels cannot be compared directly "
              f"here (recordings match {peak_corr:.2f} out of 1, and the two "
              f"groups of level differences are only {c2 - c1:.1f} dB apart). "
              "Using the transcripts and each channel's local level instead.")
    rows = classify(use_fallback=not healthy)

    # If nearly every word went to one speaker, try the fallback as well and
    # keep whichever result is less one-sided.
    if healthy and len(rows) >= 20:
        n_a = sum(1 for r in rows if r["Speaker"] == speaker_a)
        if min(n_a, len(rows) - n_a) / len(rows) < 0.10:
            rows2 = classify(use_fallback=True)
            n_a2 = sum(1 for r in rows2 if r["Speaker"] == speaker_a)
            if min(n_a2, len(rows2) - n_a2) > min(n_a, len(rows) - n_a):
                print("NOTE: comparing the two microphones sent almost every "
                      f"word to one speaker ({n_a} vs {len(rows) - n_a}). "
                      "Assigned them again using the transcripts and each "
                      "channel's local level instead, which gave a more even "
                      f"split ({n_a2} vs {len(rows2) - n_a2}).")
                rows = rows2

    # C - remove duplicates and flag disagreements 
    # Treating two tokens that overlap in time by more than half of the
    # shorter one as the same word, keeping the copy from the speaker's own
    # microphone, or, if the two transcripts disagree on the word, keeping one
    # row carrying both spellings and a DISAGREE flag.
    rows.sort(key=lambda r: r["tStart"])
    keep = [True] * len(rows)
    for r in rows:
        r["WordCheck"] = ""
    for i in range(1, len(rows)):
        j = i - 1
        while j >= 0 and not keep[j]:
            j -= 1
        if j < 0 or rows[i]["Speaker"] != rows[j]["Speaker"]:
            continue
        same_word = clean(rows[i]["Word"]) == clean(rows[j]["Word"])
        cross = rows[i]["fromOwn"] != rows[j]["fromOwn"]
        ov = min(rows[i]["tEnd"], rows[j]["tEnd"]) - max(rows[i]["tStart"], rows[j]["tStart"])
        dur_min = max(min(rows[i]["tEnd"] - rows[i]["tStart"],
                          rows[j]["tEnd"] - rows[j]["tStart"]), EPS)
        ov_frac = ov / dur_min
        if same_word and ov_frac > 0.5:
            if rows[i]["fromOwn"] and not rows[j]["fromOwn"]:
                keep[j] = False
            else:
                keep[i] = False
        elif not same_word and ov_frac > 0.5 and cross:
            combined = "/".join(sorted([clean(rows[j]["Word"]), clean(rows[i]["Word"])]))
            if rows[j]["fromOwn"]:
                rows[j]["Word"] = combined
                rows[j]["WordCheck"] = "DISAGREE"
                keep[i] = False
            else:
                rows[i]["Word"] = combined
                rows[i]["WordCheck"] = "DISAGREE"
                keep[j] = False
    out = [r for r, k in zip(rows, keep) if k]
    for r in out:
        del r["fromOwn"]

    # D - flag words that may have been counted twice -----------------------------
    # Marking with ECHO? any word that comes from both speakers less than a
    # second apart, without deciding: it may be the interlocutor genuinely
    # repeating it, or one utterance whose two copies escaped the step above.
    comp = [set(clean(w) for w in str(r["Word"]).split("/")) for r in out]
    for r in out:
        r["EchoCheck"] = ""
    for i in range(1, len(out)):
        for j in range(i - 1, -1, -1):
            if out[i]["tStart"] - out[j]["tStart"] > 1.0:
                break
            if out[i]["Speaker"] != out[j]["Speaker"] and comp[i] & comp[j]:
                out[i]["EchoCheck"] = "ECHO?"
                out[j]["EchoCheck"] = "ECHO?"
    n_echo = sum(1 for r in out if r["EchoCheck"])
    if n_echo:
        print(f'{n_echo} token(s) flagged "ECHO?" (same word, both speakers, '
              "<1 s apart): review echo vs leftover crosstalk.")
    n_dis = sum(1 for r in out if r["WordCheck"] == "DISAGREE")
    if n_dis:
        print(f'{n_dis} token(s) where the two transcripts disagree on the word '
              '(flagged "DISAGREE").')
    na = sum(1 for r in out if r["Speaker"] == speaker_a)
    print(f"{len(out)} instance(s) after speaker assignment: "
          f"{na} {speaker_a}, {len(out) - na} {speaker_b}.")
    nb = len(out) - na
    if out and (na == 0 or nb == 0):
        print("WARNING: every token was assigned to the SAME speaker. This "
              "usually means the two wav files are not the two separate, "
              "synchronized microphone recordings of this session (one per "
              "speaker), or one recording has a very different gain/content. "
              "Check the files before trusting the speaker labels.")
    elif len(out) >= 20 and min(na, nb) / len(out) < 0.10:
        print("WARNING: speaker assignment is EXTREMELY unbalanced "
              f"({na} vs {nb}). Do not trust the speaker labels as is.")
    return out
