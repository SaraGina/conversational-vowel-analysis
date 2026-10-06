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

st.set_page_config(page_title="Dyad pipeline", page_icon="🎙️", layout="wide")

# A wider column than the default, but still narrow enough for the text to be
# read comfortably, and a larger base size than Streamlit's own.
st.markdown("""<style>
html {font-size: 21px;}
.block-container {max-width: 1200px; padding-top: 2.5rem;}
html, body, .stApp, [class*="st-"] {font-size: 21px;}
h1 {font-size: 2.5rem !important;}
h2 {font-size: 1.9rem !important;}
h3 {font-size: 1.5rem !important;}
/* body text, widget labels and the help bubbles */
.stMarkdown p, .stMarkdown li, label p, label div {font-size: 1.1rem !important;}
[data-testid="stCaptionContainer"] p {font-size: 1.0rem !important;}
/* what the user types into */
input, textarea, select,
.stTextInput input, .stNumberInput input, .stSelectbox div {
    font-size: 1.05rem !important;}
.stButton button p, .stDownloadButton button p {font-size: 1.1rem !important;}
[data-testid="stFileUploaderDropzone"] {font-size: 1.05rem !important;}
/* the two ways in read as buttons: filled green for the one in use, faded
   for the other, and none of Streamlit's own underline */
.stTabs [data-baseweb="tab-list"] {gap: 0.7rem; border-bottom: none;}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {display: none !important;}
.stTabs [data-baseweb="tab"] {
    background: #e3efe7;
    border-radius: 12px;
    padding: 0.85rem 1.9rem;
    opacity: 0.55;
    transition: opacity .15s ease, background .15s ease;}
.stTabs [data-baseweb="tab"]:hover {opacity: 0.85;}
.stTabs [data-baseweb="tab"] p {
    font-size: 1.45rem !important; font-weight: 600; color: #2e7d32 !important;}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: #2e7d32; opacity: 1;}
.stTabs [data-baseweb="tab"][aria-selected="true"] p {color: #ffffff !important;}
</style>""", unsafe_allow_html=True)

# --- import the pipeline; if a library is broken, show a friendly page ------
try:
    from pipeline.run import run_config, INPUT, OUTPUT
    from pipeline.words import clean, LANGUAGES, DICTIONARIES
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

# three examples, one per contrast, meant to be replaced rather than kept
DEFAULT_PAIRS = [
    ("sheep_ship", "sheep", "ship"),
    ("pool_pull", "pool", "pull"),
    ("dock_duck", "dock", "duck"),
]


def save_into(uploaded, folder):
    """Store a picked file into the project folder (skip if already there)."""
    dest = os.path.join(folder, uploaded.name)
    data = uploaded.getbuffer()
    if not (os.path.isfile(dest) and os.path.getsize(dest) == len(data)):
        with open(dest, "wb") as f:
            f.write(data)
    return dest


st.title("Dyad vowel-analysis pipeline")
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


st.caption("Fields marked :green[*] are required. Everything else is optional.")

tab_full, tab_ann = st.tabs([
    "① Start from the recordings",
    "② Start from an annotation"])

with tab_full:
    st.markdown(
        "**Finds the words itself.** Give the two recordings - one per "
        "speaker's own microphone - and the words to look for. It transcribes "
        "them, finds every instance, works out who said each one, and measures "
        "it. This is the route that can find tokens an annotation missed.")

    with st.container(border=True):
        st.subheader("Speakers")
        lang_col, _ = st.columns([1, 2])
        with lang_col:
            language = st.selectbox(
                # English first: it is the default, and the only one with a dictionary
                "Language of the recordings", list(LANGUAGES),
                format_func=lambda c: LANGUAGES[c],
                help="What the recogniser is told to transcribe. A language without a "
                     "pronunciation dictionary still runs, but the search then uses "
                     "the words exactly as written.")
        if not os.path.isfile(os.path.join(INPUT, DICTIONARIES.get(language, ""))):
            st.info(f"No pronunciation dictionary for {LANGUAGES[language]} yet \u2014 "
                    "words will be searched exactly as written, without the "
                    "spelling-variant recovery.")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Speaker A** · native")
            up_a = st.file_uploader("Recording — own mic (.wav) :green[*]",
                                    type=["wav"], key="ua")
            label_a = st.text_input("Label :green[*]", "Confederate")
            mf_a = st.number_input("Formant ceiling (Hz)", 4000, 6000, 5000, step=100,
                                   key="fa", help=MF_HELP)
        with col2:
            st.markdown("**Speaker B** · nonnative")
            up_b = st.file_uploader("Recording — own mic (.wav) :green[*]",
                                    type=["wav"], key="ub")
            label_b = st.text_input("Label :green[*]", "Participant")
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
    def load_pronunciations(language):
        """word -> phoneme list, from the dictionary for this language.

        The language is an argument so that the cache is not shared between
        languages.

        A word can have several pronunciations; the column after the word is the
        pronunciation probability, so keep the most likely one (a rare reduced
        variant such as "bit" without its final /t/ would otherwise win).
        """
        path = os.path.join(INPUT, DICTIONARIES.get(language, ""))
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
        ph = load_pronunciations(language).get(clean(word))
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


    _PN = ("pair name", "pair_name", "pair", "name", "set")
    _W1 = ("word 1", "word_1", "word1", "w1", "first", "intended_word")
    _W2 = ("word 2", "word_2", "word2", "w2", "second")
    _MF = ("ceiling", "max_formant", "max formant", "formant ceiling", "maxformant")


    def _pick(header, names):
        for n in names:
            if n in header:
                return header[n]
        return None


    def read_pair_list(upload):
        """(name, word 1, word 2, ceiling) rows from an uploaded word list.

        A .yaml is read from its pairs: block, in either of the forms the config
        accepts. A .xlsx or .csv is read by its column names; where it has no
        column of pair names, each name is made from its two words.
        """
        data = upload.getvalue()
        name = upload.name.lower()
        rows = []

        if name.endswith((".yaml", ".yml")):
            import yaml
            doc = yaml.safe_load(io.BytesIO(data)) or {}
            pairs = doc.get("pairs") if isinstance(doc, dict) else None
            if pairs is None and isinstance(doc, dict):
                pairs = doc
            for pname, spec in (pairs or {}).items():
                if isinstance(spec, dict):
                    words = [str(w) for w in (spec.get("words") or [])]
                    mf = spec.get("max_formant")
                else:
                    words, mf = [str(w) for w in (spec or [])], None
                if len(words) == 2:
                    rows.append((str(pname), words[0], words[1],
                                 "" if mf is None else str(mf)))
            return rows

        if name.endswith(".csv"):
            import csv
            table = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        else:
            import openpyxl
            ws = openpyxl.load_workbook(io.BytesIO(data), data_only=True).worksheets[0]
            table = [list(r) for r in ws.iter_rows(values_only=True)]
        if not table:
            return rows

        header = {}
        for i, cell in enumerate(table[0]):
            header.setdefault(str(cell or "").strip().lower(), i)
        i1, i2 = _pick(header, _W1), _pick(header, _W2)
        if i1 is None or i2 is None:
            return rows
        ip, im = _pick(header, _PN), _pick(header, _MF)
        for raw in table[1:]:
            get = lambda i: ("" if i is None or i >= len(raw) or raw[i] is None
                             else str(raw[i]).strip())
            w1, w2 = get(i1), get(i2)
            if not w1 or not w2:
                continue
            rows.append((get(ip) or f"{w1}_{w2}", w1, w2, get(im)))
        return rows


    with st.container(border=True):
        st.subheader("Minimal pairs :green[*]")
        st.caption("**You choose the words here.** The pipeline will search the two "
                   "recordings for exactly these words and measure every instance it "
                   "finds. Edit any cell, remove a pair with its 🗑️ button, or add "
                   "your own below.")

        up_list = st.file_uploader(
            "Load a word list instead of typing it — optional (.yaml, .xlsx, .csv)",
            type=["yaml", "yml", "xlsx", "csv"], key="pairs_file",
            help="A pipeline .yaml is read from its pairs: block. A sheet needs a "
                 "column for each of the two words, and may add a pair name and a "
                 "ceiling. Loading a list replaces whatever is in the table.")

        if "pair_rows" not in st.session_state:
            st.session_state.pair_rows = [
                {"id": i, "name": n, "w1": w1, "w2": w2, "mf": ""}
                for i, (n, w1, w2) in enumerate(DEFAULT_PAIRS)]
            st.session_state.next_id = len(DEFAULT_PAIRS)

        # a loaded list replaces the table; the stamp keeps one upload from
        # being read again on every rerun
        if up_list is not None:
            stamp = (up_list.name, len(up_list.getvalue()))
            if st.session_state.get("pairs_from") != stamp:
                loaded = read_pair_list(up_list)
                st.session_state.pairs_from = stamp
                st.session_state.pairs_msg = (
                    f"Loaded {len(loaded)} pair(s) from {up_list.name}."
                    if loaded else
                    f"No word pairs could be read from {up_list.name}. A sheet "
                    "needs a column for each of the two words; a .yaml needs a "
                    "pairs: block.")
                if loaded:
                    start = st.session_state.next_id
                    st.session_state.pair_rows = [
                        {"id": start + i, "name": n, "w1": w1, "w2": w2, "mf": mf}
                        for i, (n, w1, w2, mf) in enumerate(loaded)]
                    st.session_state.next_id = start + len(loaded)
                    st.rerun()
            msg = st.session_state.get("pairs_msg")
            if msg:
                (st.success if msg.startswith("Loaded") else st.warning)(msg)


        def add_pair():
            st.session_state.pair_rows.append(
                {"id": st.session_state.next_id, "name": "", "w1": "", "w2": "",
                 "mf": ""})
            st.session_state.next_id += 1


        def del_pair(pid):
            st.session_state.pair_rows = [
                r for r in st.session_state.pair_rows if r["id"] != pid]


        hc1, hc2, hc3, hc4, hc5, hc6, hc7 = st.columns(
            [3, 2.4, 1.6, 2.4, 1.6, 1.4, 0.8])
        hc1.markdown("**Pair name**")
        hc2.markdown("**Word 1**")
        hc3.markdown("")
        hc4.markdown("**Word 2**")
        hc5.markdown("")
        hc6.markdown("**Ceiling**")
        unresolved = []
        for r in st.session_state.pair_rows:
            c1, c2, c3, c4, c5, c6, c7 = st.columns(
                [3, 2.4, 1.6, 2.4, 1.6, 1.4, 0.8])
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
            r["mf"] = c6.text_input("mf", r.get("mf", ""), key=f"pm{r['id']}",
                                    label_visibility="collapsed",
                                    placeholder="auto")
            c7.button("🗑️", key=f"pd{r['id']}", on_click=del_pair, args=(r["id"],),
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
        st.caption(
            "**Ceiling** is the formant ceiling in Hz for this pair alone. Left on "
            "*auto* it uses the speaker's value above. Set it for a pair whose "
            "vowels need a different analysis band - back vowels are often read "
            "better below 4500 Hz. Praat looks for the same five formants inside "
            "whatever band it is given, so lowering the ceiling changes the model "
            "and not only the range. The value used is written beside every "
            "measurement in the output.")
        st.button("➕ Add a pair", on_click=add_pair)
        st.caption(
            "These three are examples. Replace them with the words of your own "
            "study, or load a list above - the pipeline searches for exactly what "
            "is listed here.")
        pairs_rows = [{"pair name": r["name"], "word 1": r["w1"], "word 2": r["w2"],
                       "ceiling": r.get("mf", "")}
                      for r in st.session_state.pair_rows]


    def filled_pairs():
        """The rows of the table that name a pair and both of its words."""
        return [r for r in pairs_rows
                if r.get("pair name") and r.get("word 1") and r.get("word 2")]


    def pairs_for_config(rows):
        """The table as the config wants it, carrying any pair's own ceiling.

        Both ways of starting a run read the same table through here.
        """
        out = {}
        for r in rows:
            mf = str(r.get("ceiling", "")).strip()
            if not mf:
                out[r["pair name"]] = [r["word 1"], r["word 2"]]
                continue
            try:
                out[r["pair name"]] = {"words": [r["word 1"], r["word 2"]],
                                       "max_formant": float(mf)}
            except ValueError:
                st.error(f"The ceiling for '{r['pair name']}' is not a number.")
                st.stop()
        return out

    with st.container(border=True):
        st.subheader("Options")
        uh_col, _ = st.columns([1, 1])
        with uh_col:
            up_h = st.file_uploader("Human annotation Excel — optional, enables the "
                                    "system-vs-human comparison (.xlsx)",
                                    type=["xlsx"])
        # Groups each pair's tokens into discussion episodes (the Segment column): if
        # more than this many seconds pass without any token of a pair, its next token
        # starts a new segment. Not asked for here; the config file can override it.
        SEGMENT_GAP = 45
        w1c, w2c = st.columns(2)
        win_start = w1c.number_input(
            "Analysis window start (s)", 0, 100000, 0,
            help="Ignore tokens before this time - e.g. the pre-conversation part "
                 "that annotators also exclude. Leave 0 to analyze from the start.")
        win_end = w2c.number_input(
            "Analysis window end (s)", 0, 100000, 0,
            help="Ignore tokens after this time. Leave 0 to analyze to the end.")

    st.caption(
        "Already have the words located by hand? The second tab measures them "
        "straight from your annotation. Stay on this tab if you would also "
        "like to know whether the recordings hold tokens your annotation does "
        "not list.")

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
        valid = filled_pairs()
        if not valid:
            st.error("Define at least one minimal pair.")
            st.stop()
        # words alone, for the vocabulary work below
        pairs = {r["pair name"]: [r["word 1"], r["word 2"]] for r in valid}
        cfg_pairs = pairs_for_config(valid)

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
            "pairs": cfg_pairs, "segment_gap": SEGMENT_GAP, "language": language,
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



with tab_ann:
    st.markdown(
        "**Measures words that are already located.** If the words have been "
        "found by hand already, give the annotation and the recording: the "
        "vowel is measured inside exactly the boundaries it gives. No "
        "transcription, no searching, and **one recording is enough**.")

    # --- second way in: measure words an annotation already locates -------------
    with st.container(border=True):
        st.subheader("Measure an existing annotation")
        st.caption(
            "If the words have already been located by hand, the first three "
            "stages are not needed. Give **one** recording and the annotation, and "
            "every word in it is measured inside the boundaries it gives - one "
            "recording is enough here, because the annotation already says who "
            "spoke.")
        ac1, ac2 = st.columns(2)
        with ac1:
            ann_audio = st.file_uploader("Recording (.wav) :green[*]",
                                         type=["wav"], key="ann_audio")
            ann_label = st.text_input("Speaker label :green[*]", "Talker 1",
                                      key="ann_label")
        with ac2:
            ann_xlsx = st.file_uploader(
                "Annotation :green[*]",
                type=["TextGrid", "xlsx", "csv", "tsv", "txt"],
                key="ann_xlsx",
                help="A Praat TextGrid, a spreadsheet, a delimited text file "
                     "with a header row, or an Audacity label file.")
            ann_mf = st.number_input("Formant ceiling (Hz)", 3000, 7000, 5000,
                                     step=100, key="ann_mf")
        st.caption(
            "**A Praat TextGrid works as it is** - the first tier with labelled "
            "intervals is read. A sheet or a text file needs a column with the "
            "word and one with its onset in seconds; an Audacity label file is "
            "read as it is. An end is used where it is there; where it is not, "
            "the boundaries are found by silence detection and the row is marked "
            "FROM ONSET. Every word is also measured a second time with the "
            "boundaries refined, reported beside the first as a check - the two "
            "usually agree, and where they do not, the difference is how much the "
            "boundary placement moved F1 and F2.")
        st.caption(
            "**The minimal pairs above are not needed for this.** The words come "
            "from the annotation, and the Pair, Vowel, Tensity and Env columns are "
            "read from `Input/master_vocab.csv` either way. What the table still "
            "does on this route is number the trials, and apply a pair's own "
            "formant ceiling to its words.")
        st.info(
            "**This measures the words the annotation lists, and only those.** It "
            "says whether an existing annotation was measured consistently. To "
            "find words the annotation does not list, use the first tab "
            "instead - searching the recordings and working out who spoke is "
            "what needs the two separate microphones, which is why this route "
            "can run on a single recording and that one cannot.")

        if st.button("Measure the annotated words", use_container_width=True,
                     key="ann_run"):
            if ann_audio is None or ann_xlsx is None:
                st.error("Both a recording and an annotation file are needed.")
                st.stop()
            ann_log = io.StringIO()
            with st.spinner("Measuring with Praat..."):
                a_path = save_into(ann_audio, INPUT)
                x_path = save_into(ann_xlsx, INPUT)
                try:
                    with contextlib.redirect_stdout(ann_log):
                        ann_cfg = {
                            "annotations": os.path.basename(x_path),
                            "speaker_A": {"audio": os.path.basename(a_path),
                                          "label": ann_label,
                                          "max_formant": ann_mf}}
                        # the table above is optional here, and used when filled in
                        if filled_pairs():
                            ann_cfg["pairs"] = pairs_for_config(filled_pairs())
                        ann_out = run_config(ann_cfg)
                except Exception as exc:
                    st.error(f"The measurement stopped: {exc}")
                    st.code(ann_log.getvalue() or traceback.format_exc(),
                            language=None)
                    st.stop()
            st.success(f"Measured -> {os.path.basename(ann_out)}")
            st.code(ann_log.getvalue(), language=None)
            with open(ann_out, "rb") as fh:
                st.download_button("Download the measurements", fh.read(),
                                   file_name=os.path.basename(ann_out),
                                   use_container_width=True, key="ann_dl")
