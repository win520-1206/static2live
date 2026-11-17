import base64
import hashlib
import io
import os
import numpy as np
import pytest
from PIL import Image, ImageDraw
from static2live.pipeline import generate
from static2live.storage import sha256, read_json, write_json
from static2live.validator import validate_output
from test_v03 import fixture  # Explicit mocked compiler/template, never native runtime proof.


def inputs(tmp_path, protect=True):
    yy, xx = np.mgrid[:192, :256]
    image = Image.fromarray(np.stack((xx, yy, (xx + yy) % 256), axis=2).astype('uint8'))
    source = tmp_path / 'source.png'; image.save(source)
    entries = []
    for kind in ('hair', 'protected') if protect else ('hair',):
        mask = Image.new('L', image.size)
        ImageDraw.Draw(mask).rectangle((40, 20, 190, 170) if kind=='hair' else (100, 40, 160, 110), fill=255)
        stream = io.BytesIO(); mask.save(stream, format='PNG')
        entries.append({'id':kind, 'source':'manual', 'confirmed':True,
                        'asset':'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()})
    bundle = tmp_path / 'regions.json'
    write_json(bundle, {'version':'0.4', 'coordinates':'top-left-normalized',
                       'canvas':{'width':256,'height':192}, 'input_sha256':sha256(source),'regions':entries})
    return source, bundle


def config():
    return {'mode':'lite','parallax_enabled':False,'hair_sway':{'enabled':True,'amplitude_px':1}}


def test_lite_human_sway_pipeline_no_model(tmp_path, monkeypatch):
    for backend in ('ModelHumanParsing','ModelSegmentation','ModelDepth'):
        monkeypatch.setattr('static2live.pipeline.'+backend+'.predict',lambda *a,**k: pytest.fail('Lite must not infer'))
    source, bundle = inputs(tmp_path); before=sha256(source)
    root, report=generate(source,tmp_path/'output',overrides=config(),regions_path=bundle)
    assert report['structural_status']=='passed'
    assert report['status']=='not_tested'
    motion=read_json(root/'motion.json')
    assert motion['version']=='0.4' and motion['sways'][0]['kind']=='hair'
    assert read_json(root/'manifest.json')['runtime']['version']=='0.4'
    assert motion['assets']['depth'] is None
    assert sha256(source)==before
    with Image.open(root/'assets/image.png') as image:
        assert hashlib.sha256(image.tobytes()).hexdigest()==read_json(root/'analysis.json')['rgb_pixel_sha256']
    # Rehashed tampering must still fail the semantic derivation validator.
    Image.new('L',(256,192),255).save(root/'assets/masks/hair_sway.png')
    manifest=read_json(root/'manifest.json')
    manifest['resources']['assets/masks/hair_sway.png']=sha256(root/'assets/masks/hair_sway.png')
    write_json(root/'manifest.json',manifest)
    failed=validate_output(root,write=False)
    assert next(c for c in failed['checks'] if c['name']=='human_sway_protection')['status']=='failed'


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='browser opt-in')
def test_cloth_bend_actual_pixels_and_zero(tmp_path):
    from playwright.sync_api import sync_playwright
    from test_v02 import browser_launch
    from test_v06 import read_pixels

    source, regions = inputs(tmp_path)
    bundle = read_json(regions)
    bundle['regions'][0]['id'] = 'cloth'
    write_json(regions, bundle)
    root, _ = generate(source, tmp_path/'out', regions_path=regions, overrides={
        'mode':'lite', 'parallax_enabled':False, 'auto_plan':False, 'effects':[],
        'cloth_sway':{'enabled':True,'amplitude_px':1.5,'period_seconds':6.5},
    })
    assert read_json(root/'motion.json')['regions']['cloth_sway']['weight_policy']=='cloth-bend-v2'
    with sync_playwright() as playwright:
        browser = browser_launch(playwright)
        page = browser.new_page(viewport={'width':256,'height':192})
        page.goto((root/'index.html').as_uri())
        page.wait_for_function('static2live.status === "ready"')

        def frame(at):
            page.evaluate('(at) => static2live.setTime(at)', at)
            page.wait_for_timeout(100)
            return np.flipud(read_pixels(page))

        first, second = frame(0), frame(3.25)
        assert not np.array_equal(first[120:155,60:90],second[120:155,60:90])
        assert np.array_equal(first[60:90,120:140],second[60:90,120:140])
        assert np.array_equal(first[:10,:10],second[:10,:10])
        assert np.all(second[:,:,3] == 255)
        page.evaluate('static2live.setSwayStrength(0)')
        assert np.array_equal(frame(0),frame(3.25))
        page.evaluate('static2live.setSwayStrength(1); static2live.setSwayEnabled(false)')
        assert np.array_equal(frame(0),frame(3.25))
        browser.close()


@pytest.mark.parametrize('audio_enabled',[False,True])
def test_native_cloth_breath_formula_and_geometry_binding(tmp_path,fixture,audio_enabled):
    engine,_,_,_=fixture
    source,regions=inputs(tmp_path)
    bundle=read_json(regions);bundle['regions'][0]['id']='cloth';write_json(regions,bundle)
    root,report=generate(source,tmp_path/'out',regions_path=regions,engine_path=engine,overrides={
        'target':'wallpaper-engine','mode':'lite','parallax_enabled':False,'auto_plan':False,
        'effects':[],'cloth_sway':{'enabled':True,'amplitude_px':1.5},
        'audio':{'enabled':audio_enabled,'region':'cloth'},
    })
    assert report['structural_status']=='passed'
    fragments=list((root/'wallpaper-engine/shaders/effects').glob('s2l_*.frag'))
    assert any('s2lClothBreath(uv)' in path.read_text(encoding='utf8') for path in fragments)
    assert all('vec2(-1.0), vec2(1.0)' not in path.read_text(encoding='utf8') for path in fragments)
    motion=read_json(root/'motion.json')
    assert motion['regions']['cloth_sway']['motion_policy']=='cloth-breath-v2'
    assert any('vec2(local.x * 0.35, -0.9)' in path.read_text(encoding='utf8') for path in fragments)
    motion['regions']['cloth_sway']['breath_geometry'][0]+=.01
    write_json(root/'motion.json',motion)
    manifest=read_json(root/'manifest.json')
    manifest['resources']['motion.json']=sha256(root/'motion.json');write_json(root/'manifest.json',manifest)
    invalid=validate_output(root,write=False)
    assert next(c for c in invalid['checks'] if c['name']=='human_sway_protection')['status']=='failed'


def test_missing_protection_rejected(tmp_path):
    source,bundle=inputs(tmp_path,False)
    with pytest.raises(ValueError,match='保护区|protected'):
        generate(source,tmp_path/'output',overrides=config(),regions_path=bundle)


def test_native_human_resources_and_guard(tmp_path, fixture):
    source,bundle=inputs(tmp_path)
    engine,_,_,_=fixture
    root,report=generate(source,tmp_path/'output',overrides={**config(),'target':'wallpaper-engine'},regions_path=bundle,engine_path=engine)
    assert report['structural_status']=='passed'
    plan=read_json(root/'native-plan.json')
    assert plan['human_sways'][0]['kind']=='hair'
    scene=read_json(root/'wallpaper-engine/scene.json')
    p=scene['objects'][0]['effects'][0]['passes'][0]
    assert p['textures'][2:] == ['s2l_hair_weight','s2l_cloth_weight','s2l_protected']
    assert p['constantshadervalues']['hairAmplitude']['value']==1/256
    assert p['constantshadervalues']['clothAmplitude']['value']==0
    Image.new('RGBA',(256,192)).save(root/'wallpaper-engine/materials/s2l_protected.png')
    from static2live.wallpaper_engine import validate_native
    with pytest.raises(ValueError,match='蒙版传输'):
        validate_native(root)


def test_lite_parsing_refused(tmp_path):
    source,_=inputs(tmp_path)
    with pytest.raises(ValueError,match='Lite'):
        generate(source,tmp_path/'output',overrides={'human_parsing':True,'mode':'lite'})


def test_nested_sway_configuration_precedence_preserves_unspecified_fields(tmp_path):
    from static2live.config import load_config
    path=tmp_path/'config.yaml'
    write_json(path, {'preset':'warm_portrait','mode':'lite',
                     'hair_sway':{'enabled':True,'amplitude_px':1.5,'period_seconds':7,'phase':1}})
    # JSON is also valid YAML. Partial CLI overrides must not replace the
    # entire user object or reset its period/phase to defaults.
    result=load_config(path,{'hair_sway':{'amplitude_px':2},'preset':None})
    assert result['hair_sway']==dict(enabled=True,amplitude_px=2,period_seconds=7,phase=1)
    assert result['cloth_sway']['enabled'] is False


@pytest.mark.parametrize('empty', [True, False])
def test_nonzero_sway_without_eligible_pixels_refused(tmp_path, empty):
    source,bundle=inputs(tmp_path)
    value=read_json(bundle)
    mask=Image.new('L',(256,192),0 if empty else 255)
    stream=io.BytesIO();mask.save(stream,format='PNG')
    value['regions'][0 if empty else 1]['asset']='data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()
    write_json(bundle,value)
    with pytest.raises(ValueError,match='没有可运动像素'):
        generate(source,tmp_path/'output',overrides=config(),regions_path=bundle)


def test_model_masks_rederived_after_rehashed_tampering(tmp_path, monkeypatch):
    # Synthetic backends test validator algebra, never real-model quality.
    from static2live.human_parser import LABELS
    source,_=inputs(tmp_path)
    labels=np.zeros((192,256),dtype='uint8')
    labels[10:180,50:220]=2
    labels[40:110,110:170]=1
    labels[60:68,130:142]=0  # enclosed misclassified eye pixels
    monkeypatch.setattr('static2live.pipeline.ModelSegmentation.predict',lambda *a:
        (np.zeros_like(labels),{0:'person',1:'sky',2:'water'},{'backend':'segformer-b0-ade'}))
    monkeypatch.setattr('static2live.pipeline.ModelHumanParsing.predict',lambda *a:
        (labels,dict(enumerate(LABELS)),{'backend':'fashn-human-parser','model_id':'fashn-ai/fashn-human-parser'}))
    root,report=generate(source,tmp_path/'output',overrides={**config(),'mode':'smart','human_parsing':True})
    assert report['structural_status']=='passed'
    with Image.open(root/'assets/masks/person.png') as mask:assert np.asarray(mask)[62,135]==255
    # Tamper a person guard while updating all integrity/binding copies; only
    # genuine label derivation validation can detect this semantic corruption.
    relative='assets/masks/person.png'
    with Image.open(root/relative) as mask:array=np.asarray(mask).copy()
    array[62,135]=0;Image.fromarray(array).save(root/relative)
    motion=read_json(root/'motion.json');motion['regions']['person']['coverage']=float(array.mean()/255)
    write_json(root/'motion.json',motion)
    from static2live.renderer import export_web
    export_web(root,motion)
    manifest=read_json(root/'manifest.json')
    for name in manifest['resources']:manifest['resources'][name]=sha256(root/name)
    write_json(root/'manifest.json',manifest)
    failed=validate_output(root,write=False)
    check=next(c for c in failed['checks'] if c['name']=='regions_and_mode')
    assert check['status']=='failed' and 'person' in check['detail']
