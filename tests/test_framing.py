import json
import os
from pathlib import Path

import numpy as np
from PIL import Image
import pytest
import yaml

from static2live.config import load_config
from static2live.depth import SuppliedDepth
from static2live.framing import crop_box
from static2live.pipeline import generate
from static2live.regions import canonical_image, load_regions, save_regions
from static2live.storage import sha256, write_json
from static2live.validator import validate_output


@pytest.mark.parametrize('anchor,top',[('top',0),('center',50),('bottom',100)])
def test_crop_anchor_and_horizontal_center(anchor,top):
    assert crop_box((400,300),{'aspect':'2:1','anchor':anchor})==(0,top,400,top+200)
    assert crop_box((400,200),{'aspect':'1:1','anchor':anchor})==(100,0,300,200)
    assert crop_box((400,300)) is None


@pytest.mark.parametrize('value',['0:9','16:0','nan','16/9','-1:9','1:99999',16])
def test_invalid_aspect(value):
    with pytest.raises(Exception):load_config(overrides={'framing':{'aspect':value}})


def fixture(root):
    source=root/'source.png'
    y,x=np.mgrid[:300,:400]
    rgb=np.stack((y%256,x%256,np.zeros_like(x)),axis=-1).astype('uint8')
    Image.fromarray(rgb).save(source)
    depth=root/'depth.png';Image.fromarray(np.round(y/299*255).astype('uint8')).save(depth)
    masks={'protected':Image.fromarray(np.where((y<45)&(x>170)&(x<230),255,0).astype('uint8'))}
    save_regions(root/'annotation',masks,{'protected':{'id':'protected','source':'manual','confirmed':True}},sha256(source),(400,300))
    return source,depth,root/'annotation/assets/regions.json'


def test_crop_rgb_depth_mask_roundtrip_and_legacy(tmp_path):
    source,depth,regions=fixture(tmp_path);original=sha256(source)
    framing={'aspect':'2:1','anchor':'top'}
    image,size=canonical_image(source,800,framing)
    with Image.open(source) as original_image:
        assert np.array_equal(np.asarray(image),np.asarray(original_image)[:200])
    assert size==(400,300) and image.size==(400,200)
    result,provenance=SuppliedDepth(depth,size,(0,0,400,200)).predict(image)
    assert result.shape==(200,400) and .65<float(result[-1,0])<.68
    assert provenance['crop_box']==[0,0,400,200]
    masks,_,_=load_regions(regions,image.size,original,size,(0,0,400,200))
    assert np.asarray(masks['protected'])[20,200]==255
    out,report=generate(source,tmp_path/'out',overrides={'auto_plan':False,'parallax_enabled':True,
        'framing':framing,'max_edge':800},depth_map=depth,regions_path=regions)
    assert report['structural_status']=='passed'
    assert json.loads((out/'analysis.json').read_text())['crop']==[0,0,400,200]
    imported,_,_=load_regions(out/'assets/regions.json',image.size,original,size,(0,0,400,200))
    assert np.array_equal(np.asarray(imported['protected']),np.asarray(masks['protected']))
    with pytest.raises(ValueError,match='已裁切标注'):
        load_regions(out/'assets/regions.json',size,original)
    # No framing retains the previous image/depth/mask coordinate contract.
    full,_=canonical_image(source,800)
    assert full.size==(400,300) and sha256(source)==original
    # Changed framing cannot be hidden by merely rehashing the config resource.
    config=yaml.safe_load((out/'config.yaml').read_text());config['framing']['anchor']='bottom'
    (out/'config.yaml').write_text(yaml.safe_dump(config),encoding='utf8')
    manifest=json.loads((out/'manifest.json').read_text());manifest['resources']['config.yaml']=sha256(out/'config.yaml')
    write_json(out/'manifest.json',manifest)
    failed=validate_output(out,write=False)
    assert next(c for c in failed['checks'] if c['name']=='input_framing')['status']=='failed'


def test_cli_anchor_override_preserves_yaml_aspect(tmp_path):
    from static2live.cli import main
    source,_,_=fixture(tmp_path)
    config=tmp_path/'config.yaml';config.write_text('framing:\n  aspect: "2:1"\n  anchor: bottom\n',encoding='utf8')
    assert main(['generate','--input',str(source),'--config',str(config),'--no-parallax',
        '--no-auto-plan','--crop-anchor','top','--output',str(tmp_path/'out')])==0
    out=tmp_path/'out/source/v001'
    assert json.loads((out/'analysis.json').read_text())['crop']==[0,0,400,200]


def test_lower_resolution_full_mask_uses_source_frame(tmp_path):
    source,_,_=fixture(tmp_path);y,x=np.mgrid[:150,:200]
    low=tmp_path/'low'
    save_regions(low,{'protected':Image.fromarray(np.where(y<25,255,0).astype('uint8'))},
        {'protected':{'id':'protected','source':'imported','confirmed':True}},sha256(source),(200,150))
    masks,_,_=load_regions(low/'assets/regions.json',(400,200),sha256(source),(400,300),(0,0,400,200))
    assert np.asarray(masks['protected'])[20,20]==255
    assert np.asarray(masks['protected'])[150,20]==0


def test_anchor_without_aspect_is_not_silently_ignored():
    with pytest.raises(ValueError,match='crop anchor'):
        load_config(overrides={'framing':{'anchor':'top'}})


def test_exif_frame_uses_oriented_coordinates(tmp_path):
    from PIL import ImageOps
    source=tmp_path/'rotated.jpg'
    y,x=np.mgrid[:300,:400]
    image=Image.fromarray(np.stack((y%256,x%256,np.zeros_like(x)),axis=-1).astype('uint8'))
    exif=Image.Exif();exif[274]=6;image.save(source,exif=exif)
    actual,size=canonical_image(source,800,{'aspect':'2:1','anchor':'top'})
    assert size==(300,400) and actual.size==(300,150)
    with Image.open(source) as opened:expected=ImageOps.exif_transpose(opened).convert('RGB').crop((0,0,300,150))
    assert np.array_equal(np.asarray(actual),np.asarray(expected))


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='synthetic browser opt-in')
def test_browser_preserves_top_framed_rgb(tmp_path):
    from playwright.sync_api import sync_playwright
    from test_v02 import browser_launch
    from test_v06 import read_pixels
    source,_,_=fixture(tmp_path)
    root,_=generate(source,tmp_path/'out',overrides={'auto_plan':False,'parallax_enabled':False,
        'framing':{'aspect':'2:1','anchor':'top'}})
    with Image.open(root/'assets/image.png') as opened:expected=np.asarray(opened).copy()
    with sync_playwright() as pw:
        browser=browser_launch(pw);page=browser.new_page(viewport={'width':400,'height':200})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto((root/'index.html').as_uri())
        page.wait_for_function("window.static2live?.status==='ready' && static2live.frames>2")
        actual=np.flipud(read_pixels(page))
        assert actual.shape==(200,400,4) and np.all(actual[:,:,3]==255)
        assert np.max(np.abs(actual[:,:,:3].astype(int)-expected.astype(int)))<=1
        assert not errors
        browser.close()
