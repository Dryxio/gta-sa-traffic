"""Build/install a wheel in a fresh venv, run outside checkout, verify control bundle."""
import json, os, subprocess, sys, tempfile, venv
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def run(*args, cwd):
    subprocess.run(list(map(str,args)), cwd=cwd, check=True)
with tempfile.TemporaryDirectory() as temporary:
    tmp=Path(temporary);wheels=tmp/'wheels';wheels.mkdir()
    run(sys.executable,'-m','pip','wheel','--no-deps','--wheel-dir',wheels,ROOT,cwd=tmp)
    venv.create(tmp/'venv',with_pip=True)
    python=tmp/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    run(python,'-m','pip','install','--no-deps',next(wheels.glob('*.whl')),cwd=tmp)
    run(python,'-m','sa_traffic','compile',ROOT/'examples/signaled-intersection.json','--output',tmp/'compiled',cwd=tmp)
    manifest=json.loads((tmp/'compiled/manifest.json').read_text())
    assert manifest['independent_verification']['valid']
    assert (tmp/'compiled/traffic-signals.ipl').is_file()
    registry=json.loads((tmp/'compiled/signal-model-requirements.json').read_text())
    assert registry['models'] and all(set(m)=={'id','name','txd'} for m in registry['models'])
    print('Clean wheel install: import, compilation, verification and packaged registry PASS')
