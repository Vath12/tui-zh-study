'''The study modes, one module each, in menu order. See base.StudyMode.'''
from .base import StudyContext, StudyMode
from .identify import Identify
from .mixture import Mixture
from .pinyin import Pinyin
from .translation import Translation
from .writing import Writing

MODES : list[type[StudyMode]] = [Identify, Writing, Translation, Pinyin, Mixture]
