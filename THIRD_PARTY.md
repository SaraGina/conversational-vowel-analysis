# Third-party components

## Bundled data

### English (US) ARPA pronunciation dictionary
You find it on `Input/english_us_arpa.dict`

From the Montreal Forced Aligner pretrained models collection.
Licensed under **CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/), which permits redistribution with attribution.

> McAuliffe, M., Socolof, M., Mihuc, S., Wagner, M., & Sonderegger, M. (2017).
> Montreal Forced Aligner: trainable text-speech alignment using Kaldi.
> *Proceedings of Interspeech 2017*, 498-502.

Model documentation: https://mfa-models.readthedocs.io/

The dictionary is redistributed unmodified. It is included in this repository so that the pipeline runs without the need of a separate Montreal Forced Aligner install.

### Danish pronunciation dictionary
You find it on `Input/danish.dict`

Derived from the **NST pronunciation lexicon for Danish**, produced by Nordisk
sprakteknologi and made available by Spraakbanken at the National Library of
Norway.
Released under **CC0 1.0** (https://creativecommons.org/publicdomain/zero/1.0/),
a public-domain dedication that places no condition on reuse.

> NST uttaleleksikon for dansk. Spraakbanken, Nasjonalbiblioteket.
> https://www.nb.no/sprakbanken/ressurskatalog/oai-nb-no-sbr-26/

Unlike the English one, this file **is modified**: the original has 51
semicolon-separated fields per entry and writes the pronunciation as one
unsegmented SAMPA string. What is shipped here keeps the word and its
phonemes, one entry per line, with the phonemes separated by spaces and the
multi-word entries left out. Syllable and stress marks are dropped; length and
stod are kept in the file and ignored when vowels are compared.

204,027 entries, from the 237,873 of the original.

## Runtime dependencies

**None of these are redistributed here.** `pip` fetches them from PyPI when you run the install step, so each stays under its own license.

- faster-whisper, 1.2.1 
- praat-parselmouth, 0.4.7 
- soundfile, 0.13.1 
- numpy, 2.0.2 
- openpyxl, 3.1.5 
- PyYAML, 6.0.3 
- streamlit, 1.50.0 



## Methods and tools referenced

- Boersma, P., & Weenink, D. Praat: doing phonetics by computer.
  http://www.praat.org/
- Jadoul, Y., Thompson, B., & de Boer, B. (2018). Introducing Parselmouth:
  A Python interface to Praat. *Journal of Phonetics*, 71, 1-15.
- Radford, A., Kim, J. W., Xu, T., Brockman, G., McLeavey, C., & Sutskever, I.
  (2023). Robust speech recognition via large-scale weak supervision.
  *Proceedings of ICML 2023*.
- Traunmuller, H. (1990). Analytical expressions for the tonotopic sensory
  scale. *The Journal of the Acoustical Society of America*, 88(1), 97-100.
 
