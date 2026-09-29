"""Browser front-end for the dyad pipeline (runs 100% locally).

Started by "Start Dyad App.command" (Mac) / "Start Dyad App.bat" (Windows),
or manually:  ./venv/bin/streamlit run app_streamlit.py

Everything runs on this computer: the page is served from localhost and the
pipeline reads/writes files on the local disk only.
"""
import contextlib
import csv
import io
import os
import re
import traceback

import streamlit as st

st.set_page_config(page_title="Dyad pipeline", page_icon="🎙️", layout="centered")

# --- import the pipeline; if a library is broken, show a friendly page ------
try:
    from pipeline.run import run_config, INPUT, OUTPUT
    from pipeline.words import clean
except Exception:
    st.error("### ⚠️ The pipeline could not start\n"
             "One of the required libraries failed to load. This usually "
             "means the installation did not finish correctly.\n\n"
             "**What to do:** close this window, delete the `venv` folder "
             "inside `Scripts`, and double-click **Start Dyad App** again "
             "(it will reinstall everything). If it still fails, copy the "
             "details below and open an issue on the project repository.")
    st.code(traceback.format_exc())
    st.stop()

DEFAULT_PAIRS = [
    ("sheep_ship", "sheep", "ship"), ("meal_mill", "meal", "mill"),
    ("bean_bin", "bean", "bin"), ("cheek_chick", "cheek", "chick"),
    ("fool_full", "fool", "full"), ("pool_pull", "pool", "pull"),
    ("dock_duck", "dock", "duck"), ("cop_cup", "cop", "cup"),
    ("lock_luck", "lock", "luck"), ("boss_bus", "boss", "bus"),
]


def save_into(uploaded, folder):
    """Store a picked file into the project folder (skip if already there)."""
    dest = os.path.join(folder, uploaded.name)
    data = uploaded.getbuffer()
    if not (os.path.isfile(dest) and os.path.getsize(dest) == len(data)):
        with open(dest, "wb") as f:
            f.write(data)
    return dest


st.title("🎙️ Dyad vowel-analysis pipeline")
st.info("🔒 **Everything happens on this computer.** This page is served by a "
        "small program running locally — there is no server on the internet. "
        "The files you select below are only copied into the project folder "
        "on this machine and are **never uploaded anywhere**.")

CSV_HELP = """`master_vocab.csv` is a plain text file: one word per line, fields
separated by commas, saved as UTF-8. **Any plain text editor opens and edits
it directly**, which is the simplest way to change a row.

**If you prefer Excel**, be aware that opening it may put every field into
column A: Excel expects semicolons rather than commas, depending on the
regional settings of your computer. Do not re-save it that way. Open it like
this instead:

1. Open Excel on an empty sheet
2. Data → From Text/CSV
3. Pick `Input/master_vocab.csv`
4. Set Delimiter to **Comma** and File Origin to **UTF-8**
5. Load, edit, then save back keeping the CSV format

Excel may warn about "possible data loss" when saving. That is normal for any
CSV and nothing is lost: it only means a text file cannot store colours or
formulas. Choose to keep the CSV format."""

MF_HELP = """The formant ceiling tells Praat how high in frequency to look for
formants, and it has to suit the speaker's vocal tract: about 5000 Hz for
lower voices, about 5500 Hz for higher ones.

Praat always fits the same number of formants below this ceiling. Set it too
low and a real formant falls outside, so the ones above it get renumbered and
F1/F2 come out wrong. Set it too high and Praat has more room than there are
formants to fill it, so it tends to invent an extra peak - often splitting one
broad formant into two - which shifts the numbering the other way.

If F1 and F2 look implausible for a speaker, this is the first setting to
change."""


col1, col2 = st.columns(2)
with col1:
    st.subheader("Speaker A (native)")
    up_a = st.file_uploader("Recording — own mic (.wav)", type=["wav"], key="ua")
    label_a = st.text_input("Label", "Confederate")
    mf_a = st.number_input("Formant ceiling (Hz)", 4000, 6000, 5000, step=100,
                           key="fa", help=MF_HELP)
with col2:
    st.subheader("Speaker B (nonnative)")
    up_b = st.file_uploader("Recording — own mic (.wav)", type=["wav"], key="ub")
    label_b = st.text_input("Label", "Participant")
    mf_b = st.number_input("Formant ceiling (Hz)", 4000, 6000, 5500, step=100,
                           key="fb", help=MF_HELP)

# --- suggest linguistic features from the bundled pronunciation dictionary --
# ARPAbet -> IPA. Used only to pre-fill the form; the user always confirms.
ARPA_VOWEL_IPA = {
    "IY": "i", "IH": "\u026a", "EY": "e\u026a", "EH": "\u025b", "AE": "\u00e6",
    "AA": "\u0251", "AO": "\u0254", "OW": "o\u028a", "UH": "\u028a", "UW": "u",
    "AH": "\u028c", "ER": "\u025d", "AY": "a\u026a", "AW": "a\u028a",
    "OY": "\u0254\u026a",
}
ARPA_CONS_IPA = {
    "P": "p", "B": "b", "T": "t", "D": "d", "K": "k", "G": "\u0261",
    "CH": "\u02a7", "JH": "\u02a4", "F": "f", "V": "v", "TH": "\u03b8",
    "DH": "\u00f0", "S": "s", "Z": "z", "SH": "\u0283", "ZH": "\u0292",
    "HH": "h", "M": "m", "N": "n", "NG": "\u014b", "L": "l", "R": "\u0279",
    "W": "w", "Y": "j",
}
# Tense/lax only for the contrasts this convention covers; blank otherwise.
ARPA_TENSITY = {"IY": "tense", "IH": "lax", "UW": "tense", "UH": "lax",
                "AA": "tense", "AH": "lax"}


@st.cache_data(show_spinner=False)
def load_pronunciations():
    """word -> phoneme list, from the dictionary bundled in Input/.

    A word can have several pronunciations; the column after the word is the
    pronunciation probability, so keep the most likely one (a rare reduced
    variant such as "bit" without its final /t/ would otherwise win).
    """
    path = os.path.join(INPUT, "english_us_arpa.dict")
    out = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                tok = line.split()
                if len(tok) < 2:
                    continue
                ph = [re.sub(r"\d", "", p) for p in tok[1:] if p[:1].isalpha()]
                if not ph:
                    continue
                try:
                    prob = float(tok[1])
                except (ValueError, IndexError):
                    prob = 1.0
                w = clean(tok[0])
                best = out.get(w)
                if best is None or (prob, len(ph)) > (best[0], len(best[1])):
                    out[w] = (prob, ph)
    except OSError:
        pass
    return {w: ph for w, (_, ph) in out.items()}


def suggest_features(word):
    """(vowel, tensity, env) guessed from the dictionary; blanks if unknown."""
    ph = load_pronunciations().get(clean(word))
    if not ph:
        return "", "", ""
    idx = next((i for i, p in enumerate(ph) if p in ARPA_VOWEL_IPA), None)
    if idx is None:
        return "", "", ""
    onset = "".join(ARPA_CONS_IPA.get(p, "") for p in ph[:idx])
    coda = "".join(ARPA_CONS_IPA.get(p, "") for p in ph[idx + 1:])
    return (ARPA_VOWEL_IPA[ph[idx]],
            ARPA_TENSITY.get(ph[idx], ""),
            f"{onset}_{coda}")


# --- linguistic features for words the vocabulary does not know yet --------
VOCAB_CSV = os.path.join(INPUT, "master_vocab.csv")
VOCAB_HEADER = ["word", "pair", "env", "vowel", "tensity", "type"]


def known_vocab_words():
    """Cleaned words already present in master_vocab.csv."""
    try:
        with open(VOCAB_CSV, encoding="utf-8") as fh:
            return {clean(r["word"]) for r in csv.DictReader(fh)
                    if r.get("word")}
    except FileNotFoundError:
        return set()


def append_vocab_rows(rows, pairs):
    """Append user-supplied words to master_vocab.csv. Returns how many."""
    filled = [r for r in rows
              if r["word"] and (r["vowel"] or r["tensity"] or r["env"])]
    if not filled:
        return 0
    pair_of = {}
    for name, (w1, w2) in pairs.items():
        pair_of[clean(w1)] = name
        pair_of[clean(w2)] = name
    exists = os.path.isfile(VOCAB_CSV)
    with open(VOCAB_CSV, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=VOCAB_HEADER)
        if not exists:
            writer.writeheader()
        for r in filled:
            writer.writerow({"word": r["word"].strip().lower(),
                             "pair": pair_of.get(clean(r["word"]), ""),
                             "env": r["env"].strip(),
                             "vowel": r["vowel"].strip(),
                             "tensity": r["tensity"].strip(),
                             "type": "minimal"})
    return len(filled)


def resolve_features(word):
    """(vowel, tensity, env, source) for a word.

    Known words take their description from master_vocab.csv; new ones are
    derived from the bundled pronunciation dictionary.
    """
    w = clean(word)
    if not w:
        return "", "", "", ""
    for row in read_vocab_rows():
        if clean(row.get("word", "")) == w:
            return (row.get("vowel", ""), row.get("tensity", ""),
                    row.get("env", ""), "vocab")
    v, t, e = suggest_features(word)
    return v, t, e, ("dict" if v else "none")


def read_vocab_rows():
    try:
        with open(VOCAB_CSV, encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


st.subheader("Minimal pairs")
st.caption("**You choose the words here.** The pipeline will search the two "
           "recordings for exactly these words and measure every instance it "
           "finds. Edit any cell, remove a pair with its 🗑️ button, or add "
           "your own below.")

if "pair_rows" not in st.session_state:
    st.session_state.pair_rows = [
        {"id": i, "name": n, "w1": w1, "w2": w2}
        for i, (n, w1, w2) in enumerate(DEFAULT_PAIRS)]
    st.session_state.next_id = len(DEFAULT_PAIRS)


def add_pair():
    st.session_state.pair_rows.append(
        {"id": st.session_state.next_id, "name": "", "w1": "", "w2": ""})
    st.session_state.next_id += 1


def del_pair(pid):
    st.session_state.pair_rows = [
        r for r in st.session_state.pair_rows if r["id"] != pid]


hc1, hc2, hc3, hc4, hc5, hc6 = st.columns([3, 2.4, 1.6, 2.4, 1.6, 0.8])
hc1.markdown("**Pair name**")
hc2.markdown("**Word 1**")
hc3.markdown("")
hc4.markdown("**Word 2**")
hc5.markdown("")
unresolved = []
for r in st.session_state.pair_rows:
    c1, c2, c3, c4, c5, c6 = st.columns([3, 2.4, 1.6, 2.4, 1.6, 0.8])
    r["name"] = c1.text_input("name", r["name"], key=f"pn{r['id']}",
                              label_visibility="collapsed",
                              placeholder="e.g. sheep_ship")
    r["w1"] = c2.text_input("w1", r["w1"], key=f"pw1{r['id']}",
                            label_visibility="collapsed", placeholder="word 1")
    r["w2"] = c4.text_input("w2", r["w2"], key=f"pw2{r['id']}",
                            label_visibility="collapsed", placeholder="word 2")
    for word, col in ((r["w1"], c3), (r["w2"], c5)):
        if not word.strip():
            continue
        v, t, e, src = resolve_features(word)
        if src == "none":
            col.markdown(f"<span style='color:#c0392b'>? &nbsp;{word}</span>",
                         unsafe_allow_html=True)
            unresolved.append(word.strip())
        else:
            col.markdown(
                f"<span style='color:#888'>{v or '-'} &nbsp;{t or ''}"
                f"<br>{e or ''}</span>", unsafe_allow_html=True)
    c6.button("🗑️", key=f"pd{r['id']}", on_click=del_pair, args=(r["id"],),
              help="Remove this pair")
st.caption(
    "The grey text beside each word is its vowel, tensity and consonant "
    "environment. To set these yourself, edit that word's row in "
    "`Input/master_vocab.csv` and reload this page - words already listed "
    "there are always used as written.",
    help=CSV_HELP)
if unresolved:
    st.warning(
        "No pronunciation found for: **" + ", ".join(unresolved) + "**. "
        "These words will still be searched for and measured, but the Pair, "
        "Vowel, Tensity and Env columns will be empty. Add them by hand to "
        "`Input/master_vocab.csv` if you need those columns.")
st.button("➕ Add a pair", on_click=add_pair)
pairs_rows = [{"pair name": r["name"], "word 1": r["w1"], "word 2": r["w2"]}
              for r in st.session_state.pair_rows]

st.subheader("Options")
up_h = st.file_uploader("Human annotation Excel — optional, enables the "
                        "system-vs-human comparison (.xlsx)", type=["xlsx"])
seg_gap = st.number_input(
    "Segment gap (s)", 5, 300, 45,
    help="Groups each pair's tokens into discussion episodes (the Segment "
         "column): if more than this many seconds pass without any token of "
         "a pair, its next token starts a new segment - e.g. the first "
         "discussion of pool/pull vs a later revisit.")
w1c, w2c = st.columns(2)
win_start = w1c.number_input(
    "Analysis window start (s)", 0, 100000, 0,
    help="Ignore tokens before this time - e.g. the pre-conversation part "
         "that annotators also exclude. Leave 0 to analyze from the start.")
win_end = w2c.number_input(
    "Analysis window end (s)", 0, 100000, 0,
    help="Ignore tokens after this time. Leave 0 to analyze to the end.")

if st.button("▶ Run pipeline", type="primary", use_container_width=True):
    if up_a is None or up_b is None:
        st.error("Please select the two .wav recordings first (one per speaker).")
        st.stop()
    # Two recordings of one conversation normally have the same size, so only
    # the name is checked here; run_config compares the audio itself.
    if up_a.name == up_b.name:
        st.error("**Both speakers point at the same file.** The pipeline "
                 "compares the two microphones against each other, so it "
                 "needs the two separate recordings of one conversation, one "
                 "per speaker.")
        st.stop()
    pairs = {r["pair name"]: [r["word 1"], r["word 2"]]
             for r in pairs_rows
             if r.get("pair name") and r.get("word 1") and r.get("word 2")}
    if not pairs:
        st.error("Define at least one minimal pair.")
        st.stop()

    auto_rows = []
    for _name, (_w1, _w2) in pairs.items():
        for _w in (_w1, _w2):
            if clean(_w) in known_vocab_words():
                continue
            _v, _t, _e, _src = resolve_features(_w)
            if _src == "dict":
                auto_rows.append({"word": _w, "vowel": _v,
                                  "tensity": _t, "env": _e})
    n_added = append_vocab_rows(auto_rows, pairs)
    if n_added:
        st.caption(f"{n_added} new word(s) described from the pronunciation "
                   "dictionary and stored in master_vocab.csv.")

    with st.spinner("Storing the selected files in the project folder "
                    "(on this computer)..."):
        audio_a = save_into(up_a, INPUT)
        audio_b = save_into(up_b, INPUT)
        human_name = save_into(up_h, OUTPUT) if up_h is not None else None

    cfg = {
        "speaker_A": {"audio": os.path.basename(audio_a), "label": label_a,
                      "max_formant": mf_a},
        "speaker_B": {"audio": os.path.basename(audio_b), "label": label_b,
                      "max_formant": mf_b},
        "pairs": pairs, "segment_gap": seg_gap,
        "analysis_start": win_start, "analysis_end": win_end,
    }
    if human_name:
        cfg["human_excel"] = os.path.basename(human_name)

    # --- run in a worker thread and narrate live progress -------------------
    import re
    import threading
    import time

    log = io.StringIO()
    result = {}

    def _work():
        try:
            with contextlib.redirect_stdout(log):
                result["out"] = run_config(cfg)
        except Exception:
            result["err"] = traceback.format_exc()

    def _phase(txt):
        """Map the log so far to (label, progress 0-1)."""
        meas = re.findall(r"measured (\d+)/(\d+) tokens", txt)
        if "extracting human reference" in txt or "Building comparison" in txt:
            return "Building the comparison and TextGrids...", 0.97
        if re.search(r"Done\. \d+ token", txt):
            return "Writing the Excel...", 0.95
        if meas:
            a, b = map(int, meas[-1])
            return f"Measuring tokens with Praat... {a}/{b}", 0.72 + 0.22 * a / b
        if "Measuring" in txt:
            return "Measuring tokens with Praat...", 0.72
        if "Speaker separation" in txt:
            return "Deciding who said each word...", 0.70
        if "Analyzing microphone levels" in txt:
            return "Analyzing the two microphones...", 0.60
        if "Found " in txt:
            return "Searching the target words...", 0.58
        if "Imported" in txt:
            return "Reading the transcripts...", 0.55
        if "Transcribing" in txt:
            n_done = txt.count("Wrote ")
            return (f"Transcribing recording {min(n_done + 1, 2)} of 2 - "
                    "the long step (~10 min per 50-min file)...",
                    0.10 + 0.22 * n_done)
        return "Starting...", 0.03

    worker = threading.Thread(target=_work, daemon=True)
    worker.start()
    bar = st.progress(0.0)
    phase_box = st.empty()
    log_box = st.empty()
    while worker.is_alive():
        txt = log.getvalue()
        label, frac = _phase(txt)
        bar.progress(min(frac, 0.99))
        phase_box.markdown(f"**{label}**")
        tail = "\n".join(txt.replace("\r", "\n").splitlines()[-10:])
        log_box.code(tail or "...", language=None)
        time.sleep(1)
    worker.join()

    if "err" in result:
        bar.progress(1.0)
        phase_box.markdown("**The analysis stopped**")
        st.error("### Something went wrong\n"
                 "Nothing was lost. Please copy the details below and "
                 "open an issue on the project repository.")
        st.code(log.getvalue() + "\n" + result["err"])
        st.stop()
    out_xlsx = result["out"]
    bar.progress(1.0)
    phase_box.markdown("**Finished ✔**")
    log_box.empty()
    with st.expander("Show the full log"):
        st.code(log.getvalue(), language=None)

    st.success("All results were written to the project's **Output** folder. "
               "Download the Excels here:")
    log_txt = log.getvalue()
    if "WARNING: the comparison could not be built" in log_txt:
        st.warning("**The analysis finished and its Excel is valid, but the "
                   "comparison vs the human Excel could not be built** — "
                   "usually the human Excel has a different format than "
                   "expected (see the exact reason in the log at the bottom).")
    if "WARNING: every token was assigned to the SAME speaker" in log_txt:
        st.warning("**All tokens were assigned to the same speaker.** Check "
                   "that the two wav files really are the two separate, "
                   "synchronized microphones of this session (one per "
                   "speaker) — otherwise the speaker labels are not "
                   "trustworthy.")
    if "EXTREMELY unbalanced" in log_txt:
        st.warning("**Speaker assignment is extremely unbalanced** — one "
                   "channel is probably much quieter/noisier than the other, "
                   "so its speaker's tokens get misassigned. Try the "
                   "denoised/level-matched exports of both channels.")
    if "almost UNRELATED" in log_txt:
        st.warning("**The two recordings don't sound like the same room** "
                   "(their loudness patterns are uncorrelated — see the log). "
                   "One of them is probably dominated by constant noise "
                   "(try the denoised export) or the files are not from the "
                   "same session. Speaker assignment cannot be trusted.")
    if "appear to be OFFSET" in log_txt:
        st.warning("**The two recordings appear to be out of sync** (see the "
                   "estimated offset in the log). Trim/synchronize the two "
                   "wav files so they start at the same moment, then re-run.")
    if "annotation appears shifted" in log_txt:
        st.info("**A global time offset was detected between the human "
                "annotation and the audio** — matching was done with "
                "corrected times (see the log and the Summary tab). Worth "
                "checking which timeline the annotation was made on.")
    comp = os.path.join(OUTPUT, "COMPARISON_system_vs_human.xlsx")
    has_comp = human_name and os.path.isfile(comp)
    d1, d2 = st.columns(2)
    with open(out_xlsx, "rb") as f:
        d1.download_button("⬇ Analysis Excel (all tokens)", f,
                           file_name=os.path.basename(out_xlsx),
                           type="primary", use_container_width=True)
    if has_comp:
        with open(comp, "rb") as f:
            d2.download_button("⬇ Comparison vs human (colored)", f,
                               file_name="COMPARISON_system_vs_human.xlsx",
                               type="primary", use_container_width=True)

    if has_comp:
        import openpyxl
        sm = openpyxl.load_workbook(comp)["Summary"]
        rows_sm = [{"Metric": sm.cell(r, 1).value,
                    "Value": sm.cell(r, 2).value}
                   for r in range(2, sm.max_row + 1)]
        st.subheader("System vs human — summary")
        st.table(rows_sm)
        matched = next((r["Value"] for r in rows_sm
                        if "Matched" in str(r["Metric"])), None)
        if str(matched) == "0":
            st.warning("**0 tokens matched the human annotation.** This "
                       "usually means the recordings and the human Excel "
                       "belong to **different sessions** - check that they "
                       "are from the same dyad/conversation.")
