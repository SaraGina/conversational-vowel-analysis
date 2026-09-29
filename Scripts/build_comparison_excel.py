#!/usr/bin/env python3
"""Colored comparison Excel: system output vs human annotation.

Matches tokens by (Speaker, Pair, Onset +/- TOL). Main sheet: one row per
system token (minimal-pair tokens only). For F1, F2, F1_Bark, F2_Bark the
human-value cell is colored:
- green  = values agree            (relative diff <= 3% Hz / 0.20 Bark)
- orange = numerically similar     (<= 12% Hz / 0.60 Bark)
- red    = different value
If a system token has NO human match -> whole row PINK.
Human tokens with no system match -> sheet 'Only_in_human'.

Usage: python3 build_comparison_excel.py SYSTEM.xlsx HUMAN.xlsx OUT.xlsx
"""
import sys, os, re
import openpyxl
from openpyxl.styles import Font, PatternFill

# how far apart two tokens may be and still count as the same one, seconds
TOL = 2.5
# relative diff for Hz
GREEN_REL, ORANGE_REL = 0.03, 0.12
# absolute diff for Bark
GREEN_ABS, ORANGE_ABS = 0.20, 0.60
clean = lambda s: re.sub(r"[^a-z']", "", str(s).lower().strip())

FILL = {"green": PatternFill("solid", fgColor="C6EFCE"),
        "orange": PatternFill("solid", fgColor="FFEB9C"),
        # strong red (clearly != pink)
        "red":   PatternFill("solid", fgColor="F8696B"),
        # pale pink
        "pink":  PatternFill("solid", fgColor="FBDDF0"),
        "blue":  PatternFill("solid", fgColor="DDEBF7"),
        "purple": PatternFill("solid", fgColor="E4D7F5"),
        "head":  PatternFill("solid", fgColor="D9D9D9")}
BOLD = Font(bold=True)

def _read_sheet(path):
    ws = openpyxl.load_workbook(path, data_only=True).active
    hdr = [c.value for c in ws[1]]
    ix = {n: i for i, n in enumerate(hdr)}
    rows = [[ws.cell(r, c + 1).value for c in range(len(hdr))]
            for r in range(2, ws.max_row + 1)
            if ws.cell(r, ix["Onset"] + 1).value is not None]
    return ix, rows

def _to_number(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def _agreement_colour(sysv, humv, kind):
    a, b = _to_number(sysv), _to_number(humv)
    if a is None or b is None: return None
    d = abs(a - b)
    if kind == "bark":
        return "green" if d <= GREEN_ABS else "orange" if d <= ORANGE_ABS else "red"
    rel = d / max(abs(b), 1e-9)
    return "green" if rel <= GREEN_REL else "orange" if rel <= ORANGE_REL else "red"

if len(sys.argv) != 4:
    sys.exit("Usage: python3 build_comparison_excel.py "
             "SYSTEM.xlsx HUMAN.xlsx OUT.xlsx")
for path in sys.argv[1:3]:
    if not os.path.isfile(path):
        sys.exit(f"ERROR: '{path}' not found.")

six, S = _read_sheet(sys.argv[1])
hix, H = _read_sheet(sys.argv[2])
out = sys.argv[3]

def _pair_name(row, ix):  return clean(row[ix["Pair"]]) if "Pair" in ix else ""
# minimal-pair tokens only (non-empty Pair) on both sides
Sm = [r for r in S if _pair_name(r, six)]
Hm = [r for r in H if _pair_name(r, hix)]

# greedy matching by (Speaker, Pair, onset +/- TOL)
# speaker compared case-insensitively: annotations mix "participant"/"Participant"
spk = lambda r, ix: str(r[ix["Speaker"]]).strip().lower()

def _match_tokens(offset=0.0, smap=None):
    """Match system tokens to human tokens whose Onset is shifted by
    `offset` seconds; `smap` maps human speaker labels to system labels.
    Returns (pairs, h_used)."""
    smap = smap or {}
    h_used = [False] * len(Hm)
    # (sys_row, hum_row|None)
    pairs = []
    for sr in Sm:
        ss, sp, so = spk(sr, six), _pair_name(sr, six), _to_number(sr[six["Onset"]])
        best, bestdt = -1, TOL + 1
        for j, hr in enumerate(Hm):
            if h_used[j]: continue
            hs = smap.get(spk(hr, hix), spk(hr, hix))
            if hs == ss and _pair_name(hr, hix) == sp:
                dt = abs(_to_number(hr[hix["Onset"]]) + offset - so)
                if dt <= TOL and dt < bestdt:
                    best, bestdt = j, dt
        if best >= 0:
            h_used[best] = True
            pairs.append((sr, Hm[best]))
        else:
            pairs.append((sr, None))
    return pairs, h_used

# Speaker labels may follow different conventions (e.g. "English speaker" /
# "Mandarin speaker" vs "Confederate" / "Participant"). If the label sets
# differ, try both possible assignments and keep the one that matches more.
speaker_map = {}
sys_sp = sorted({spk(sr, six) for sr in Sm})
hum_sp = sorted({spk(hr, hix) for hr in Hm})
if set(sys_sp) != set(hum_sp) and len(sys_sp) == 2 and len(hum_sp) == 2:
    cand_a = dict(zip(hum_sp, sys_sp))
    cand_b = dict(zip(hum_sp, sys_sp[::-1]))
    n_a = sum(1 for _, h in _match_tokens(0.0, cand_a)[0] if h)
    n_b = sum(1 for _, h in _match_tokens(0.0, cand_b)[0] if h)
    speaker_map = cand_a if n_a >= n_b else cand_b
    print("NOTE: the annotation uses different speaker labels than the "
          "system; matched them automatically: "
          + ", ".join(f"'{k}' -> '{v}'" for k, v in speaker_map.items())
          + f" ({max(n_a, n_b)} vs {min(n_a, n_b)} matches for the two "
            "possible assignments).")

pairs, h_used = _match_tokens(0.0, speaker_map)
time_offset = 0.0

# If almost nothing matched, the annotation may use a different time origin
# than the audio (e.g. annotated on a differently-trimmed file). Estimate a
# global offset from same-pair token time differences and retry.
n0 = sum(1 for _, h in pairs if h)
if Hm and Sm and n0 < 0.2 * len(Hm):
    diffs = []
    for hr in Hm:
        for sr in Sm:
            if _pair_name(sr, six) == _pair_name(hr, hix):
                diffs.append(_to_number(sr[six["Onset"]]) - _to_number(hr[hix["Onset"]]))
    if diffs:
        import collections
        binned = collections.Counter(round(d) for d in diffs)
        peak, count = binned.most_common(1)[0]
        if count >= max(5, 0.2 * len(Hm)) and abs(peak) > TOL:
            fine = [d for d in diffs if abs(d - peak) <= 3]
            # median around peak
            cand = sorted(fine)[len(fine) // 2]
            pairs2, h_used2 = _match_tokens(cand, speaker_map)
            n2 = sum(1 for _, h in pairs2 if h)
            if n2 > max(n0 * 2, 0.3 * len(Hm)):
                pairs, h_used, time_offset = pairs2, h_used2, cand
                print(f"NOTE: the human annotation appears shifted by "
                      f"{cand:+.1f} s relative to the audio; matching used "
                      f"the corrected times ({n2} matches instead of {n0}). "
                      "Check which timeline the annotation was made on.")

only_human = [Hm[j] for j in range(len(Hm)) if not h_used[j]]

# Human tokens that lie beyond the last system token often mean the audio
# file is shorter than the session the annotation covers (truncated export).
sys_end = max(_to_number(sr[six["Onset"]]) for sr in Sm) if Sm else 0
beyond = [hr for hr in only_human
          if _to_number(hr[hix["Onset"]]) + time_offset > sys_end + 60]
if beyond:
    hum_end = max(_to_number(hr[hix["Onset"]]) for hr in Hm)
    print(f"WARNING: {len(beyond)} human token(s) lie AFTER the last token "
          f"the system found (annotation reaches {hum_end:.0f} s but the "
          f"system's last token is at {sys_end:.0f} s). The audio file may "
          "be truncated / shorter than the session that was annotated.")

METRICS = [("F1", "hz"), ("F2", "hz"), ("F1_Bark", "bark"), ("F2_Bark", "bark")]
cols = ["MatchStatus", "EchoCheck", "Pair", "Speaker", "Word_sys", "Word_hum",
        "Onset_sys", "Onset_hum"]
for m, _ in METRICS: cols += [f"{m}_sys", f"{m}_hum"]
# number of identifying columns
NID = 8

wb = openpyxl.Workbook()
ws = wb.active; ws.title = "Comparison"
ws.append(cols)
for c in ws[1]: c.font = BOLD; c.fill = FILL["head"]

iEcho = six.get("EchoCheck")
for sr, hr in pairs:
    match = "matched" if hr else "system-only"
    echo = str(sr[iEcho] or "") if iEcho is not None else ""
    if echo.lower() in ("none", "nan"): echo = ""
    base = [match, echo, sr[six["Pair"]], sr[six["Speaker"]], sr[six["Word"]],
            (hr[hix["Word"]] if hr else ""),
            round(_to_number(sr[six["Onset"]]), 2),
            (round(_to_number(hr[hix["Onset"]]), 2) if hr else "")]
    vals = []
    stats = []
    for m, kind in METRICS:
        sv = sr[six[m]] if m in six else None
        hv = hr[hix[m]] if (hr and m in hix) else None
        sv = round(_to_number(sv), 2) if _to_number(sv) is not None else sv
        hv = round(_to_number(hv), 2) if _to_number(hv) is not None else hv
        vals += [sv, hv]
        stats.append(_agreement_colour(sv, hv, kind) if hr else None)
    ws.append(base + vals)
    row = ws.max_row
    # system-only token -> pink row
    if hr is None:
        for c in range(1, len(cols) + 1):
            ws.cell(row, c).fill = FILL["pink"]
    else:
        for k, (m, _) in enumerate(METRICS):
            st = stats[k]
            # color the _hum cell
            if st:
                # position of {m}_hum (1-based)
                col = NID + 2 * k + 2
                ws.cell(row, col).fill = FILL[st]
    # highlight speaker-ambiguity flag
    if echo:
        ws.cell(row, 2).fill = FILL["purple"]

# append the human-only tokens at the end (light blue), so all three
# MatchStatus values are visible in this single sheet
for hr in [Hm[j] for j in range(len(Hm)) if not h_used[j]]:
    row_vals = ["human-only", "", hr[hix["Pair"]], hr[hix["Speaker"]], "",
                hr[hix["Word"]], "", round(_to_number(hr[hix["Onset"]]), 2)]
    for m, _ in METRICS:
        hv = hr[hix[m]] if m in hix else None
        row_vals += ["", round(_to_number(hv), 2) if _to_number(hv) is not None else hv]
    ws.append(row_vals)
    for c in range(1, len(cols) + 1):
        ws.cell(ws.max_row, c).fill = FILL["blue"]

# summary sheet: token counts
n_match = sum(1 for _, h in pairs if h)
n_variant = sum(1 for sr, _ in pairs
                if "LabelReview" in six and str(sr[six["LabelReview"]]).upper() == "VARIANT")
sm = wb.create_sheet("Summary")
sm.append(["Metric", "Value"])
for c in sm[1]: c.font = BOLD; c.fill = FILL["head"]
if speaker_map:
    sm.append(["NOTE: speaker labels mapped automatically",
               ", ".join(f"{k} -> {v}" for k, v in speaker_map.items())])
if time_offset:
    sm.append(["DETECTED TIME OFFSET (annotation vs audio, s)",
               f"{time_offset:+.1f} - matching used corrected times; "
               "check which timeline the annotation was made on"])
if beyond:
    sm.append(["Human tokens beyond the end of the audio "
               "(wav possibly truncated)", len(beyond)])
for k, v in [("System tokens (minimal-pair)", len(Sm)),
             ("  of which VARIANT (neighbour spelling, confirm label)", n_variant),
             ("Human tokens (minimal-pair)", len(Hm)),
             ("Matched system <-> human", n_match),
             ("Human-token recall", f"{100*n_match/max(len(Hm),1):.0f}%  ({n_match}/{len(Hm)})"),
             ("System-only (no human match, pink rows)", len(Sm) - n_match),
             ("Human-only (not found by system, see 'Only_in_human')", len(Hm) - n_match)]:
    sm.append([k, v])
sm.column_dimensions["A"].width = 52

# sheet with human-only tokens + automatic diagnosis of WHY each was missed
wh = wb.create_sheet("Only_in_human")
hhdr = ["Pair", "Speaker", "Word", "Onset", "F1", "F2", "F1_Bark", "F2_Bark",
        "Diagnosis", "Nearby_system_tokens"]
wh.append(hhdr)
for c in wh[1]: c.font = BOLD; c.fill = FILL["head"]
for hr in only_human:
    hp, hs, ho = _pair_name(hr, hix), spk(hr, hix), _to_number(hr[hix["Onset"]])
    hw = clean(hr[hix["Word"]])
    near, other_spk, burst, crosspair = [], False, False, False
    for i, sr in enumerate(Sm):
        so = _to_number(sr[six["Onset"]])
        if abs(so - ho) > 3.0:
            continue
        st = "matched" if pairs[i][1] is not None else "system-only"
        w, spp = str(sr[six["Word"]]), _pair_name(sr, six)
        if spp == hp:
            near.append(f"{w} {sr[six['Speaker']]} @{so:.1f} ({st})")
            if spk(sr, six) != hs:
                other_spk = True
            elif st == "matched":
                burst = True
        elif abs(so - ho) <= 1.0 and "/" in w and any(
                c == hw or c.startswith(hw) or hw.startswith(c)
                for c in (clean(x) for x in w.split("/"))):
            crosspair = True
            near.append(f"{w} {sr[six['Speaker']]} @{so:.1f} (cross-pair: {spp})")
    if crosspair:
        diag = "exists as a cross-pair DISAGREE token (word merged across pairs) - relabel by hand"
    elif other_spk:
        diag = "detected but assigned to the other speaker (echo / crosstalk ambiguity)"
    elif burst:
        diag = "nearby repetition matched to another human token; this production missed (burst)"
    elif near:
        diag = "same-pair token nearby but could not be paired - review"
    else:
        diag = "no system token nearby: ASR miss"
    wh.append([hr[hix[c]] if c in hix else "" for c in hhdr[:8]]
              + [diag, "; ".join(near)])
wh.column_dimensions["I"].width = 60
wh.column_dimensions["J"].width = 60

# legend (separate sheet AND embedded at the top-right of the main sheet)
leg = [("green", "green", "values agree (diff <= 3% Hz / 0.20 Bark)"),
       ("orange", "orange", "numerically similar (<= 12% Hz / 0.60 Bark)"),
       ("red", "red", "different value"),
       ("pink", "pink", "system-only: token with no human match (whole row)"),
       ("blue", "blue", "human-only: annotated by human, not found by system (whole row)"),
       ("purple", "purple", "ECHO?: same word, both speakers, <1 s apart - review speaker ambiguity")]
wl = wb.create_sheet("Legend")
for name, key, desc in leg:
    wl.append([name, desc]); wl.cell(wl.max_row, 1).fill = FILL[key]
# embedded copy: two columns to the right of the data on the Comparison sheet
# legend color column (1-based)
lc = len(cols) + 2
ws.cell(1, lc, "LEGEND").font = BOLD
for i, (name, key, desc) in enumerate(leg, start=2):
    ws.cell(i, lc, name).fill = FILL[key]
    ws.cell(i, lc + 1, desc)

wb.save(out)
n_match = sum(1 for _, h in pairs if h)
print(f"System (minimal-pair): {len(Sm)} | Human (minimal-pair): {len(Hm)}")
print(f"Matched: {n_match} | system-only (pink): {len(Sm)-n_match} | human-only: {len(only_human)}")
print(f"-> {out}")
