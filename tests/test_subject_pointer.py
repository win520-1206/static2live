"""Subject continuity contract; synthetic fixtures are not native visual QA."""
import numpy as np
import os
import pytest
from PIL import Image, ImageDraw
from static2live.pipeline import generate
from static2live.storage import read_json, write_json, sha256
from static2live.wallpaper_engine import subject_pointer_guard, validate_native
from test_v03 import fixture
from test_v04 import inputs, config


@pytest.mark.parametrize('policy',['subject-rigid-typo',1,[],{}])
def test_runtime_pointer_policy_does_not_silently_select_freeze(policy):
    from static2live.native_runtime import fragment_source
    with pytest.raises(ValueError,match='policy|策略'):
        fragment_source('vec2 offset = pointer*',{'shader':{'preset':'warm_glow'}},policy)


def test_rigid_shader_rewrite_requires_the_expected_formula():
    from static2live.pointer import human_fragment,RIGID_POLICY
    with pytest.raises(ValueError,match='formula|公式'):
        human_fragment('void main() {}',RIGID_POLICY)


def test_subject_guard_anchors_hair_face_and_cloth_without_changing_masks(tmp_path):
    size=(256,192);regions={}
    for key,box in [('person',(70,20,180,180)),('hair',(50,20,190,140)),
                    ('cloth',(70,130,200,185)),('protected',(90,50,150,110))]:
        mask=Image.new('L',size);ImageDraw.Draw(mask).rectangle(box,fill=255)
        mask.save(tmp_path/(key+'.png'));regions[key]={'asset':key+'.png'}
    motion={'canvas':dict(width=256,height=192),'regions':regions,
            'parallax':{'amplitude_px':1.2},'sways':[{'amplitude_px':1}]}
    before={key:sha256(tmp_path/(key+'.png')) for key in regions}
    guard=np.asarray(subject_pointer_guard(tmp_path,motion))
    for key in regions:
        with Image.open(tmp_path/(key+'.png')) as mask:
            assert np.all(guard[np.asarray(mask)>0]==255)
    assert guard[80,46]==255  # exterior inverse-sampling safety halo
    assert guard[80,5]==0 and guard[5,5]==0  # background still responds
    depth=np.full(size[::-1],.8)
    pointer=depth*(1-guard/255.)+.85*guard/255.
    assert pointer[80,55]==pointer[80,110]==.85  # coherent NONZERO hair/face motion
    assert pointer[80,5]>0
    assert before=={key:sha256(tmp_path/(key+'.png')) for key in regions}


def test_native_person_only_uses_subject_guard_without_sways_or_face_mask(tmp_path,fixture):
    engine,_,source,depth=fixture
    person=Image.new('L',(128,96));ImageDraw.Draw(person).rectangle((35,20,90,75),fill=255)
    person.save(tmp_path/'person.png');bundle=tmp_path/'regions.json'
    write_json(bundle,{'version':'0.2','coordinates':'top-left-normalized',
        'input_sha256':sha256(source),'canvas':{'width':128,'height':96},
        'regions':[{'id':'person','source':'imported','confirmed':True,'asset':'person.png'}]})
    root,report=generate(source,tmp_path/'out',regions_path=bundle,depth_map=depth,engine_path=engine,
        overrides={'target':'wallpaper-engine','auto_plan':False,'effects':[]})
    assert report['structural_status']=='passed'
    motion=read_json(root/'motion.json');assert 'protected' not in motion['regions'] and not motion.get('sways')
    plan=read_json(root/'native-plan.json')
    assert plan['protected_motion'] and plan['pointer_policy']=='subject-rigid-v2'
    scene=read_json(root/'wallpaper-engine/scene.json')
    assert scene['objects'][0]['effects'][0]['passes'][0]['textures'][-1]=='s2l_pointer_guard'
    assert validate_native(root)


def test_native_subject_pointer_guard_keeps_time_sway_and_particle_cover(tmp_path,fixture):
    engine,_,_,_=fixture;source,bundle=inputs(tmp_path)
    annotation=read_json(bundle)
    person=Image.new('L',(256,192));ImageDraw.Draw(person).rectangle((35,15,200,180),fill=255)
    person.save(tmp_path/'person.png')
    annotation['regions'].append({'id':'person','source':'imported','confirmed':True,'asset':'person.png'})
    write_json(bundle,annotation)
    root,report=generate(source,tmp_path/'out',engine_path=engine,regions_path=bundle,
        overrides={**config(),'target':'wallpaper-engine','auto_plan':False,
                   'effects':[{'type':'dust','exclude_person':True}]})
    assert report['structural_status']=='passed'
    plan=read_json(root/'native-plan.json');assert plan['pointer_policy']=='subject-rigid-v2'
    scene=read_json(root/'wallpaper-engine/scene.json')
    image_objects=[obj for obj in scene['objects'] if 'image' in obj]
    assert len(image_objects)==2
    passes=[obj['effects'][0]['passes'][0] for obj in image_objects]
    assert [{k:v for k,v in p.items() if k!='id'} for p in passes][0]=={k:v for k,v in passes[1].items() if k!='id'}
    assert passes[0]['textures'][-1]=='s2l_pointer_guard'
    assert passes[0]['constantshadervalues']['hairAmplitude']['value']>0
    assert validate_native(root)
    Image.new('RGBA',(256,192)).save(root/'wallpaper-engine/materials/s2l_pointer_guard.png')
    with pytest.raises(ValueError,match='人物鼠标保护蒙版'):validate_native(root)


@pytest.mark.parametrize('shader',['warm_glow','float'])
def test_runtime_subject_guard_does_not_replace_effect_protection(tmp_path,fixture,shader):
    from test_v06 import fixture_image
    engine,_,_,_=fixture;source,bundle=fixture_image(tmp_path)
    annotation=read_json(bundle)
    mask=Image.new('L',(256,192));ImageDraw.Draw(mask).rectangle((60,30,180,180),fill=255)
    mask.save(tmp_path/'subject.png')
    annotation['regions'].append({'id':'person','source':'imported','confirmed':True,'asset':'subject.png'})
    # float uses an explicit other region; no inferred geometry.
    annotation['regions'].append({'id':'other','source':'imported','confirmed':True,'asset':'subject.png'})
    write_json(bundle,annotation)
    root,report=generate(source,tmp_path/'out',regions_path=bundle,engine_path=engine,
        overrides={'target':'wallpaper-engine','parallax_enabled':False,'auto_plan':False,
                   'audio':{'enabled':True},'shader':{'preset':shader}})
    assert report['structural_status']=='passed'
    scene=read_json(root/'wallpaper-engine/scene.json');p=scene['objects'][0]['effects'][0]
    assert '_subject/' in p['file'] and len(p['passes'][0]['textures'])==7
    # Guard uses depth G; opaque alpha avoids browser premultiplication losses.
    with Image.open(root/'wallpaper-engine/materials/s2l_depth.png') as packed:
        assert np.array_equal(np.asarray(packed.getchannel('G')),np.asarray(subject_pointer_guard(root,read_json(root/'motion.json'))))
    assert validate_native(root)
    plan=read_json(root/'native-plan.json')
    saved_policy=plan['pointer_policy']
    plan['pointer_policy']='subject-rigid-typo'
    write_json(root/'native-plan.json',plan)
    with pytest.raises(ValueError,match='未知人物鼠标策略'):
        validate_native(root)
    plan['pointer_policy']=saved_policy
    write_json(root/'native-plan.json',plan)
    Image.new('RGBA',(256,192),(51,51,51,0)).save(root/'wallpaper-engine/materials/s2l_depth.png')
    with pytest.raises(ValueError,match='鼠标保护传输'):validate_native(root)


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='browser opt-in')
def test_web_subject_coherent_pointer_and_independent_time_sway(tmp_path):
    from playwright.sync_api import sync_playwright
    from test_v06 import read_pixels
    source,bundle=inputs(tmp_path)
    annotation=read_json(bundle)
    mask=Image.new('L',(256,192));ImageDraw.Draw(mask).rectangle((35,15,200,180),fill=255)
    mask.save(tmp_path/'subject.png')
    annotation['regions'].append({'id':'person','source':'imported','confirmed':True,'asset':'subject.png'})
    write_json(bundle,annotation)
    depth=tmp_path/'depth.png';Image.fromarray(np.tile(np.arange(256,dtype='uint8'),(192,1))).save(depth)
    root,report=generate(source,tmp_path/'out',regions_path=bundle,depth_map=depth,
        overrides={**config(),'parallax_enabled':True,'auto_plan':False,'parallax':{'fraction':.01}})
    assert report['structural_status']=='passed'
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':256,'height':192});errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto((root/'index.html').as_uri());page.wait_for_function('static2live.status==="ready"')
        page.evaluate('static2live.setTime(1);static2live.setPointer(-1,0)')
        page.wait_for_function('static2live.pointer[0]<-.999');a=read_pixels(page)
        page.evaluate('static2live.setPointer(1,0)');page.wait_for_function('static2live.pointer[0]>.999');b=read_pixels(page)
        # Bottom-left readPixels coordinates. Face, adjoining hair mass and cloth.
        assert not np.array_equal(a[35:145,55:175],b[35:145,55:175])
        # Same 3.264-canvas-pixel translation across face and hair: translating
        # the second frame back must reduce error versus the frozen-policy oracle.
        for rows in (slice(55,95),slice(105,135)):
            aa=a[rows,65:155,:3].astype(float)
            translation_errors=[np.mean(np.abs(aa-b[rows,65+s:155+s,:3].astype(float))) for s in (-4,-3,0,3,4)]
            assert min(translation_errors[0],translation_errors[1],translation_errors[3],translation_errors[4]) < translation_errors[2]
        assert np.mean(np.abs(a[30:150,5:15,:3].astype(float)-b[30:150,5:15,:3]))>.1
        assert np.all(a[:,:,3]==255) and np.all(b[:,:,3]==255)
        page.evaluate('static2live.setPointer(0,0)')
        page.wait_for_function('Math.abs(static2live.pointer[0])<.001');baseline=read_pixels(page)
        page.evaluate('static2live.setTime(3)');page.wait_for_timeout(100);c=read_pixels(page)
        assert not np.array_equal(baseline,c)  # pointer held fixed; time sway works
        assert not errors;browser.close()
