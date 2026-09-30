import pathlib
import json
from dataclasses import dataclass

LOCATION = pathlib.Path(__file__).parent.parent.parent / 'resources' / 'strokes' / 'graphics.txt'

@dataclass
class Zi:
    unicode : str
    strokes : list
    medians : list
    n_strokes : int

class HanziStroke:

    stroke_data : dict[str, Zi] | None = None

    @classmethod
    def _load_lazy(cls):
        if cls.stroke_data is not None:
            return
        data = {}
        with open(LOCATION, 'r', encoding='utf-8') as f:
            for x in f.readlines():
                if not x.strip():
                    continue
                _d = json.loads(x)
                data[_d['character']] = Zi(
                    unicode=_d['character'],
                    strokes=_d['strokes'],
                    medians=_d['medians'],
                    n_strokes=len(_d['strokes']),
                )
        cls.stroke_data = data

    @classmethod
    def get_strokes(cls, char) -> Zi:
        cls._load_lazy()
        if char not in cls.stroke_data:
            raise KeyError(f'no stroke data for {char!r}')
        return cls.stroke_data[char]

if __name__ == "__main__":
    HanziStroke._load_lazy()
    print(HanziStroke.get_strokes('我'))
