import argparse
from pathlib import Path

from v2.vocabulary.vocab import VOCAB_DIR

from .quiz.screen import MODES, QuizScreen
from .strokes import StrokeLook
from .tui import App
from .viewer import ViewerScreen


def main():
    parser = argparse.ArgumentParser(prog='python -m v2.app', description='Chinese character practice in the terminal.')
    parser.add_argument('mode', nargs='?', choices=['view', *MODES], default='read',
                        help='view: type characters and watch their strokes; '
                             + '; '.join(f'{m}: {d}' for m, d in MODES.items()))
    parser.add_argument('-s', '--source', type=Path, default=VOCAB_DIR,
                        help='quiz vocab: a .txt file, or a directory of them (default: all of resources/vocab)')
    args = parser.parse_args()

    app = App()
    look = StrokeLook()
    for setting in look.settings():
        app.settings.add(setting)
    screen = ViewerScreen(look) if args.mode == 'view' else QuizScreen(look, args.mode, args.source)
    app.main(screen)


if __name__ == '__main__':
    main()
