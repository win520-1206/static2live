"""Runnable skill recipes and reference integrity, not an LLM-behavior eval."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
from PIL import Image
import yaml

from static2live.storage import read_json, sha256


def test_skill_reference_links_are_local_and_resolve():
    project=Path(__file__).resolve().parents[1]
    for file in [project/'SKILL.md',*sorted((project/'references').glob('*.md'))]:
        for target in re.findall(r'\]\(([^)]+)\)',file.read_text(encoding='utf8')):
            if target.startswith(('http://','https://','#')):continue
            relative=target.split('#',1)[0]
            path=Path(relative)
            assert not path.is_absolute(),(file,target)
            resolved=(file.parent/path).resolve()
            assert resolved.is_relative_to(project) and resolved.is_file(),(file,target)


def test_installed_cli_skill_recipes_without_models(tmp_path):
    # Deliberately synthetic RGB, not a substitute for a real depth model.
    yy,xx=np.indices((128,192))
    source=tmp_path/'source.png'
    Image.fromarray(np.stack([xx,yy,(xx+yy)%256],axis=2).astype('uint8')).save(source)
    original=sha256(source)
    cache=tmp_path/'absent-model-cache'
    cwd=tmp_path/'unrelated-working-directory';cwd.mkdir()
    config=tmp_path/'request.yaml'
    config.write_text(yaml.safe_dump({'preset':'warm_portrait','mode':'lite',
        'parallax_enabled':False,'effects':[],'hair_sway':{'enabled':False,'amplitude_px':0},
        'shader':{'preset':'none'},'audio':{'enabled':False}}),encoding='utf8')
    env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
    def cli(*args):
        return subprocess.run([sys.executable,'-X','utf8','-m','static2live',*map(str,args)],
            cwd=cwd,env=env,capture_output=True,text=True,encoding='utf8',timeout=60)
    def generate(*extra,expected_structure='passed'):
        run=cli(source,'--config',config,'--model-cache',cache,'--output',tmp_path/'out',*extra)
        assert run.returncode==0,run.stderr
        report=json.loads(run.stdout)
        assert report['status']=='not_tested' and report['structural_status']==expected_structure
        return Path(report['output'])
    first=generate();second=generate()
    assert (first.name,second.name)==('v001','v002')
    motion=read_json(first/'motion.json')
    assert not motion['effects'] and not motion.get('sways')
    assert not motion['parallax_enabled'] and motion['assets']['depth'] is None
    assert read_json(first/'manifest.json')['segmentation']['backend']=='none'
    # CLI's explicit effect replaces an empty YAML list, without losing other choices.
    dust=generate('--effect','dust')
    assert [e['type'] for e in read_json(dust/'motion.json')['effects']]==['dust']
    fallback=generate('--target','wallpaper-engine','--engine-path',tmp_path/'missing-engine',expected_structure='warning')
    adapter=read_json(fallback/'manifest.json')['adapter']
    assert adapter['actual']=='web' and adapter['requested']=='wallpaper-engine' and adapter['fallback_reason']
    run=cli(source,'--parallax','--model-cache',cache,'--output',tmp_path/'must-not-exist')
    assert run.returncode!=0 and 'models prepare' in run.stderr
    assert not cache.exists() and not (tmp_path/'must-not-exist').exists()
    assert sha256(source)==original
