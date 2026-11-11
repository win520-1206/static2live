"""QA input integrity only; does not claim actual host pointer acceptance."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image

from static2live.config import load_config
from static2live.storage import sha256


def test_pointer_fixture_is_explicit_synthetic_and_non_destructive(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'examples/make_native_parallax_demo.py'
    root = tmp_path / 'pointer-qa'
    command = [sys.executable, '-X', 'utf8', str(script), '--output', str(root)]
    run = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, encoding='utf8')
    assert run.returncode == 0, run.stderr
    config = load_config(root / 'config.yaml')
    assert config['parallax_enabled'] and config['parallax']['fraction'] == .01
    assert not config['auto_plan'] and config['mode'] == 'lite'
    assert config['effects'] == [] and config['shader']['preset'] == 'none'
    assert not config['audio']['enabled']
    assert not config['hair_sway']['enabled'] and not config['cloth_sway']['enabled']
    with Image.open(root / 'depth.png') as opened:
        depth = np.asarray(opened)
        assert opened.size == (640, 360) and opened.mode == 'L'
        assert np.all(depth[:, :320] == 0) and np.all(depth[:, 320:] == 255)
    with Image.open(root / 'grid.png') as opened:
        assert opened.getpixel((16, 10)) == (225, 232, 238)
    bundle = json.loads((root / 'assets/regions.json').read_text(encoding='utf8'))
    assert bundle['input_sha256'] == sha256(root / 'grid.png')
    assert len(bundle['regions']) == 1
    region = bundle['regions'][0]
    assert region['id'] == 'protected' and region['source'] == 'imported'
    with Image.open(root / 'assets' / region['asset']) as opened:
        assert opened.getpixel((320, 180)) == 255
        assert opened.getpixel((80, 180)) == 0
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_subject_pointer_fixture_has_distinct_subject_and_face_anchors(tmp_path):
    script=Path(__file__).resolve().parents[1]/'examples/make_native_parallax_demo.py'
    root=tmp_path/'subject-pointer'
    run=subprocess.run([sys.executable,'-X','utf8',str(script),'--output',str(root),'--subject-anchor'],
        cwd=tmp_path,capture_output=True,text=True,encoding='utf8')
    assert run.returncode==0,run.stderr
    config=load_config(root/'config.yaml')
    assert config['parallax_enabled'] and config['shader']['preset']=='warm_glow'
    assert config['shader']['strength']==0 and not config['audio']['enabled']
    bundle=json.loads((root/'assets/regions.json').read_text('utf8'))
    regions={region['id']:region for region in bundle['regions']}
    assert set(regions)=={'person','protected','glow'}
    with Image.open(root/'assets'/regions['person']['asset']) as person,Image.open(root/'assets'/regions['protected']['asset']) as face:
        assert person.getpixel((400,180))==255 and face.getpixel((400,180))==0
        assert person.getpixel((80,180))==0 and face.getpixel((320,180))==255
