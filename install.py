'''Download the data the app needs into .data/cache/, once, and parse it
into resources/.

    uv run python install.py            # fetch anything not cached yet, then parse
    uv run python install.py --force    # fetch again even if it is

Each Source in SOURCES knows where its cached copy is (`path`), whether it's
there and intact (`cached`), how to read it (`text()`; for a zip, the file
inside it), and how to turn it into rows for `output`:

    from install import SOURCES
    text = SOURCES['cedict'].text()

Downloads are kept exactly as they came (bytes), next to a .json file with
their sha256, so a damaged copy is noticed and fetched again.

Parsed files are tab separated, one row per line, with the md5 of the rows
on the first line.
'''
import argparse
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / '.data' / 'cache'
RESOURCE_DIR = ROOT / 'resources'
TIMEOUT = 120  # seconds

Rows = list[tuple[str, ...]]


@dataclass
class Source:
    '''Something to download, and what to make of it.

      url, file  where it comes from, and its name in CACHE_DIR
      member     for a zip, the file inside it that's wanted
      encoding   of the text (in the zip member, for a zip)
      check      check(text): what's wrong with a download, or None if it
                 looks right, so a bad one (an error page) isn't cached
      output     where it goes in RESOURCE_DIR
      parse      parse(text): the rows to write to `output`; with no parse,
                 the text is copied there as it is'''
    url : str
    file : str
    member : str | None = None
    encoding : str = 'utf-8'
    check : Callable[[str], str | None] = lambda text: None
    parse : Callable[[str], Rows] | None = None
    output : str | None = None

    @property
    def path(self) -> Path:
        '''Where the cached copy is.'''
        return CACHE_DIR / self.file

    @property
    def meta_path(self) -> Path:
        return CACHE_DIR / (self.file + '.json')

    @property
    def output_path(self) -> Path | None:
        return RESOURCE_DIR / self.output if self.output else None

    @property
    def cached(self) -> bool:
        '''Whether it's been downloaded and the copy is intact.'''
        try:
            meta = json.loads(self.meta_path.read_text(encoding='utf-8'))
            return hashlib.sha256(self.path.read_bytes()).hexdigest() == meta['sha256']
        except (OSError, ValueError, KeyError):
            return False

    def decode(self, body : bytes) -> str:
        '''The text in a download (from inside the zip, for a zip).'''
        if self.member:
            try:
                body = zipfile.ZipFile(io.BytesIO(body)).read(self.member)
            except (zipfile.BadZipFile, KeyError) as e:
                raise RuntimeError(f'not a zip with {self.member} in it: {e}')
        try:
            return body.decode(self.encoding)
        except UnicodeDecodeError as e:
            raise RuntimeError(f'can\'t read it as {self.encoding}: {e}')

    def text(self) -> str:
        '''The cached copy, decoded. FileNotFoundError if it isn't downloaded (run install.py).'''
        if not self.cached:
            raise FileNotFoundError(f'{self.file} isn\'t downloaded (or the copy is damaged): run install.py')
        return self.decode(self.path.read_bytes())

    def fetch(self):
        '''Download it, check it, and cache it.'''
        request = urllib.request.Request(self.url, headers={'User-Agent': 'chinese-practice-installer'})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
        if problem := self.check(self.decode(body)):
            raise RuntimeError(f'the download doesn\'t look right ({problem}), not caching it')
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + '.tmp')
        tmp.write_bytes(body)
        tmp.replace(self.path)   # all or nothing, so a failed run can't leave half a file
        self.meta_path.write_text(json.dumps({
            'url': self.url, 'sha256': hashlib.sha256(body).hexdigest(),
            'fetched': datetime.now().isoformat(timespec='seconds'),
        }, indent=2) + '\n', encoding='utf-8')

    def write_output(self) -> str:
        '''Write `output` from the cached copy: parsed, the md5 of the rows
        then the rows, tab separated; else the text as it is. The file is only
        rewritten if it would change. Returns what was done, for printing.'''
        text = self.text()
        if self.parse:
            rows = self.parse(text)
            out = '\n'.join('\t'.join(row) for row in rows)
            text, what = hashlib.md5(out.encode('utf-8')).hexdigest() + '\n' + out, f'{len(rows):,} rows'
        else:
            what = f'{len(text.splitlines()):,} lines'
        where = self.output_path.relative_to(ROOT)
        if self.output_path.exists() and self.output_path.read_text(encoding='utf-8') == text:
            return f'{where} is up to date ({what})'
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(text, encoding='utf-8')
        return f'wrote {what} to {where}'


# Jun Da's character frequency list

def has_frequency_list(text : str) -> str | None:
    rows = re.findall(r'^\d+\t\S\t\d+\t', text, re.M)
    return None if len(rows) >= 1000 else f'only {len(rows)} rows in the list'


def parse_char_freq(text : str) -> Rows:
    '''A few /* comment */ lines, then one row per line: rank, character,
    count, cumulative %, pinyin, English. Kept: character, count, pinyin
    (tone numbers, readings split by /), English.'''
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.startswith('/*'):
            continue
        _, char, count, _, pinyin, english = line.split('\t')
        rows.append((char, count, pinyin, english))
    return rows


# CC-CEDICT

CEDICT_LINE = re.compile(r'^(\S+) (\S+) \[([^\]]*)\] /(.*)/\s*$')


def has_cedict_entries(text : str) -> str | None:
    entries = sum(1 for line in text.splitlines() if CEDICT_LINE.match(line))
    return None if entries >= 10000 else f'only {entries} entries'


def parse_cedict(text : str) -> Rows:
    '''# comment lines, then one entry per line:
    "Traditional Simplified [pin1 yin1] /definition/definition/".
    Kept per entry: simplified, traditional, pinyin (tone numbers, syllables
    split by spaces, as in CEDICT: u: for ü, 5 for the neutral tone, capitals
    for proper nouns), and the definitions, split by /. A word with more than
    one reading (好 hao3, hao4) has a row for each.'''
    rows = []
    for line in text.splitlines():
        if line.startswith('#') or not line.strip():
            continue
        m = CEDICT_LINE.match(line)
        if m is None:
            raise ValueError(f'not a CC-CEDICT entry: {line!r}')
        traditional, simplified, pinyin, definitions = m.groups()
        rows.append((simplified, traditional, pinyin, definitions))
    return rows


# Make Me a Hanzi's stroke data

def has_stroke_data(text : str) -> str | None:
    '''One JSON object per line: {"character", "strokes" (SVG paths), "medians"}.'''
    lines = [line for line in text.splitlines() if line.strip()]
    try:
        bad = next((line for line in lines if not {'character', 'strokes', 'medians'} <= json.loads(line).keys()), None)
    except ValueError as e:
        return f'a line isn\'t JSON: {e}'
    if bad is not None:
        return f'a line is missing character/strokes/medians: {bad[:60]}'
    return None if len(lines) >= 9000 else f'only {len(lines)} characters'


SOURCES = {
    # Modern Chinese character frequency list (Jun Da, MTSU), as the plain
    # text download (CharFreq.txt). It's GB2312; gb18030 is a superset of it.
    'char_freq': Source('https://lingua.mtsu.edu/chinese-computing/statistics/char/download.php?Which=MO',
                        'CharFreq_MO.txt', encoding='gb18030', check=has_frequency_list,
                        parse=parse_char_freq, output='jun-da_frequency.tsv'),
    # CC-CEDICT (MDBG), a Chinese-English dictionary. CC BY-SA 4.0.
    'cedict': Source('https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.zip',
                     'cedict_1_0_ts_utf-8_mdbg.zip', member='cedict_ts.u8', check=has_cedict_entries,
                     parse=parse_cedict, output='cc-cedict.tsv'),
    # Make Me a Hanzi (Shaunak Kishore): stroke outlines and medians for each
    # character, used to draw them (src/stroke). Copied as it is.
    'strokes': Source('https://raw.githubusercontent.com/skishore/makemeahanzi/master/graphics.txt',
                      'makemeahanzi_graphics.txt', check=has_stroke_data, output='strokes/graphics.txt'),
}


def main() -> int:
    parser = argparse.ArgumentParser(description='Download the data the app needs into .data/cache/, and parse it.')
    parser.add_argument('--force', action='store_true', help='download again even if already cached')
    args = parser.parse_args()
    failed = False
    for name, source in SOURCES.items():
        where = source.path.relative_to(ROOT)
        if source.cached and not args.force:
            print(f'{name}: already cached ({where})')
        else:
            print(f'{name}: downloading {source.url}')
            try:
                source.fetch()
                print(f'{name}: cached {where} ({source.path.stat().st_size:,} bytes)')
            except (OSError, RuntimeError) as e:
                print(f'{name}: failed: {e}', file=sys.stderr)
                failed = True
                continue
        if source.output:
            print(f'{name}: {source.write_output()}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
