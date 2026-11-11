"""Real synthetic WebGL/audio checks; no personal photo browser access."""
import io
import wave
import base64
import os
import json
import re
import numpy as np
import pytest
from PIL import Image
from static2live.config import load_config
from static2live.motion import validate_motion
from static2live.pipeline import generate
from static2live.storage import sha256,write_json,read_json
from static2live.validator import validate_output
from static2live.wallpaper_engine import plan_native


def fixture_image(tmp_path):
    y,x=np.mgrid[:192,:256]
    source=tmp_path/'scene.png'
    Image.fromarray(np.stack((x,y,(x*7+y*3)%256),axis=2).astype('uint8')).save(source)
    regions=[]
    for key in ('glow','water','protected'):
        mask=np.zeros((192,256),dtype='uint8')
        if key=='protected':mask[50:100,100:150]=255
        else:mask[20:180,20:230]=255
        stream=io.BytesIO();Image.fromarray(mask).save(stream,format='PNG')
        regions.append({'id':key,'source':'manual','confirmed':True,'asset':'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()})
    path=tmp_path/'regions.json'
    write_json(path,{'version':'0.4','coordinates':'top-left-normalized','input_sha256':sha256(source),'canvas':{'width':256,'height':192},'regions':regions})
    return source,path


@pytest.mark.parametrize('invalid',[
    {'performance_profile':'fake'}, {'audio':{'strength':float('nan')}},
    {'display':{'viewport':[.75,0,.5,1]}}, {'display':{'viewport':[0,0,0,1]}},
    {'shader':{'preset':'fake'}}, {'audio':{'region':'unknown'}},
])
def test_options_reject_invalid(invalid):
    with pytest.raises(Exception):load_config(overrides=invalid)


def test_v06_pipeline_and_binding(tmp_path):
    source,regions=fixture_image(tmp_path);before=sha256(source)
    config={'parallax_enabled':False,'performance_profile':'eco','audio':{'enabled':True,'region':'glow'},'shader':{'preset':'water_ripple'}}
    root,report=generate(source,tmp_path/'out',overrides=config,regions_path=regions)
    assert report['structural_status']=='passed' and report['status']=='not_tested'
    motion=read_json(root/'motion.json');assert motion['version']=='0.6'
    assert read_json(root/'manifest.json')['runtime']['version']=='0.6'
    assert motion['runtime']['performance']['fps']==15 and motion['runtime']['shader']['region']=='water'
    assert sha256(source)==before
    plan=plan_native(motion,load_config(overrides=config))
    assert len(plan['unsupported'])==1 and plan['runtime_effect']['audio']['enabled']
    motion['runtime']['performance']['fps']=999
    with pytest.raises(ValueError):validate_motion(motion)
    with pytest.raises(ValueError,match='glow'):
        generate(source,tmp_path/'missing',overrides={'parallax_enabled':False,'shader':{'preset':'warm_glow'}})
    # Updating hashes alone cannot make a corrupted constant mask valid.
    html=(root/'index.html').read_text('utf8')
    pattern=r'(<script id="static2live-data" type="application/json">)(.*?)(</script>)'
    match=re.search(pattern,html);boot=json.loads(match.group(2));boot['white']=boot['black']
    html=html[:match.start(2)]+json.dumps(boot)+html[match.end(2):]
    (root/'index.html').write_text(html,encoding='utf8')
    manifest=read_json(root/'manifest.json');manifest['resources']['index.html']=sha256(root/'index.html');write_json(root/'manifest.json',manifest)
    failed=validate_output(root,write=False)
    assert next(c for c in failed['checks'] if c['name']=='offline_embedding')['status']=='failed'


BROWSER=pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='browser opt-in')


def read_pixels(page):
    data=page.evaluate('''()=>{const a=static2live.readPixels();let s='';for(let i=0;i<a.length;i+=8192)s+=String.fromCharCode(...a.slice(i,i+8192));return btoa(s)}''')
    w,h=page.evaluate('[document.querySelector("canvas").width,document.querySelector("canvas").height]')
    return np.frombuffer(base64.b64decode(data),np.uint8).reshape(h,w,4)


@BROWSER
@pytest.mark.parametrize('preset',['warm_glow','water_ripple','neon_pulse'])
def test_shader_actual_pixels(tmp_path,preset):
    from playwright.sync_api import sync_playwright
    source,regions=fixture_image(tmp_path)
    root,_=generate(source,tmp_path/'out',overrides={'parallax_enabled':False,'shader':{'preset':preset,'amplitude_px':1,'strength':1}},regions_path=regions)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':256,'height':192});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto((root/'index.html').as_uri());page.wait_for_function('static2live.status==="ready"')
        page.evaluate('static2live.setTime(0)');page.wait_for_timeout(100);a=read_pixels(page)
        page.evaluate('static2live.setTime(2)');page.wait_for_timeout(100);b=read_pixels(page)
        assert not np.array_equal(a,b)
        # Deep inside the explicit protected patch remains exactly unchanged.
        # readPixels uses bottom-left origin, unlike source masks' top-left.
        assert np.array_equal(a[105:125,115:135],b[105:125,115:135])
        assert np.array_equal(a[:8,:8],b[:8,:8])
        assert np.all(a[:,:,3]==255)
        page.evaluate('static2live.setShaderEnabled(false);static2live.setTime(0)');page.wait_for_timeout(100);off=read_pixels(page)
        page.evaluate('static2live.setTime(3)');page.wait_for_timeout(100);assert np.array_equal(off,read_pixels(page))
        page.emulate_media(reduced_motion='reduce');page.evaluate('static2live.setShaderEnabled(true)');page.wait_for_timeout(100);reduced=read_pixels(page)
        page.wait_for_timeout(100);assert np.array_equal(reduced,read_pixels(page))
        assert not errors;browser.close()


@BROWSER
@pytest.mark.parametrize('layout',['horizontal','vertical','unequal'])
def test_profile_budget_and_spanning(tmp_path,layout):
    from playwright.sync_api import sync_playwright
    source,_=fixture_image(tmp_path)
    if layout=='vertical':
        rects=([0,0,1,1],[0,0,1,.5],[0,.5,1,.5]);sizes=((256,384),(256,192),(256,192))
    elif layout=='unequal':
        rects=([0,0,1,1],[0,0,1/3,1],[1/3,0,2/3,1]);sizes=((768,192),(256,192),(512,192))
    else:
        rects=([0,0,1,1],[0,0,.5,1],[.5,0,.5,1]);sizes=((512,192),(256,192),(256,192))
    roots=[]
    for rect in rects:
        root,_=generate(source,tmp_path/'out',overrides={'parallax_enabled':False,'performance_profile':'eco','display':{'viewport':rect},'effects':[{'type':'dust','count':40}]})
        roots.append(root)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        images=[]
        for i,root in enumerate(roots):
            page=browser.new_page(viewport={'width':sizes[i][0],'height':sizes[i][1]},device_scale_factor=2)
            page.goto((root/'index.html').as_uri());page.wait_for_function('static2live.status==="ready"')
            page.evaluate('static2live.setTime(2)');page.wait_for_timeout(150)
            assert page.evaluate('static2live.effectParticleCounts[0].count')==20
            count=page.evaluate('static2live.frames');page.wait_for_timeout(600)
            assert 2<=page.evaluate('static2live.frames')-count<=14
            images.append(read_pixels(page));page.close()
        combined=np.concatenate([images[2],images[1]],axis=0) if layout=='vertical' else np.concatenate(images[1:],axis=1)
        assert combined.shape==images[0].shape
        assert np.abs(combined.astype(float)-images[0].astype(float)).mean()<.15
        page=browser.new_page(viewport={'width':5000,'height':3000},device_scale_factor=2)
        page.goto((roots[0]/'index.html').as_uri());page.wait_for_function('static2live.status==="ready"')
        width,height=page.evaluate('[document.querySelector("canvas").width,document.querySelector("canvas").height]')
        assert width*height<=2073600 and width<5000 and height<3000
        browser.close()


@BROWSER
def test_local_audio_real_fft_and_stop(tmp_path):
    from playwright.sync_api import sync_playwright
    source,regions=fixture_image(tmp_path)
    # Isolate audio: V1 can independently recommend water motion from this fixture.
    root,_=generate(source,tmp_path/'out',overrides={'parallax_enabled':False,'audio':{'enabled':True,'region':'glow'},'shader':{'preset':'none'}},regions_path=regions)
    samples=(np.sin(np.arange(44100)*2*np.pi*220/44100)*20000).astype('<i2')
    wav=tmp_path/'tone.wav'
    with wave.open(str(wav),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(44100);f.writeframes(samples.tobytes())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader','--mute-audio'])
        page=browser.new_page(viewport={'width':256,'height':192});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto((root/'index.html').as_uri());page.wait_for_function('static2live.status==="ready"')
        page.locator('#audio-controls summary').click();quiet=read_pixels(page)
        for _ in range(2):
            page.locator('#audio-file').set_input_files(wav)
            page.wait_for_function('static2live.audio.status==="playing" && static2live.audio.level>.01')
            sounding=read_pixels(page);assert not np.array_equal(quiet,sounding)
            assert np.array_equal(quiet[105:125,115:135],sounding[105:125,115:135])
            page.evaluate('static2live.setAudioEnabled(false)');page.wait_for_timeout(100)
            assert np.array_equal(quiet,read_pixels(page))
            page.evaluate('static2live.setAudioEnabled(true)')
            page.click('#audio-stop');page.wait_for_function('static2live.audio.level===0 && static2live.audio.status==="waiting"')
            page.wait_for_timeout(100);assert np.array_equal(quiet,read_pixels(page))
        assert not errors;browser.close()


@BROWSER
def test_spanning_offset_portrait_gap_and_negative_desktop_origin(tmp_path):
    """Reported OS layout geometry in isolated Chromium, not physical-screen QA."""
    from playwright.sync_api import sync_playwright
    source,_=fixture_image(tmp_path)
    # Primary (0,0,1920,1080), portrait (-1600,-367,1067,1707).
    # These are explicit regression data, not auto-detection or production defaults.
    union=(3520,1707)
    crops=[(0,0,*union),(0,0,1067,1707),(1600,367,1920,1080)]
    roots=[]
    for x,y,w,h in crops:
        rect=[x/union[0],y/union[1],w/union[0],h/union[1]]
        root,_=generate(source,tmp_path/'out',overrides={'parallax_enabled':False,
            'performance_profile':'quality','display':{'viewport':rect},'effects':[]})
        roots.append(root)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        images=[]
        for root,(_,_,w,h) in zip(roots,crops):
            page=browser.new_page(viewport={'width':w,'height':h},device_scale_factor=1)
            page.goto((root/'index.html').as_uri());page.wait_for_function('static2live.status==="ready"')
            page.evaluate('static2live.setTime(2)');page.wait_for_timeout(100)
            pixels=np.flipud(read_pixels(page))
            assert pixels.shape==(h,w,4) and np.all(pixels[:,:,3]==255)
            images.append(pixels);page.close()
        for actual,(x,y,w,h) in zip(images[1:],crops[1:]):
            expected=images[0][y:y+h,x:x+w]
            assert np.abs(actual.astype(float)-expected.astype(float)).mean()<.15
        browser.close()
