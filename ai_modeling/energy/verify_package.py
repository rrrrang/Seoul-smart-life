"""이 영역 폴더만 임시 경로로 복사해 단독 실행을 검사한다."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

if __name__ == '__main__':
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    root = Path(__file__).resolve().parent
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    env.pop('PYTHONPATH', None)
    with tempfile.TemporaryDirectory(prefix=root.name + '-only-') as directory:
        isolated = Path(directory) / root.name
        shutil.copytree(root, isolated, ignore=shutil.ignore_patterns('__pycache__', '.venv', 'venv', '.git'))
        result = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(isolated / 'verify_checks.py')],
                                cwd=directory, env=env, encoding='utf-8', capture_output=True)
        print(result.stdout, end='')
        print(result.stderr, end='', file=sys.stderr)
        raise SystemExit(result.returncode)
