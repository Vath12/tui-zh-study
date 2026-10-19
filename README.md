# Disclaimer

Very WIP, project's primary purpose is to study, being well written software is secondary to that goal.

# Description

A terminal app for learning to read and write Chinese characters. Characters
are drawn stroke by stroke right in the terminal, and you're quizzed on your
own wordlists: what a character is, how it's pronounced, how to write it, and
how to read numbers.

## Requirements

- macOS on Apple Silicon. Text to speech and the language model run on
  [MLX](https://github.com/ml-explore/mlx).
- Python 3.13 or newer, and [uv](https://docs.astral.sh/uv/).
- A terminal with a Unicode font. The default "squares" drawing uses the
  Unicode 16 octant characters; if your font doesn't have them, switch to
  "dots" (braille) in Options.

## Setup

```sh
uv sync                     # install the dependencies
uv run python install.py    # download the dictionary, frequency list and stroke data
```

`install.py` downloads each data source once into `.data/cache/` (checked by
sha256), then writes what the app reads into `resources/`. Run it again with
`--force` to download fresh copies. Nothing in `resources/` is committed; it
all comes from here.

## Running

```sh
uv run python -m src.app.proto
```

Press **Tab** for the menu. Every menu row is also a command you can type on
the bottom line, by its name: `/writing`, `/session new Drill`,
`/vocabulary add ~/words.txt`, `/options speed 1s`. `/help` lists them.

### First, add some words

The study modes ask about the words in your wordlists. A wordlist is a `.txt`
file with one word or character per line (anything after it on the line, and
lines starting with `#`, are ignored):

```
你好
谢谢
学生
```

Open **Vocabulary** from the menu and drag the file onto the terminal, or use
`/vocabulary add PATH`. Turn lists on and off with Enter. The app remembers
where each file is, so editing the file updates the list.

### Modes

| Mode | What you do |
|---|---|
| Identify | See characters written stroke by stroke; type what they are. Up and down change the difficulty: one word at a time, or a few together. |
| Writing | See the pinyin; write the characters on paper, press Space to reveal the strokes, then mark yourself right or wrong (y/n). |
| Pinyin | See a word; type its pinyin, with tone marks or numbers (`nǐhǎo`, `ni3 hao3`). |
| Numeracy | See a number in characters (一千零五); type it in digits (1005). Up and down change the difficulty. |
| Dictionary | Type a character or word to see its strokes, readings and meanings. |
| Translation, Mixture | Not ready yet. |

Questions favour characters you haven't seen in a while or keep getting
wrong.

### Sessions

A session keeps your progress, mode and options, saved in `.data/sessions/`.
Make, rename, switch and delete sessions under **Session** in the menu
(deleting asks you to type the session's name). **None** is a session that
isn't saved.

## Other tools

```sh
uv run python -m src.tts.test               # type a line, hear it (Qwen3-TTS)
uv run python -m src.vocabulary.dictionary  # a quick look at the dictionary data
uv run python -m unittest discover _tests   # the tests
```

The first text-to-speech run downloads the model (about 2.5 GB) from Hugging
Face. Spoken clips are cached in `.tts_cache/`.

`run.sh` starts the older quiz app (`python -m src.app`), which predates the
menu-based app above.

## Project layout

```
install.py        downloads and prepares the data
src/
  app/            the app: proto.py (the main screen), modes/, sessions, wordlists
  tui/            a small terminal UI toolkit on blessed: layout, widgets,
                  screens, a diffing renderer, a pixel canvas drawn as text
  stroke/         stroke data and drawing / animating characters
  vocabulary/     Dictionary (CC-CEDICT + character frequency), pinyin, numbers
  tts/            text to speech (Qwen3-TTS via mlx-audio), playback, clip cache
  llm/            a local language model server (mlx-lm), for sentences to come
  util/           loading the TSV files install.py writes
_tests/           unit tests
```

## Data sources

The data isn't included in this repository; `install.py` downloads it from
these sources, under their own terms:

- **CC-CEDICT**, the Chinese-English dictionary, published by
  [MDBG](https://www.mdbg.net/chinese/dictionary?page=cc-cedict), under
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
- **Modern Chinese character frequency list** by Jun Da, Middle Tennessee
  State University
  ([lingua.mtsu.edu](https://lingua.mtsu.edu/chinese-computing/statistics/)).
  See the site for its terms of use.
- **Stroke data** from [Make Me a Hanzi](https://github.com/skishore/makemeahanzi)
  by Shaunak Kishore, derived from fonts by Arphic Technology, under the
  [Arphic Public License](https://github.com/skishore/makemeahanzi/tree/master/APL)
  (see its [COPYING](https://github.com/skishore/makemeahanzi/blob/master/COPYING)).
- **Text to speech**: [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) models
  (Apache-2.0), run through [mlx-audio](https://github.com/Blaizzy/mlx-audio).
