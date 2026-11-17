import base64
import io
import json
import os
import re

import numpy as np
from PIL import Image
import pytest

from static2live.config import load_config
from static2live.motion import validate_motion
from static2live.pipeline import generate
from static2live.storage import read_json, sha256, write_json
from static2live.validator import validate_output
from static2live.wallpaper_engine import plan_native
from test_v06 import fixture_image


def foliage_fixture(tmp_path):
    source, path = fixture_image(tmp_path)
    bundle = read_json(path)
    mask = np.zeros((192, 256), dtype='uint8')
    mask[25:170, 25:125] = 255
    stream = io.BytesIO()
    Image.fromarray(mask).save(stream, format='PNG')
    bundle['regions'].append({'id':'other','source':'manual','confirmed':True,
        'asset':'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()})
    write_json(path, bundle)
    return source, path


def options(shader='none', intensity=.8):
    return {'auto_plan':False, 'parallax_enabled':False,
            'effects':[{'type':'foliage_sway','amplitude_px':1.5,'intensity':intensity,'period_seconds':8}],
            'shader':{'preset':shader,'amplitude_px':1,'strength':.7,'period_seconds':4}}


def test_foliage_binding_and_limits(tmp_path):
    source, regions = foliage_fixture(tmp_path)
    root, report = generate(source, tmp_path/'out', regions_path=regions, overrides=options('water_ripple'))
    assert report['structural_status']=='passed'
    motion = read_json(root/'motion.json')
    assert motion['parallax']['overscan_px'] >= 1.5*.8+1*.7
    with pytest.raises(ValueError):
        load_config(overrides={'effects':[{'type':'foliage_sway','region':'full'}]})
    with pytest.raises(ValueError):
        load_config(overrides={'effects':[{'type':'foliage_sway','amplitude_px':4.1}]})
    with pytest.raises(ValueError,match='other'):
        generate(source,tmp_path/'missing',overrides=options())
    motion['parallax']['overscan_px']=1
    with pytest.raises(ValueError):
        validate_motion(motion)
    native=plan_native(read_json(root/'motion.json'),load_config(overrides=options('water_ripple')))
    assert any('foliage_sway' in item for item in native['unsupported'])
    html=(root/'index.html').read_text('utf8')
    match=re.search(r'(<script id="static2live-data" type="application/json">)(.*?)(</script>)',html,re.S)
    boot=json.loads(match.group(2))
    packed=Image.open(io.BytesIO(base64.b64decode(boot['effect_texture'].split(',',1)[1]))).copy()
    assert packed.mode=='RGBA'
    assert packed.getpixel((120,75))[1]==0  # Protected overlap.
    assert packed.getpixel((60,130))[1]==255
    packed.putpixel((60,130),(0,0,0,255))
    stream=io.BytesIO();packed.save(stream,format='PNG')
    boot['effect_texture']='data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()
    (root/'index.html').write_text(html[:match.start(2)]+json.dumps(boot)+html[match.end(2):],encoding='utf8')
    manifest=read_json(root/'manifest.json');manifest['resources']['index.html']=sha256(root/'index.html')
    write_json(root/'manifest.json',manifest)
    assert next(check for check in validate_output(root,write=False)['checks']
                if check['name']=='offline_embedding')['status']=='failed'


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='browser opt-in')
@pytest.mark.parametrize('shader',['none','water_ripple'])
def test_foliage_actual_pixels_and_composition(tmp_path, shader):
    from playwright.sync_api import sync_playwright
    source, regions=foliage_fixture(tmp_path)
    root,_=generate(source,tmp_path/'out',regions_path=regions,overrides=options(shader))
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':256,'height':192})
        page.goto((root/'index.html').as_uri())
        page.wait_for_function('static2live.status==="ready"')
        def frame(time, effects=True, advanced=True):
            count=page.evaluate('static2live.frames')
            page.evaluate('([t,e,s])=>{static2live.setTime(t);static2live.setEffectsEnabled(e);static2live.setShaderEnabled(s)}',
                          [time,effects,advanced])
            page.wait_for_function('([t,n])=>static2live.time===t && static2live.frames>n',arg=[time,count])
            return np.asarray(Image.open(io.BytesIO(page.screenshot())).convert('RGB'))
        still0,still2=frame(0,False,False),frame(2,False,False)
        assert np.array_equal(still0,still2)
        plant0,plant2=frame(0,True,False),frame(2,True,False)
        assert not np.array_equal(plant0,plant2)
        assert np.array_equal(plant0[70:90,115:135],plant2[70:90,115:135])
        if shader=='water_ripple':
            water0,water1=frame(0,False,True),frame(1,False,True)
            assert not np.array_equal(water0,water1)
            both=frame(1,True,True)
            assert not np.array_equal(both,water1)
        page.evaluate('static2live.motion.effects[0].intensity=0')
        zero0,zero2=frame(0,True,False),frame(2,True,False)
        assert np.array_equal(zero0,zero2)
        page.evaluate('static2live.motion.effects[0].intensity=.8')
        page.emulate_media(reduced_motion='reduce')
        page.wait_for_function('static2live.reducedMotion')
        reduced0=frame(0,True,True)
        page.wait_for_timeout(120)
        reduced1=np.asarray(Image.open(io.BytesIO(page.screenshot())).convert('RGB'))
        assert np.array_equal(reduced0,reduced1)
        assert page.evaluate('static2live.shaderCompiled && static2live.errors.length===0')
        browser.close()


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='browser opt-in')
def test_soft_dust_visible_and_excludes_person(tmp_path):
    from playwright.sync_api import sync_playwright
    source,regions=foliage_fixture(tmp_path)
    bundle=read_json(regions)
    guard=next(region for region in bundle['regions'] if region['id']=='protected')
    bundle['regions'].append({**guard,'id':'person'})
    write_json(regions,bundle)
    config={'auto_plan':False,'parallax_enabled':False,'effects':[
        {'type':'dust','count':90,'intensity':.8,'size_px':6,'softness':.8,'exclude_person':True}]}
    root,report=generate(source,tmp_path/'out',regions_path=regions,overrides=config)
    assert report['structural_status']=='passed'
    with pytest.raises(ValueError):
        load_config(overrides={'effects':[{'type':'rain','softness':.8}]})
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':256,'height':192})
        page.goto((root/'index.html').as_uri())
        page.wait_for_function('static2live.status==="ready"')
        page.evaluate('static2live.setTime(0)')
        def alpha():
            count=page.evaluate('static2live.frames')
            page.wait_for_function('n=>static2live.frames>n',arg=count)
            return np.asarray(page.evaluate('Array.from(document.querySelector("#effects").getContext("2d").getImageData(0,0,256,192).data)'),
                              dtype='uint8').reshape(192,256,4)[:,:,3]
        soft=alpha()
        assert np.count_nonzero(soft)>100
        assert np.max(soft[50:100,100:150])==0
        page.evaluate('static2live.motion.effects[0].softness=0')
        hard=alpha()
        assert soft.sum()<hard.sum()
        page.evaluate('static2live.setEffectsEnabled(false)')
        assert np.max(alpha())==0
        browser.close()
