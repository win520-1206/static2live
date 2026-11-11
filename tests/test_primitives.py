import os
import numpy as np
import pytest
from static2live.primitives import GEOMETRIC,SHADER_MODES
from static2live.pipeline import generate
from static2live.storage import read_json,write_json
from static2live.validator import validate_output
from test_v03 import fixture
from test_v06 import fixture_image,read_pixels


def primitive_inputs(tmp_path):
    source,regions=fixture_image(tmp_path)
    value=read_json(regions)
    # Explicit test-region identity, not automatic semantic recognition.
    value['regions'].append({**next(r for r in value['regions'] if r['id']=='glow'),'id':'other'})
    write_json(regions,value)
    return source,regions


@pytest.mark.parametrize('preset',GEOMETRIC)
def test_native_primitive_transport_and_bounds(tmp_path,fixture,preset):
    engine,_,_,_=fixture;source,regions=primitive_inputs(tmp_path)
    root,report=generate(source,tmp_path/'out',regions_path=regions,engine_path=engine,
        overrides={'target':'wallpaper-engine','parallax_enabled':False,'shader':{'preset':preset,'amplitude_px':1,'strength':1}})
    assert report['structural_status']=='passed'
    motion=read_json(root/'motion.json')
    assert motion['parallax']['overscan_px']>=1
    scene=read_json(root/'wallpaper-engine/scene.json')
    effect=scene['objects'][0]['effects'][0]
    assert effect['file']=='effects/s2l_primitives/effect.json'
    constants=effect['passes'][0]['constantshadervalues']
    assert constants['shaderMode']==SHADER_MODES.index(preset)
    assert constants['canvasAspect']==256/192
    assert (root/'wallpaper-engine/shaders/effects/s2l_primitives.frag').is_file()
    constants['canvasAspect']=1
    write_json(root/'wallpaper-engine/scene.json',scene)
    assert validate_output(root,write=False)['structural_status']=='failed'


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='browser opt-in')
@pytest.mark.parametrize('preset',GEOMETRIC)
def test_primitive_web_pixels(tmp_path,preset):
    from playwright.sync_api import sync_playwright
    source,regions=primitive_inputs(tmp_path)
    root,_=generate(source,tmp_path/'out',regions_path=regions,
        overrides={'parallax_enabled':False,'shader':{'preset':preset,'amplitude_px':1,'strength':1,'period_seconds':8}})
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':256,'height':192});errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto((root/'index.html').as_uri());page.wait_for_function('static2live.status==="ready"')
        def frame(t):
            page.evaluate('t=>static2live.setTime(t)',t);page.wait_for_timeout(90)
            return read_pixels(page)
        a=frame(0);b=frame(2);loop=frame(8)
        assert not np.array_equal(a,b)
        assert np.array_equal(a[105:125,115:135],b[105:125,115:135])
        assert np.array_equal(a[:8,:8],b[:8,:8]) and np.all(a[:,:,3]==255)
        assert np.abs(a.astype(float)-loop.astype(float)).mean()<.01
        page.evaluate('static2live.motion.runtime.shader.amplitude_px=0')
        zero=frame(0);assert np.array_equal(zero,frame(2))
        page.evaluate('static2live.motion.runtime.shader.amplitude_px=1;static2live.setShaderEnabled(false)')
        off=frame(0);assert np.array_equal(off,frame(2))
        page.evaluate('static2live.setShaderEnabled(true)');page.emulate_media(reduced_motion='reduce')
        reduced=frame(1);assert np.array_equal(reduced,frame(2))
        assert not errors;browser.close()
