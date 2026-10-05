import hashlib
import io

import polars as pl

def load_hashed_tsv(path, schema : dict[str, pl.DataType] | list[str] | None = None) -> pl.DataFrame:
    '''A TSV with the md5 of its rows on the first line (as install.py
    writes them), as a DataFrame, after checking the hash. schema names the
    columns, with their types if it's a dict (others are strings); without
    it they're column_1, column_2, ...'''
    with open(path, 'rb') as f:
        content = f.read().decode('utf-8').split('\n')
    l0 = content[0]
    data = '\n'.join(content[1:])
    h = hashlib.md5(data.encode('utf-8')).hexdigest()
    if not l0 == h:
        raise Exception(f'corrupted data in: {path}\n\t* checkhash mismatch\n\t{h} =/= {l0}')
    names = list(schema) if schema is not None else None
    return pl.read_csv(
        io.StringIO(data), separator='\t', has_header=False, new_columns=names,
        quote_char=None,   # the text has " in it (CEDICT: as in 忘不了 "cannot forget")
        schema_overrides=schema if isinstance(schema, dict) else None,
        infer_schema=False if not isinstance(schema, dict) else True,
    )


if __name__ == "__main__":
    import pathlib

    CEDICT_SCHEMA = {'simplified': pl.String, 'traditional': pl.String, 'pinyin': pl.String, 'definitions': pl.String}
    JUNDA_SCHEMA = {'char': pl.String, 'count': pl.Int64, 'pinyin': pl.String, 'english': pl.String}

    rdir = pathlib.Path(__file__).parent.parent.parent / 'resources'
    dat = load_hashed_tsv(rdir / "cc-cedict.tsv", CEDICT_SCHEMA)
    jd = load_hashed_tsv(rdir / "jun-da_frequency.tsv", JUNDA_SCHEMA)
    print(dat.head(10))
    print('-' * 100)
    print(jd.head(10))
