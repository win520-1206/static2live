import base64
import hashlib
import io
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
