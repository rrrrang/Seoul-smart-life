"""저장 모델의 호환 클래스를 이 폴더 안에 연결한다."""
import sys
import types
from . import common
if 'Model_Training' not in sys.modules:
    legacy = types.ModuleType('Model_Training')
    legacy.__path__ = []
    sys.modules['Model_Training'] = legacy
sys.modules.setdefault('Model_Training.common', common)
sys.modules['Model_Training'].common = sys.modules['Model_Training.common']
