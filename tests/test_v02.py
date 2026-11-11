import base64
import builtins
from pathlib import Path
import json
import io
import os
import numpy as np
from PIL import Image
import pytest
from static2live.pipeline import generate
from static2live.editor import export_editor
from static2live.config import load_config
from static2live.effects import complete_effect
from static2live.regions import load_regions
from static2live.segmentation import ModelSegmentation,semantic_regions,prepare_segmentation,resize_class_logits
from static2live.motion import validate_motion
from static2live.storage import sha256,write_json,read_json
from static2live.validator import validate_output


@pytest.fixture
def source(tmp_path):
    y,x=np.indices((192,256));rgb=np.stack([x,(y*1.2)%256,(x*.3+y*.6)%256],axis=2).astype('uint8')
    path=tmp_path/'scene.png';Image.fromarray(rgb).save(path)
    return path


def bundle(source,path,regions=('sky','person','cloud','glow')):
    entries=[]
    for key in regions:
        array=np.zeros((192,256),dtype='uint8')
        if key=='person':array[80:175,100:156]=255
        else: array[:80]=255
        stream=io.BytesIO();Image.fromarray(array).save(stream,format='PNG')
        entries.append({'id':key,'source':'manual','confirmed':True,'asset':'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()})
    value={'version':'0.2','coordinates':'top-left-normalized','input_sha256':sha256(source),'canvas':{'width':256,'height':192},'regions':entries}
    write_json(path,value);return value


def test_lite_no_model_no_network(source,tmp_path,monkeypatch):
    original=builtins.__import__
    def checked(name,*args,**kwargs):
        if name.split('.')[0] in ['torch','transformers','huggingface_hub']:raise AssertionError('Lite imported a model dependency')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',checked)
    root,report=generate(source,tmp_path/'out',overrides={'parallax_enabled':False,'effects':[{'type':'dust'}]})
    assert report['structural_status']=='passed'
    assert not (root/'assets/depth.png').exists()
    assert read_json(root/'motion.json')['assets']['depth'] is None
    assert 'depth_estimation' in report['not_applicable']


def test_smart_no_fallback(source,tmp_path):
    with pytest.raises(ValueError,match='不会自动下载或回退 Lite'):
        generate(source,tmp_path/'out',model_cache=tmp_path/'missing',overrides={'mode':'smart','parallax_enabled':False})
    with pytest.raises(ValueError,match='许可'):prepare_segmentation(tmp_path)


def test_semantic_table():
    masks,records=semantic_regions(np.array([[0,1],[2,3]],dtype='uint8'),{0:'wall',1:'person',2:'sky',3:'water'})
    assert set(masks)=={'person','sky','water'} and all(r['source']=='model' for r in records.values())
    assert 'cloud' not in masks
    with pytest.raises(ValueError):semantic_regions(np.zeros((2,2)),{0:'wall'})


def test_bounded_logits_equal_full():
    torch=pytest.importorskip('torch');torch.manual_seed(13)
    logits=torch.randn(1,21,8,9)
    full=torch.nn.functional.interpolate(logits,size=(29,37),mode='bilinear',align_corners=False).argmax(1)[0]
    assert torch.equal(resize_class_logits(logits,(29,37)).long(),full)
    logits.zero_();assert not resize_class_logits(logits,(29,37)).any() # ties keep lowest class ID


def test_mirror_official_hash(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import hashlib
    huggingface_hub=pytest.importorskip('huggingface_hub')
    from static2live.model_download import download_snapshot
    raw=b'expected-weights'
    file=SimpleNamespace(rfilename='model.safetensors',lfs={'sha256':hashlib.sha256(raw).hexdigest()},blob_id=None)
    class Api:
        def __init__(self,endpoint):assert endpoint=='https://huggingface.co'
        def model_info(self,*args,**kwargs):assert kwargs['files_metadata'];return SimpleNamespace(sha='official-commit',siblings=[file])
    calls=[]
    def download(*args,**kwargs):
        calls.append(kwargs);(tmp_path/'model.safetensors').write_bytes(raw)
    monkeypatch.setattr(huggingface_hub,'HfApi',Api);monkeypatch.setattr(huggingface_hub,'snapshot_download',download)
    revision,endpoint=download_snapshot('test','main',tmp_path,['model.safetensors'],'https://hf-mirror.com')
    assert revision=='official-commit' and calls[0]['revision']==revision and endpoint=='https://hf-mirror.com'
    monkeypatch.setattr(huggingface_hub,'snapshot_download',lambda *a,**kw:(tmp_path/'model.safetensors').write_bytes(b'corrupt'))
    with pytest.raises(ValueError,match='官方文件校验失败'):download_snapshot('test','main',tmp_path,['model.safetensors'],'https://hf-mirror.com')


def test_config_binding_tamper(source,tmp_path):
    root,_=generate(source,tmp_path/'out',overrides={'parallax_enabled':False})
    motion=read_json(root/'motion.json');motion['seed']+=1;write_json(root/'motion.json',motion)
    assert validate_output(root)['structural_status']=='failed'


@pytest.mark.parametrize('bad',[{'mode':'auto'},{'effects':[{'type':'unknown'}]},{'effects':[{'type':'dust','intensity':float('nan')}]},
  {'effects':[{'type':'dust','count':257}]},{'effects':[{'type':'cloud_drift','region':'sky'}]},{'effects':[{'type':'dust'},{'type':'dust'}]}])
def test_bad_v02_config(bad):
    with pytest.raises(Exception):load_config(overrides=bad)


def test_region_binding_and_confirmation(source,tmp_path):
    path=tmp_path/'regions.json';value=bundle(source,path)
    masks,_,_=load_regions(path,(128,96),sha256(source));assert masks['sky'].size==(128,96)
    value['regions'][0]['source']='rule';value['regions'][0]['confirmed']=False;write_json(path,value)
    with pytest.raises(ValueError,match='未确认'):load_regions(path,(256,192),sha256(source))
    value['regions'][0]['confirmed']=True;value['input_sha256']='wrong';write_json(path,value)
    with pytest.raises(ValueError,match='哈希'):load_regions(path,(256,192),sha256(source))


def test_shared_regions_reimport(source,tmp_path):
    path=tmp_path/'regions.json';bundle(source,path)
    root,report=generate(source,tmp_path/'out',regions_path=path,overrides={'parallax_enabled':False,'effects':[{'type':'glow'}]})
    assert report['structural_status']=='passed'
    other,_=generate(source,tmp_path/'out',regions_path=root/'assets/regions.json',overrides={'parallax_enabled':False})
    assert other.name=='v002'
    assert Image.open(other/'assets/masks/sky.png').tobytes()==Image.open(root/'assets/masks/sky.png').tobytes()
    editor=export_editor(source,tmp_path/'annotations',regions_path=root/'assets/regions.json')
    assert (editor/'index.html').exists()


def test_missing_region_warning(source,tmp_path):
    root,report=generate(source,tmp_path/'out',overrides={'parallax_enabled':False,'effects':[{'type':'cloud_drift'}]})
    assert report['structural_status']=='warning' and read_json(root/'motion.json')['effects'][0]['enabled'] is False


def test_v01_real_output_readonly():
    outputs=Path(__file__).parents[1]/'output'
    old=next((p for p in outputs.glob('*/v002') if read_json(p/'motion.json').get('version')=='0.1'),None)
    if old is None:pytest.skip('private local V0.1 output not distributed')
    assert validate_output(old,write=False)['structural_status']=='passed'


def browser_launch(pw):
    return pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='browser opt-in')
@pytest.mark.parametrize('kind',['rain','snow','dust','fog','glow','cloud_drift'])
def test_effects_browser(source,tmp_path,kind):
    from playwright.sync_api import sync_playwright
    path=tmp_path/'regions.json';bundle(source,path)
    config={'parallax_enabled':False,'effects':[{'type':kind,'region':'cloud' if kind=='cloud_drift' else 'sky','intensity':.7,'amplitude_px':1}]}
    root,_=generate(source,tmp_path/'out',regions_path=path,overrides=config)
    with sync_playwright() as pw:
        browser=browser_launch(pw);page=browser.new_page(viewport={'width':256,'height':192})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto((root/'index.html').as_uri());page.wait_for_function("window.static2live && static2live.status==='ready'")
        def pixels(time,enabled=True):
            page.evaluate('([t,e])=>{static2live.setTime(t);static2live.setEffectsEnabled(e)}',[time,enabled]);page.wait_for_timeout(80)
            return np.array(page.evaluate('static2live.readPixels()'),dtype='uint8').reshape(192,256,4)
        a=pixels(0);b=pixels(2);assert not np.array_equal(a,b)
        assert np.array_equal(pixels(2),b),'fixed seed/time not deterministic'
        off=pixels(2,False);assert np.array_equal(off,pixels(0,False))
        # readPixels is bottom-up. Lower source part lies outside sky/cloud mask.
        assert np.array_equal(a[:100],off[:100]) and np.array_equal(b[:100],off[:100]),'effect leaked outside region'
        page.emulate_media(reduced_motion='reduce');page.wait_for_timeout(100)
        assert np.array_equal(pixels(0),pixels(3))
        assert not errors
        browser.close()


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='browser opt-in')
def test_editor_browser(source,tmp_path):
    from playwright.sync_api import sync_playwright
    editor=export_editor(source,tmp_path/'annotations')
    with sync_playwright() as pw:
        browser=browser_launch(pw);page=browser.new_page(viewport={'width':700,'height':850})
        page.goto((editor/'index.html').as_uri());page.wait_for_function('window.static2liveEditor && static2liveEditor.ready')
        canvas=page.locator('#paint');canvas.scroll_into_view_if_needed();box=canvas.bounding_box()
        page.mouse.move(box['x']+box['width']*.3,box['y']+box['height']*.5);page.mouse.down()
        page.mouse.move(box['x']+box['width']*.6,box['y']+box['height']*.5,steps=10);page.mouse.up()
        saved=page.evaluate('static2liveEditor.exportBundle()');assert saved['regions'][0]['source']=='manual'
        path=tmp_path/'drawn.json';write_json(path,saved);masks,_,_=load_regions(path,(256,192),sha256(source))
        assert np.asarray(masks['person']).sum()>0
        page.select_option('#tool','erase');canvas.scroll_into_view_if_needed();box=canvas.bounding_box()
        page.mouse.click(box['x']+box['width']*.45,box['y']+box['height']*.5)
        erased=page.evaluate('static2liveEditor.exportBundle()');write_json(path,erased)
        next_masks,_,_=load_regions(path,(256,192),sha256(source));assert np.asarray(next_masks['person']).sum()<np.asarray(masks['person']).sum()
        page.set_viewport_size({'width':1100,'height':900});box=canvas.bounding_box()
        point=page.evaluate('([x,y])=>static2liveEditor.normalizedPoint(x,y)',[box['x']+box['width']*.3,box['y']+box['height']*.4])
        assert np.allclose(point,[.3,.4])
        page.locator('summary').click()
        page.click('#bright');assert page.evaluate('!!static2liveEditor.candidate')
        with pytest.raises(Exception):page.evaluate('static2liveEditor.exportBundle()')
        page.click('#confirm');value=page.evaluate('static2liveEditor.exportBundle()');assert value['regions'][0]['source']=='rule'
        page.evaluate('(value)=>static2liveEditor.importBundle(value)',saved)
        assert page.evaluate('static2liveEditor.exportBundle()')['regions'][0]['asset']==saved['regions'][0]['asset']
        browser.close()
