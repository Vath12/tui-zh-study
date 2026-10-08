'''The study modes, one module each, in menu order. See base.StudyMode.'''
from .base import StudyContext, StudyMode
from .identify import Identify
from .lookup import Lookup
from .mixture import Mixture
from .numeracy import Numeracy
from .pinyin import Pinyin
from .translation import Translation
from .writing import Writing

MODES : list[type[StudyMode]] = [Identify, Writing, Translation, Pinyin, Numeracy, Mixture, Lookup]
