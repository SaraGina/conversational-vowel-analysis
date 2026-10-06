# Documentation

Details behind the [README](README.md): the settings, the output columns, the
flags, how the stages work, and what the pipeline does not do.

---

## Requirements in full

- **Python 3.9 or newer.** Praat itself arrives with the Install step: the
  `parselmouth` package carries Praat's own code, so the Praat application is
  not needed.
- **Two mono or stereo `.wav` files**, one per speaker's own microphone. Both
  microphones will pick up both speakers; the pipeline handles that. If a file
  is stereo, only the first channel is read — the channels are never mixed.
- **Single-syllable target words.** Each word is assumed to carry one vowel of
  interest, and one interval per word is measured. Words with more than one
  syllable are found and timed, but only one of their vowels is measured, with
  no indication of which — so they are outside what this pipeline is built for
  at the moment.

## Languages

Set `language:` in the config, or pick it in the browser app: `en` (English),
`da` (Danish) or `ja` (Japanese). The speakers may have any first language —
that is what the pipeline was built to study — but the words being searched for
are in the language chosen here.

English and Danish ship with a pronunciation dictionary, which lets the search
also find the spellings a recogniser may invent for a target word. **Japanese
has no dictionary yet**, so Japanese words are searched exactly as written; the
measurements are unaffected. Japanese is also matched inside longer tokens, as
described under `PARTIAL` below.

To add a language, drop a dictionary in `Input/`, name it in `DICTIONARIES` in
`Scripts/pipeline/words.py`, and add that language's vowels to `VOWELS` in the
same file. A language with no dictionary still runs.

## Config settings

**`max_formant`** is the formant ceiling passed to Praat's formant tracker. It
tells the tracker how high in frequency to look for formants, and it has to
match the speaker's vocal tract: roughly 5000 Hz for lower voices and 5500 Hz
for higher ones. Set it too low and a formant is missed; too high and the
tracker may split one formant in two. It is the one setting worth checking per
speaker.

**A pair's own `max_formant`.** A pair whose vowels need a different analysis
band can declare its own ceiling, and its tokens are then measured with that
value instead of the speaker's:

```yaml
pairs:
  sheep_ship: [sheep, ship]
  pool_pull:
    words: [pool, pull]
    max_formant: 4000
```

Back vowels are often read better below 4500 Hz, because F1 and F2 sit low and
close together and a wide band invites the tracker to put F2 where F3 is. Praat
looks for the same five formants inside whatever band it is given, so lowering
the ceiling changes the model and not only the range.

The ceiling is declared **per pair, never per vowel.** Both members of a pair
share it, so the setting cannot favour one member of the contrast over the
other — which it would if the ceiling followed the vowel the token is thought
to be.

Because the ceiling may differ between pairs, F1 and F2 are not strictly
comparable *across* pairs measured with different values. The `MaxFormant`
column records the value used for every row, so this stays visible rather than
hidden in a settings file.

**`human_excel`** points at a manual annotation placed in `Output/`, to produce
the optional comparison file. `Input/manual_annotation_template.xlsx` shows the
columns expected, with a description of each on its second sheet; an existing
annotation sheet works as it is, as long as those columns are present.

**`segment_gap`** groups repeated discussions of the *same* word pair. If a pair
is talked about, then not mentioned for longer than this many seconds, its next
token starts a new segment — so a first discussion of *sheep/ship* is separated
from a later return to it. It does not mark a change of word pair: each pair is
segmented on its own. The browser app uses a fixed value and does not expose it.

## Measuring words that are already located

A study that has already been annotated by hand does not need the first three
stages. Naming an annotation file in the config reads the word list from it and
starts at the measurement:

```yaml
annotations: my_annotation.xlsx   # in Input/ or Output/

speaker_A:
  audio: recording.wav
  label: Talker 1
  max_formant: 5000
```

`speaker_B` can be left out, so **a single recording is enough** — the two
microphones are only needed to work out who spoke, which the annotation
already says.

Four kinds of annotation are read:

| File | How it is read |
|---|---|
| `.TextGrid` | Every labelled interval of one tier. By default the first interval tier that has any labelled interval — in a TextGrid this pipeline wrote, that is the word tier. `annotation_tier:` in the config names a different one. |
| `.xlsx` | The first sheet that names a word column and an onset column. |
| `.csv` `.tsv` `.txt` | The same, by column name, with the separator detected. |
| Audacity labels | `start`, `end`, `label` per line, with no header. Recognised by the first field being a number. |

For the table-shaped files, the word column may be called `Word`,
`Trial_word`, `Intended_word`, `Target`, `Token`, `Label` or `Text`, and the
onset column `Onset`, `Word_Start`, `Start`, `tStart`, `Begin` or `tmin`. Two
more are used where present: an end (`Offset`, `Word_End`, `End`, `tEnd`,
`tmax`) and a speaker (`Speaker`, `Participant`, `Talker`), whose values must
match the labels in the config.

A row whose end is missing is given a short window from its onset, its
boundaries are found by silence detection inside it, and it is marked
`FROM ONSET` in the `Boundaries` column. A TextGrid tier name is treated as a
hint about the speaker: it is used when it matches a label in the config, and
simply ignored when it does not.

**`pairs` is optional on this route**, since the words come from the
annotation rather than from a search. `Pair`, `Vowel`, `Tensity` and `Env` are
read from `Input/master_vocab.csv` either way, so they do not depend on it.
What declaring the pairs still does here is number the trials, and apply a
pair's own formant ceiling to the words of that pair.

**The boundaries given are kept as they are.** Where an end is supplied, the
vowel is looked for inside exactly that interval and nothing is adjusted
behind the annotator's back.

Every word is then measured a **second** time with the boundaries refined, and
that result is reported alongside in `Onset_refined`, `Offset_refined`,
`F1_refined` and `F2_refined`. These are a check rather than a competing
answer, and most of the time they agree with the first measurement: refinement
only moves a boundary when it finds a silence inside the margin, and an
annotator who cut tightly leaves nothing to move. Where they differ, the
difference is how much the placement of the word boundary moved F1 and F2 —
which is otherwise impossible to tell apart from a disagreement about the
measurement itself.

The measurement is the same code on both routes, so a result obtained this way
and one obtained from the recordings are directly comparable.

What this route does **not** do is find anything. The token list is the
annotation's, so it reports on whether an existing annotation was measured
consistently, never on whether anything was missed. Finding words the
annotator did not mark needs the full route: two recordings, one per speaker's
own microphone, and the list of words to search for.

## The output columns

Each row carries `Onset`, `Offset`, word and vowel duration, their ratio, F1
and F2 in both Hz and Bark, the speaker, the trial and segment index, and the
quality flags.

The linguistic columns (`Pair`, `Vowel`, `Tensity`, `Env`) come from
`Input/master_vocab.csv`, a small table describing each word: its vowel in IPA,
whether it is tense or lax, and its consonant environment (`ʃ_p` for *sheep*,
the `_` standing for the vowel). How a word gets into it depends on which route
is used.

**In the browser app** it is not normally edited by hand. A searched-for word
that is not listed yet is described from the bundled pronunciation dictionary;
the values appear in grey beside the word, ready to be checked before pressing
Run, and are written to the file at that point.

**From the command line** the file is only read, never written. A target word
that is not listed there gets empty `Pair`, `Vowel`, `Tensity` and `Env`
columns, and an unlabelled vowel tier in its TextGrid — the token is still found
and measured. Add a row for each new word before running. Extending the
automatic description to this route as well is planned.

### Opening `master_vocab.csv`

It is a plain text file: one word per line, with the fields separated by
**commas** and saved as **UTF-8**.

**Any plain text editor opens and edits it directly**, which is the simplest way
to change a row.

**In Excel**, be aware that opening the file may put every field into column A.
Nothing is broken: Excel expects semicolons rather than commas, depending on the
computer's regional settings. **Do not re-save it that way** — import it with
*Data → From Text/CSV*, choosing Comma and UTF-8.

Either way, the pipeline always reads the file correctly.

## Quality flags

The pipeline always signals when it has met something uncertain. Five flags in
the Excel mark the tokens a human should look at. Go to the recording at the
`Onset` given in that row and listen to what is happening, to resolve the
ambiguity that was flagged:

- `CHECK`: word or vowel very short, or formants missing
- `DISAGREE`: the two microphones transcribed different words
- `VARIANT`: found through a neighbouring spelling; confirm the identity
- `ECHO?`: the same word from both speakers within 1 second
- `PARTIAL`: the target was found inside a longer token, so the boundaries are
  that token's and need checking

### `PARTIAL` and the `HeardAs` column

In a language written without spaces between words, the recogniser has to
decide for itself where one word ends. A token it reports may hold the target
word and more besides: a search for ねこ can arrive as ねこが, the noun with its
particle attached.

Those hits are kept rather than discarded, because the word really was spoken
and the row sends the reviewer to the right moment in the recording. What
cannot be trusted is the extent: the onset and offset are the longer token's,
so the word duration is too long, and the vowel the measurement lands on need
not be the target's. The `HeardAs` column shows the token as the recogniser
wrote it, next to the target the row is filed under.

Such a row is therefore a pointer to a place in the audio, not a measurement
to be used as it stands. This applies to Japanese; English and Danish are
matched whole, and never produce it.

On a `DISAGREE` row the `Word` column keeps both spellings, and `Vowel`,
`Tensity` and `Env` are taken from whichever of them appears first in the
vocabulary file. That is one of the two candidates, not a decision about which
word was spoken. The acoustic measurements are unaffected, since they are read
from the audio and never from the spelling, and `Pair` is the same for both
members of a minimal pair. An analysis that groups tokens by `Vowel` or
`Tensity` should therefore resolve these rows by listening, or leave them out.

The output is intended to be a **superset** of what a human would annotate: it
might over-generate, and the reviewer might trim.

## How it works

Seven stages, in `Scripts/pipeline/`:

1. **Transcription** (`transcribe_fw.py`): faster-whisper, word-level
   timestamps, language forced, channel 1 only if the file is stereo
2. **Token search** (`words.py`): expands each target word to
   phonetic-neighbour spellings the recogniser may produce
3. **Speaker assignment** (`speaker.py`): acoustic, calibration-free; merges the
   two microphones' copies of the same word
4. **Boundary refinement** (`measure.py`): Praat silence detection on the word
5. **Vowel identification** (`measure.py`): longest stretch where F2 is a
   well-defined resonance (−3 dB bandwidth under 400 Hz)
6. **Measurement** (`measure.py`): F1/F2 averaged over the central third of the
   vowel
7. **Annotation and output** (`analyze.py`): linguistic features, Bark
   conversion, Excel, TextGrids

### Three specific decisions made in the code

**Speaker assignment is acoustic.** Each token is assigned by comparing the two
recordings with each other: at every moment the pipeline takes the level in
microphone A minus the level in microphone B, and the token goes to whichever of
the two was the louder one while it was spoken.

How much louder is not fixed in advance. The level differences measured across
the whole conversation fall into two groups — one for the stretches where
speaker A is the louder, one for speaker B — and the boundary is placed between
them, separately for each recording. Nothing has to be calibrated beforehand.

Because both microphones pick up both speakers, the same word reaches the two
transcripts twice, at different levels. Whenever the two copies overlap in time
they are merged into a single token and attributed to one speaker, so a word
said once is not counted twice.

**Target words are expanded phonetically.** A search for the literal target
words alone misses tokens twice over. Recognisers spell the same vowel
inconsistently, and speakers do not always produce the vowel the word calls for
— a non-native speaker aiming at *sheep* may realise it closer to *ship*, and
the recogniser writes down what it hears. Those are exactly the tokens a study
of pronunciation wants to keep, yet they are the ones a literal search throws
away.

Each target word is therefore expanded using the bundled pronunciation
dictionary: a candidate must share the consonant skeleton and differ in exactly
one vowel, and that vowel must lie within distance 1 in the height/backness
plane. So *pole* is kept as a candidate for *pool*/*pull*, while *peel* is
rejected. Tokens found this way carry a `VARIANT` flag, so the word each one
belongs to can be confirmed.

**The measurement engine is Praat, using Parselmouth.**

## Limitations

- **Overlapping speech.** Assignment assumes each talker is loudest in their own
  microphone. When the two levels are close the decision is fragile — hence the
  `ECHO?` flag.
- **Recogniser ceiling.** What the recogniser does not transcribe cannot be
  measured. Neighbour expansion reduces this but does not remove it.
- **Formant ceilings** are set by hand per speaker and affect F1/F2.
- **Vowel detection depends on F2 being trackable.** In noisy recordings, or in
  tokens too short for a stable analysis, no stretch meets the bandwidth
  criterion; the token then falls back to its voiced interval and is marked
  `CHECK` rather than dropped.
- **Validation so far** covers L2 English (Japanese and Mandarin L1 speakers)
  over the /i–ɪ/, /u–ʊ/ and /ɑ–ʌ/ contrasts. Other contrasts and languages
  remain to be tested. Danish and Japanese are implemented but not yet
  validated against hand annotation.
- **Target words are chosen, not discovered automatically**: in the browser app
  they are typed into the **Minimal pairs** table, and on the command line
  listed under `pairs:` in the `.yaml` config.

## Versions

`v1.0.0` is the version used for the AVSP 2026 presentation, archived with its
own DOI. Later versions extend the pipeline beyond that study; use the release
that matches the work being cited.
