from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import jsonschema
import numpy as np
from PIL import Image
import pytest

from static2live.config import load_config
from static2live.depth import ModelDepth, SuppliedDepth, normalize_depth
from static2live.motion import create_motion, validate_motion
from static2live.pipeline import generate
from static2live.storage import allocate_version, check_overwrite, read_json, safe_resource, sha256, write_json
from static2live.validator import validate_output


@pytest.fixture
def sources(tmp_path):
    image, depth=tmp_path/'image.png',tmp_path/'depth.png'
    y,x=np.indices((100,160))
    Image.fromarray(np.stack([x%256,y%256,(x+y)%256],axis=2).astype('uint8')).save(image)
    Image.fromarray((x*255/159).astype('uint8')).save(depth)
    return image,depth


def test_priority(tmp_path):
    cfg=tmp_path/'config.yaml'
    cfg.write_text('preset: portrait_subtle\nmax_edge: 512\nparallax:\n  response_seconds: 0.4\n',encoding='utf8')
    c=load_config(cfg,{'max_edge':None,'device':None})
    assert c['max_edge']==512 and c['parallax']=={'fraction':.002,'response_seconds':.4}
    c=load_config(cfg,{'max_edge':1024,'preset':'landscape_soft'})
    assert c['max_edge']==1024 and c['parallax']['fraction']==.004 and c['parallax']['response_seconds']==.4


@pytest.mark.parametrize('override',[{'target':'video'},{'device':'other'},{'max_edge':0},{'parallax':{'fraction':.011}}, {'parallax':{'fraction':float('inf')}},{'parallax':{'fraction':float('nan')}},{'unknown':1}])
def test_bad_config(override):
    with pytest.raises((ValueError,jsonschema.ValidationError)):
        load_config(overrides=override)


@pytest.mark.parametrize('preset,fraction',[('portrait_subtle',.002),('general_balanced',.003),('landscape_soft',.004)])
def test_units(preset,fraction):
    m=create_motion((2048,1365),load_config(overrides={'preset':preset}))
    assert m['parallax']['amplitude_px']==pytest.approx(1365*fraction)
    validate_motion(m)
    m['parallax']['amplitude_px']=20
    with pytest.raises(ValueError): validate_motion(m)


def test_depth_direction_size(sources):
    image,depth=sources
    arr,meta=SuppliedDepth(depth,(160,100)).predict(Image.open(image))
    assert arr.shape==(100,160) and arr[:,0].max()==0 and arr[:,-1].min()==1 and meta['near_white']
    with pytest.raises(ValueError): SuppliedDepth(depth,(100,160)).predict(Image.open(image))
    Image.new('RGB',(160,100)).save(depth)
    with pytest.raises(ValueError): SuppliedDepth(depth,(160,100)).predict(Image.open(image))
    with pytest.raises(ValueError): normalize_depth([[float('nan')]])
    assert not normalize_depth(np.ones((2,2))).any()


def test_no_fake_depth(tmp_path):
    with pytest.raises(ValueError,match='models prepare'): ModelDepth(tmp_path).predict(Image.new('RGB',(64,64)))


def test_generate_integrity_versions(sources,tmp_path):
    image,depth=sources
    original=sha256(image)
    root,report=generate(image,tmp_path/'out',depth_map=depth,overrides={'max_edge':128})
    other,_=generate(image,tmp_path/'out',depth_map=depth)
    assert root.name=='v001' and other.name=='v002' and sha256(image)==original
    assert report['structural_status']=='passed' and report['status']=='not_tested'
    assert Image.open(root/'assets/image.png').size==(128,80)
    expected=Image.open(image).convert('RGB');expected.thumbnail((128,128),Image.Resampling.LANCZOS)
    assert np.array_equal(expected,Image.open(root/'assets/image.png'))
    (root/'runtime.js').write_text('corrupted',encoding='utf8')
    assert validate_output(root)['structural_status']=='failed'


def test_refs_and_hash(sources,tmp_path):
    root,_=generate(sources[0],tmp_path/'out',depth_map=sources[1])
    manifest=read_json(root/'manifest.json')
    motion=read_json(root/'motion.json');motion['assets']['depth']='../../outside.png'
    write_json(root/'motion.json',motion)
    manifest['resources']['motion.json']=sha256(root/'motion.json')
    write_json(root/'manifest.json',manifest)
    assert validate_output(root)['structural_status']=='failed'
    with pytest.raises(ValueError): safe_resource(root,'../outside')
    with pytest.raises(ValueError): safe_resource(root,str(root/'index.html'))


def test_stale_embedding(sources,tmp_path):
    root,_=generate(sources[0],tmp_path/'out',depth_map=sources[1])
    manifest=read_json(root/'manifest.json')
    motion=read_json(root/'motion.json');motion['parallax']['amplitude_px']=0
    write_json(root/'motion.json',motion)
    manifest['resources']['motion.json']=sha256(root/'motion.json')
    write_json(root/'manifest.json',manifest)
    report=validate_output(root)
    assert next(c for c in report['checks'] if c['name']=='offline_embedding')['status']=='failed'


def test_atomic_versions(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths=list(pool.map(lambda _:allocate_version(tmp_path,'same'),range(32)))
    assert len(set(paths))==32 and {p.name for p in paths}=={f'v{i:03d}' for i in range(1,33)}


def test_overwrite_safe(sources,tmp_path):
    image,depth=sources
    with pytest.raises((ValueError,FileNotFoundError)): check_overwrite(tmp_path,[])
    root,_=generate(image,tmp_path/'out',depth_map=depth)
    new,_=generate(image,root,depth_map=depth,overwrite=True)
    assert new==root and list(root.parent.glob('v001.backup-*'))
    with pytest.raises(ValueError): check_overwrite(root,[root/'assets/image.png'])
    (root/'user.txt').write_text('mine')
    with pytest.raises(ValueError,match='用户文件'): generate(image,root,depth_map=depth,overwrite=True)


def test_corrupt_illegal(sources,tmp_path):
    bad=tmp_path/'bad.jpg';bad.write_bytes(b'not image')
    with pytest.raises(Exception): generate(bad,tmp_path/'out',depth_map=sources[1])
    with pytest.raises(ValueError): generate(sources[0],tmp_path,depth_map=sources[1])


def test_cli_arbitrary_cwd(sources,tmp_path):
    result=subprocess.run([sys.executable,'-m','static2live.cli',str(sources[0]),'--depth-map',str(sources[1]),'--output',str(tmp_path/'out')],cwd=tmp_path,capture_output=True)
    assert result.returncode==0,result.stderr
    result=subprocess.run([sys.executable,'-m','static2live.cli','generate','--input',str(sources[0]),'--target','video'],capture_output=True)
    assert result.returncode!=0 and b'web' in result.stderr
