# Automatic acoustic analysis of dyadic conversation

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23045187.svg)](https://doi.org/10.5281/zenodo.23045187)

An open-source Python pipeline that finds, segments and measures target words
in unscripted two-speaker conversations, replacing manual annotation in Praat.

Given two audio recordings — one microphone per speaker — it transcribes
them, locates every instance of the target words, works out
from the audio alone which speaker produced each one, segments the word and
its vowel, and measures F1, F2 and duration. Cases it is unsure about are
flagged to indicate that a manual check is needed.

It was built for studying native–nonnative phonetic adaptation over English
tense–lax vowel contrasts (*sheep–ship*, *pool–pull*, *dock–duck*), but
nothing in the design is specific to those words or to English.

**This pipeline is for anyone interested in analysing speech from two
separate recordings of the same scene.** No programming or Python skills are
needed, and no previous experience with Praat is assumed. There is a browser
app that starts by double-clicking, and the command-line route is a single
command.

---

## Requirements

- **Python 3.9 or newer.** That is all. Praat itself arrives with the Install
  step below: the `parselmouth` package carries Praat's own code, so the Praat
  application is not needed.
- **Two mono or stereo `.wav` files**, one per speaker's own microphone.
  Both microphones will pick up both speakers; the pipeline handles that.
  If a file is stereo, only the first channel is read - the channels are
  never mixed.
- **Single-syllable target words.** Each word is assumed to carry one vowel
  of interest, and one interval per word is measured. Words with more than
  one syllable are found and timed, but only one of their vowels is measured,
  with no indication of which - so they are outside what this pipeline is
  built for at the moment.
- **A language the recogniser knows.** Set `language:` in the config, or pick
  it in the browser app: `en` (English) or `da` (Danish). The speakers may have
  any first language - that is what the pipeline was built to study - but the
  words being searched for are in the language chosen here.

  Both ship with a pronunciation dictionary, which lets the search also find
  the spellings a recogniser may invent for a target word. To add a third
  language, drop a dictionary in `Input/`, name it in `DICTIONARIES` in
  `Scripts/pipeline/words.py`, and add that language's vowels to `VOWELS` in
  the same file. A language with no dictionary still runs and the measurements
  are unaffected, but the words are then searched exactly as written.

## Install

**macOS / Linux**
```bash
git clone https://github.com/SaraGina/conversational-vowel-analysis.git
cd conversational-vowel-analysis/Scripts
python3 -m venv venv
./venv/bin/pip install -r requirements_asr.txt
```

**Windows**
```
git clone https://github.com/SaraGina/conversational-vowel-analysis.git
cd conversational-vowel-analysis\Scripts
py -m venv venv
venv\Scripts\pip install -r requirements_asr.txt
```

The first run downloads the speech-recognition model (about 1.5 GB, once).

## Run it

### Option A — use the browser app instead of the terminal

Double-click **`Start Dyad App`** in `Scripts/`
(`.command` on macOS, `.bat` on Windows). The first launch installs everything
by itself and then opens the browser. Select the two recordings, adjust the
word list, and press **Run pipeline**.

On macOS the first launch may be blocked: right-click → Open.

### Option B — use the terminal

Copy the contents of `Scripts/example_dyad.yaml` into a new file, save it with a
`.yaml` extension, edit it as shown below, and run:

```bash
cd Scripts
./run_dyad my_dyad.yaml         # macOS / Linux
run_dyad.bat my_dyad.yaml       # Windows
```

A minimal config:

```yaml
speaker_A:
  audio: speakerA.wav           # place in Input/
  label: Confederate
  max_formant: 5000             # ~5000 Hz lower voices, ~5500 Hz higher
speaker_B:
  audio: speakerB.wav
  label: Participant
  max_formant: 5500

pairs:
  sheep_ship: [sheep, ship]
  pool_pull:  [pool, pull]

segment_gap: 45                 # see below
```

**`max_formant`** is the formant ceiling passed to Praat's formant tracker.
It tells the tracker how high in frequency to look for formants, and it has
to match the speaker's vocal tract: roughly 5000 Hz for lower voices and
5500 Hz for higher ones. Set it too low and a formant is missed; too high and
the tracker may split one formant in two. It is the one setting worth checking
per speaker.

**`segment_gap`** groups repeated discussions of the *same* word pair. If a
pair is talked about, then not mentioned for longer than this many seconds,
its next token starts a new segment - so a first discussion of
*sheep/ship* from a later return to it. It does not mark a change of word
pair: each pair is segmented on its own.

Transcription takes roughly 10 minutes per 50 minutes of audio, once per
recording. Everything runs locally; no audio leaves the machine.

## What comes out

Written to `Output/`:


-  `<dyad>_ALL_sets_analysis.xlsx`: one row per measured token
-  `TextGrids_SYSTEM/`:  one Praat TextGrid per speaker, with word and vowel tiers
- `COMPARISON_system_vs_human.xlsx`: colour-coded comparison against a manual annotation, if one is supplied 

The comparison is optional. To use it, point `human_excel` in the config at an
annotation file placed in `Output/`. `Input/manual_annotation_template.xlsx`
shows the columns expected, with a description of each on its second sheet;
an existing annotation sheet works as it is, as long as those columns are
present.

Each row carries `Onset`, `Offset`, word and vowel duration, their ratio, F1
and F2 in both Hz and Bark, the speaker, the trial and segment index, and the
quality flags below.

The linguistic columns (`Pair`, `Vowel`, `Tensity`, `Env`) come from
`Input/master_vocab.csv`, a small table describing each word: its vowel in
IPA, whether it is tense or lax, and its consonant environment (`ʃ_p` for
*sheep*, the `_` standing for the vowel). How a word gets into it depends on
which route is used.

**In the browser app** it is not normally edited by hand. A searched-for word
that is not listed yet is described from the bundled pronunciation dictionary;
the values appear in grey beside the word, ready to be checked before pressing
Run, and are written to the file at that point.

**From the command line** the file is only read, never written. A target word
that is not listed there gets empty `Pair`, `Vowel`, `Tensity` and `Env`
columns, and an unlabelled vowel tier in its TextGrid - the token is still
found and measured. Add a row for each new word before running. Extending the
automatic description to this route as well is planned. 


### Opening `master_vocab.csv`

It is a plain text file: one word per line, with the fields separated by
**commas** and saved as **UTF-8**.

**Any plain text editor opens and edits it directly**, which is the simplest
way to change a row.

**In Excel**, be aware that opening the file may put every field
into column A. Nothing is broken: Excel expects semicolons rather than commas,
depending on the computer's regional settings. **Do not re-save it
that way** - import it with *Data → From Text/CSV*, choosing Comma and UTF-8.

Either way, the pipeline always reads the file correctly.

### Quality flags

The pipeline always signals when it has met something uncertain. Four flags
in the Excel mark the tokens a human should look at. Go to the recording at
the `Onset` given in that row and listen to what is happening, to resolve the
ambiguity that was flagged:

- `CHECK`: word or vowel very short, or formants missing
- `DISAGREE`: the two microphones transcribed different words 
- `VARIANT`: found through a neighbouring spelling; confirm the identity 
- `ECHO?`: the same word from both speakers within 1 second

On a `DISAGREE` row the `Word` column keeps both spellings, and `Vowel`,
`Tensity` and `Env` are taken from whichever of them appears first in the
vocabulary file. That is one of the two candidates, not a decision about which
word was spoken. The acoustic measurements are unaffected, since they are read
from the audio and never from the spelling, and `Pair` is the same for both
members of a minimal pair. An analysis that groups tokens by `Vowel` or
`Tensity` should therefore resolve these rows by listening, or leave them out.

The output is intended to be a **superset** of what a human would annotate:
it might over-generate, and the reviewer might trim.

## How it works

Seven stages, in `Scripts/pipeline/`:


1- Transcription (`transcribe_fw.py`): faster-whisper, word-level timestamps, language forced, channel 1 only if stereo audio file
2- Token search (`words.py`): expands each target word to phonetic-neighbour spellings the recogniser may produce
3- Speaker assignment (`speaker.py`): acoustic, calibration-free; merges the two microphones' copies of the same word
4- Boundary refinement (`measure.py`): Praat silence detection on the word
5- Vowel identification (`measure.py`): longest stretch where F2 is a well-defined resonance (−3 dB bandwidth under 400 Hz)
6- Measurement (`measure.py`): F1/F2 averaged over the central third of the vowel
7- Annotation and output (`analyze.py`): linguistic features, Bark conversion, Excel, TextGrids

Three specific decisions made in the code:

**Speaker assignment is acoustic**
Each token is assigned by comparing the two recordings with each other: at
every moment the pipeline takes the level in microphone A minus the level in
microphone B, and the token goes to whichever of the two was the louder one
while it was spoken.

How much louder is not fixed in advance. The level differences measured
across the whole conversation fall into two groups - one for the stretches
where speaker A is the louder, one for speaker B - and the boundary is placed
between them, separately for each recording. Nothing has to be calibrated
beforehand.

Because both microphones pick up both speakers, the same word reaches the two
transcripts twice, at different levels. Whenever the two copies overlap in
time they are merged into a single token and attributed to one speaker, so a
word said once is not counted twice.

**Target words are expanded phonetically.** A search for the literal target
words alone misses tokens twice over. Recognisers spell the same vowel
inconsistently, and speakers do not always produce the vowel the word calls
for - a non-native speaker aiming at *sheep* may realise it closer to *ship*,
and the recogniser writes down what it hears. Those are exactly the tokens a
study of pronunciation wants to keep, yet they are the ones a literal search
throws away.

Each target word is therefore expanded using the bundled pronunciation
dictionary: a candidate must share the consonant skeleton and differ in
exactly one vowel, and that vowel must lie within distance 1 in the
height/backness plane. So *pole* is kept as a candidate for *pool*/*pull*,
while *peel* is rejected. Tokens found this way carry a `VARIANT` flag, so
the word each one belongs to can be confirmed.

**The measurement engine is Praat, using Parselmouth.**

## Limitations

- **Overlapping speech.** Assignment assumes each talker is loudest in their
  own microphone. When the two levels are close the decision is fragile —
  hence the `ECHO?` flag.
- **Recogniser ceiling.** What the recogniser does not transcribe cannot be
  measured. Neighbour expansion reduces this but does not remove it.
- **Formant ceilings** are set by hand per speaker and affect F1/F2.
- **Vowel detection depends on F2 being trackable.** In noisy recordings, or
  in tokens too short for a stable analysis, no stretch meets the bandwidth
  criterion; the token then falls back to its voiced interval and is marked
  `CHECK` rather than dropped.
- **Validation so far** covers L2 English (Japanese and Mandarin L1 speakers)
  over the /i–ɪ/, /u–ʊ/ and /ɑ–ʌ/ contrasts. Other contrasts and languages
  remain to be tested.
- Target words are chosen, not discovered automatically: in the browser app
  they are typed into the **Minimal pairs** table, and on the command line
  listed under `pairs:` in the `.yaml` config.

## A note on the data

This repository contains **code only**. The conversational recordings this
pipeline was developed on, and the measurement tables derived from them, are
personal data under the GDPR and are not distributed here. There is no sample
audio; the pipeline runs on recordings supplied by the user.

Trying it out takes two `.wav` files from a single conversation, one per
speaker's own microphone, and a list of the words to be measured.

## Versions

`v1.0.0` is the version used for the AVSP 2026 presentation, archived with its
own DOI. Later versions extend the pipeline beyond that study; use the release
that matches the work you are citing.

## Citing

    https://doi.org/10.5281/zenodo.23045187

That DOI always resolves to the most recent version. Each release also
has its own: version 1.0.0 is `10.5281/zenodo.23045188`.

Full author list and the conference abstract are in `CITATION.cff`, which
GitHub's "Cite this repository" button reads.

## License

MIT — see `LICENSE`.

The bundled pronunciation dictionary is redistributed under CC BY 4.0; runtime
dependencies keep their own licenses. See `THIRD_PARTY.md`.
