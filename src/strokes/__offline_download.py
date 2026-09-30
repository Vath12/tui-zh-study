import json
import sys
import urllib.request
from pathlib import Path

# Stroke data for ~9,500 characters from Make Me a Hanzi (Arphic Public License).
# One JSON object per line: {"character", "strokes" (SVG outlines), "medians"},
# with strokes in stroke order.
GRAPHICS_URL = "https://raw.githubusercontent.com/skishore/makemeahanzi/master/graphics.txt"
GRAPHICS_PATH = Path(__file__).parent.parent.parent / "resources" / "strokes" / "graphics.txt"


def download_stroke_data(dest: Path = GRAPHICS_PATH, force: bool = False) -> Path:
    """Download the full stroke data file to `dest` (skipped if it's already
    there, unless force). Returns the path."""
    if dest.exists() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(GRAPHICS_URL, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done, shown = 0, -1
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            if total and done * 100 // total != shown:
                shown = done * 100 // total
                print(f"\rdownloading stroke data: {shown}%", end="", file=sys.stderr)
    print(file=sys.stderr)
    # Make sure it's the file we expect before replacing anything.
    with open(tmp, encoding="utf-8") as f:
        count = sum(1 for line in f if "strokes" in json.loads(line))
    tmp.replace(dest)
    print(f"saved {count} characters to {dest}", file=sys.stderr)
    return dest


if __name__ == "__main__":
    download_stroke_data(force="--force" in sys.argv)
