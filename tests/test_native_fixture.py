"""Synthetic QA helper: isolate effect choice, no implicit audio or overwrite."""
from pathlib import Path
import subprocess
import sys

import pytest

from static2live.config import load_config
from PIL import Image


@pytest.mark.parametrize('extra,shader,audio',[
    ([], 'neon_pulse',False),
    (['--shader','float'],'float',False),
    (['--shader','wave','--diagnostic-grid','--amplitude-px','3.5'],'wave',False),
    (['--shader','neon_pulse','--diagnostic-flat','--amplitude-px','0'],'neon_pulse',False),
    (['--with-audio','--shader','warm_glow'],'warm_glow',True),
])
def test_native_demo_is_explicit_and_non_destructive(tmp_path,extra,shader,audio):
    script=Path(__file__).resolve().parents[1]/'examples/make_native_runtime_demo.py'
    output=tmp_path/'new-qa-fixture'
    run=subprocess.run([sys.executable,'-X','utf8',str(script),'--output',str(output),*extra],
        cwd=tmp_path,capture_output=True,text=True,encoding='utf8')
    assert run.returncode==0,run.stderr
    config=load_config(output/'config.yaml')
    assert config['shader']['preset']==shader and config['audio']['enabled'] is audio
    assert config['effects']==[] and not config['auto_plan'] and not config['parallax_enabled']
    # A successful helper writes known masks, never pretends to run parsing.
    import json
    bundle=json.loads((output/'assets/regions.json').read_text(encoding='utf8'))
    assert {r['id'] for r in bundle['regions']}=={'glow','water','other','protected'}
    assert all(r['source']=='imported' for r in bundle['regions'])
    assert Image.open(output/'demo.png').size==(640,360)
    if '--diagnostic-grid' in extra:
        assert config['shader']['amplitude_px']==3.5
        with Image.open(output/'demo.png') as grid:
            assert grid.getpixel((0,0))==(250,170,70)
            assert grid.getpixel((16,10))==(225,232,238)
            assert grid.getpixel((10,10))==(28,42,56)
    if '--diagnostic-flat' in extra:
        assert config['shader']['amplitude_px']==0
        with Image.open(output/'demo.png') as flat:
            assert flat.getextrema()==((12,12),(12,12),(12,12))
    before={p.relative_to(output):p.read_bytes() for p in output.rglob('*') if p.is_file()}
    again=subprocess.run([sys.executable,str(script),'--output',str(output)],capture_output=True)
    assert again.returncode!=0
    assert before=={p.relative_to(output):p.read_bytes() for p in output.rglob('*') if p.is_file()}


@pytest.mark.parametrize('amplitude',['nan','inf','-1','3.7'])
def test_native_demo_rejects_invalid_amplitude_before_writing(tmp_path,amplitude):
    script=Path(__file__).resolve().parents[1]/'examples/make_native_runtime_demo.py'
    output=tmp_path/'invalid-fixture'
    run=subprocess.run([sys.executable,str(script),'--output',str(output),'--amplitude-px',amplitude],capture_output=True)
    assert run.returncode!=0
    assert not output.exists()


def test_native_demo_refuses_conflicting_diagnostic_patterns(tmp_path):
    script=Path(__file__).resolve().parents[1]/'examples/make_native_runtime_demo.py'
    output=tmp_path/'conflicting-fixture'
    run=subprocess.run([sys.executable,str(script),'--output',str(output),
        '--diagnostic-grid','--diagnostic-flat'],capture_output=True)
    assert run.returncode!=0 and not output.exists()
