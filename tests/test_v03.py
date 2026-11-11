"""Native mapping unit fixtures are explicitly synthetic, not runtime acceptance."""
from copy import deepcopy
from pathlib import Path
import numpy as np
from PIL import Image
import pytest
from static2live.config import load_config
from static2live.motion import create_motion
from static2live.pipeline import generate
from static2live.storage import write_json,read_json,sha256
from static2live.validator import validate_output
from static2live import wallpaper_engine as we


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    engine=tmp_path/'engine';(engine/'bin').mkdir(parents=True)
    (engine/'wallpaper64.exe').write_bytes(b'UNIT FIXTURE NOT EXECUTABLE')
    (engine/'bin/resourcecompiler64.exe').write_bytes(b'UNIT FIXTURE NOT EXECUTABLE')
    write_json(engine/'version.json',{'version':'unit-fixture'})
    template=engine/'assets/effects/depthparallax/preview'
    for d in ['materials','models','effects/depthparallax','shaders/effects']:(template/d).mkdir(parents=True,exist_ok=True)
    write_json(template/'project.json',{'type':'scene','file':'scene.json','title':'unit fixture'})
    base={'id':28,'image':'models/fixture.json','effects':[{'id':32,'file':'effects/depthparallax/effect.json','passes':[]}]}
    write_json(template/'scene.json',{'version':5,'general':{},'objects':[base]})
    write_json(template/'models/fixture.json',{'material':'materials/fixture.json'})
    write_json(template/'materials/fixture.json',{'passes':[{'shader':'genericimage2','textures':['fixture'],'blending':'translucent'}]})
    write_json(template/'effects/depthparallax/effect.json',{'dependencies':['shaders/effects/depthparallax.frag']})
    (template/'shaders/effects/depthparallax.frag').write_text('UNIT FIXTURE, NOT GLSL')
    def mock_compile(engine,path):
        path.with_suffix('.tex').write_bytes(b'TEXV_UNIT_TEST_HEADER_ONLY'+path.read_bytes())
        return {'input':path.name,'returncode':0,'output':'MOCK: not actual compiler or engine test'}
    monkeypatch.setattr(we,'compile_texture',mock_compile)
    source=tmp_path/'source.png';depth=tmp_path/'depth.png'
    Image.new('RGB',(128,96),(20,30,40)).save(source)
    Image.fromarray(np.tile(np.arange(128,dtype='uint8')*2,(96,1))).save(depth)
    return engine,template,source,depth


def test_target_and_native_sway_config():
    assert load_config(overrides={'target':'wallpaper-engine'})['target']=='wallpaper-engine'
    for overrides in [{'native_sway':True},{'sway_amplitude_px':float('nan')},{'sway_amplitude_px':5}]:
        with pytest.raises(Exception):load_config(overrides=overrides)


def test_native_framed_canvas_and_depth_share_coordinates(fixture,tmp_path):
    engine,_,source,depth=fixture
    root,report=generate(source,tmp_path/'framed',depth_map=depth,engine_path=engine,
        overrides={'target':'wallpaper-engine','auto_plan':False,
            'framing':{'aspect':'16:9','anchor':'top'}})
    assert report['structural_status']=='passed'
    assert read_json(root/'analysis.json')['crop']==[0,0,128,72]
    assert read_json(root/'native-plan.json')['canvas']=={'width':128,'height':72}
    assert read_json(root/'wallpaper-engine/scene.json')['general']['orthogonalprojection']=={'width':128,'height':72}
    with Image.open(root/'assets/depth.png') as opened:assert opened.size==(128,72)
    # Mock compiler validates mapping only, never actual GPU/visual acceptance.


def test_sway_sampling_support_preserves_source():
    mask=Image.new('L',(64,64));mask.paste(255,(20,20,44,44))
    before=np.asarray(mask).copy()
    support=np.asarray(we.sway_sampling_mask(mask,4))
    assert np.array_equal(before,np.asarray(mask))
    assert support[32,17]>250  # Outward silhouette sampling is no longer pinned.
    assert support[32,10]==0 and support[32,32]==255
    assert np.any((support>0)&(support<255))


def test_native_sway_sampling_validation(fixture,tmp_path):
    engine,_,source,_=fixture
    foliage=engine/'assets/effects/foliagesway'
    (foliage/'materials').mkdir(parents=True)
    (foliage/'shaders').mkdir()
    write_json(foliage/'effect.json',{'dependencies':[],'passes':[]})
    mask=Image.new('L',(128,96));mask.paste(255,(40,30,70,60));mask.save(tmp_path/'other.png')
    annotation=tmp_path/'regions.json'
    write_json(annotation,{'version':'0.2','coordinates':'top-left-normalized','input_sha256':sha256(source),
        'canvas':{'width':128,'height':96},'regions':[{'id':'other','source':'imported',
        'confirmed':True,'asset':'other.png'}]})
    root,report=generate(source,tmp_path/'out',regions_path=annotation,engine_path=engine,
        overrides={'target':'wallpaper-engine','parallax_enabled':False,'native_sway':True,'sway_amplitude_px':.5})
    assert report['structural_status']=='passed'
    effect=read_json(root/'wallpaper-engine/scene.json')['objects'][0]['effects'][0]
    assert effect['passes'][0]['combos']=={'MODE':0,'MASK':1}
    assert effect['passes'][0]['textures']==[None,'s2l_sway_mask','s2l_noise']
    assert 'sampling_policy' in read_json(root/'native-plan.json')['sway']
    Image.new('RGBA',(128,96)).save(root/'wallpaper-engine/materials/s2l_sway_mask.png')
    with pytest.raises(ValueError,match='采样蒙版'):we.validate_native(root)


def test_missing_engine_fallback(tmp_path,monkeypatch):
    source=tmp_path/'image.png';Image.new('RGB',(100,80)).save(source)
    def absent(*args):raise we.AdapterUnavailable('explicit test: engine missing')
    monkeypatch.setattr(we,'find_engine',absent)
    root,report=generate(source,tmp_path/'out',overrides={'target':'wallpaper-engine','parallax_enabled':False})
    manifest=read_json(root/'manifest.json')
    assert manifest['adapter']['actual']=='web' and (root/'index.html').is_file()
    assert report['structural_status']=='warning'
    assert next(c for c in report['checks'] if c['name']=='native_runtime')['status']=='not_tested'


def test_real_errors_not_silent_fallback(fixture,tmp_path,monkeypatch):
    engine,template,source,depth=fixture
    def fail(*args):raise ValueError('compiler failure')
    monkeypatch.setattr(we,'compile_texture',fail)
    with pytest.raises(ValueError,match='compiler failure'):
        generate(source,tmp_path/'out',overrides={'target':'wallpaper-engine'},depth_map=depth,engine_path=engine)
    assert list((tmp_path/'out').rglob('generation-error.json'))


def test_native_resources_and_binding(fixture,tmp_path):
    engine,template,source,depth=fixture;original=sha256(source);template_hash=sha256(template/'scene.json')
    root,report=generate(source,tmp_path/'out',depth_map=depth,engine_path=engine,
        overrides={'target':'wallpaper-engine','effects':[{'type':'dust'}]})
    assert report['structural_status']=='passed' and report['status']=='not_tested'
    assert sha256(source)==original and sha256(template/'scene.json')==template_hash
    assert read_json(root/'manifest.json')['adapter']['actual']=='native-scene'
    scene=read_json(root/'wallpaper-engine/scene.json')
    constants=scene['objects'][0]['effects'][0]['passes'][0]['constantshadervalues']
    amplitude=read_json(root/'motion.json')['parallax']['amplitude_px']
    scales=list(map(float,constants['scale']['value'].split()))
    assert np.allclose(np.array(scales)*np.array([128,96]),amplitude)
    assert 'sens' not in constants and 'center' not in constants
    assert scene['objects'][0]['effects'][0]['file']=='effects/s2l_depth/effect.json'
    shader=(root/'wallpaper-engine/shaders/effects/s2l_depth.frag').read_text()
    # Engine GLSL->HLSL translation does not expand single-scalar vec2 constructors.
    assert 'vec2(-1.0, -1.0)' in shader and 'vec2(0.0, 0.0)' in shader
    assert 'vec2(-1.0)' not in shader and 'vec2(1.0)' not in shader
    particle=next(o for o in scene['objects'] if 'particle' in o)
    assert 'alpha' not in particle and particle['instanceoverride']['alpha']['value']==1
    dust=read_json(root/'wallpaper-engine'/particle['particle'])
    initial={v['name']:v for v in dust['initializer']}
    effective=read_json(root/'native-plan.json')['particles'][0]
    assert initial['sizerandom']['max']==effective['size_px']*10
    assert initial['alpharandom']['max']==min(1,effective['intensity']*2.4)
    # Dust keeps contrast on bright backgrounds; do not regress to additive washout.
    dust_material=read_json(root/'wallpaper-engine'/dust['material'])
    assert dust_material['passes'][0]['blending']=='translucent'
    assert initial['sizerandom']['min']>0 and initial['alpharandom']['min']>0
    assert dust['emitter'][0]['distancemax']=='64.0 48.0 0'
    assert float(initial['velocityrandom']['max'].split()[1])==effective['speed_px_s']
    assert next(v for v in dust['operator'] if v['name']=='alphafade')['fadeouttime']==.8
    assert scene['general']['cameraparallaxamount']==0
    (root/'wallpaper-engine/materials/s2l_depth.tex').write_bytes(b'bad')
    assert validate_output(root)['structural_status']=='failed'


def test_unsupported_recorded(fixture,tmp_path):
    engine,template,source,_=fixture
    root,_=generate(source,tmp_path/'out',engine_path=engine,overrides={'target':'wallpaper-engine','parallax_enabled':False,
        'effects':[{'type':'dust','region':'full'},{'type':'fog','region':'full'}]})
    assert len(read_json(root/'native-plan.json')['particles'])==2
    config=load_config(overrides={'target':'wallpaper-engine','parallax_enabled':False,'effects':[{'type':'glow','region':'full'}]})
    plan=we.plan_native(create_motion((128,96),config,depth_present=False),config)
    assert len(plan['unsupported'])==1 and not plan['particles']
    config['native_sway']=True
    with pytest.raises(ValueError,match='other'):we.plan_native(create_motion((128,96),config,depth_present=False),config)


def test_template_escape_rejected(fixture,tmp_path):
    engine,template,source,depth=fixture
    value=read_json(template/'models/fixture.json');value['material']='../../outside.json';write_json(template/'models/fixture.json',value)
    with pytest.raises(ValueError,match='越界'):
        generate(source,tmp_path/'out',depth_map=depth,engine_path=engine,overrides={'target':'wallpaper-engine'})


def test_missing_native_reference_fails(fixture,tmp_path):
    engine,template,source,depth=fixture
    root,_=generate(source,tmp_path/'out',depth_map=depth,engine_path=engine,overrides={'target':'wallpaper-engine'})
    scene=read_json(root/'wallpaper-engine/scene.json');scene['objects'][0]['effects'][0]['visible']['user']='unknown'
    write_json(root/'wallpaper-engine/scene.json',scene)
    manifest=read_json(root/'manifest.json');manifest['resources']['wallpaper-engine/scene.json']=sha256(root/'wallpaper-engine/scene.json');write_json(root/'manifest.json',manifest)
    assert validate_output(root)['structural_status']=='failed'


def test_invalid_template_no_fake_native(fixture,tmp_path):
    engine,template,source,_=fixture
    write_json(template/'project.json',{'file':'index.html','type':'web'})
    with pytest.raises(ValueError,match='Scene'):
        generate(source,tmp_path/'out',overrides={'target':'wallpaper-engine','parallax_enabled':False},engine_path=engine)


def test_native_observation_guard(fixture,tmp_path):
    engine,template,source,depth=fixture
    root,_=generate(source,tmp_path/'out',depth_map=depth,engine_path=engine,overrides={'target':'wallpaper-engine','effects':[{'type':'dust'}]})
    with pytest.raises(ValueError,match='缺少'):we.record_native(root,'Unit mock observation, not actual runtime',['load'])
    report=we.record_native(root,'Unit mock observation, not actual runtime',['load','mouse','edges','properties','particles'])
    assert next(c for c in report['checks'] if c['name']=='native_runtime')['status']=='passed'
    assert report['status']=='not_tested'  # Does not invent browser/visual acceptance.
    (root/'wallpaper-engine/scene.json').write_text('{}')
    with pytest.raises(ValueError):we.record_native(root,'bad',['load','mouse','edges','properties','particles'])


def test_native_preview_no_desktop_switch(fixture,tmp_path,monkeypatch):
    from types import SimpleNamespace
    engine,template,source,depth=fixture
    root,_=generate(source,tmp_path/'out',depth_map=depth,engine_path=engine,overrides={'target':'wallpaper-engine'})
    commands=[]
    def mock_run(command,**kwargs):commands.append(command);return SimpleNamespace(pid=1,poll=lambda:None)
    monkeypatch.setattr(we.subprocess,'Popen',mock_run)
    result=we.preview_native(root,engine)
    assert '-playInWindow' in commands[0] and result['runtime_status']=='not_tested'
    assert result['window_title'].isascii() and result['window_title'].startswith('Static2Live QA ')
    assert 'path_strategy' in result and 'warnings' in result


@pytest.mark.parametrize('aspect,expected',[(None,[853,640]),('16:9',[960,540]),
    ('3440:1440',[960,405]),('9:16',[360,640])])
def test_native_preview_preserves_canvas_aspect(fixture,tmp_path,monkeypatch,aspect,expected):
    from types import SimpleNamespace
    engine,_,source,depth=fixture
    overrides={'target':'wallpaper-engine','auto_plan':False}
    if aspect:overrides['framing']={'aspect':aspect,'anchor':'top'}
    root,_=generate(source,tmp_path/'out',depth_map=depth,engine_path=engine,overrides=overrides)
    commands=[]
    monkeypatch.setattr(we.subprocess,'Popen',lambda command,**kwargs:
        (commands.append(command) or SimpleNamespace(pid=1,poll=lambda:None)))
    result=we.preview_native(root,engine)
    command=commands[0]
    actual=[int(command[command.index('-width')+1]),int(command[command.index('-height')+1])]
    assert actual==expected==result['requested_preview_size']
    assert '-playInWindow' in command and result['runtime_status']=='not_tested'
    canvas=read_json(root/'motion.json')['canvas']
    assert abs(actual[0]*canvas['height']-actual[1]*canvas['width'])<=max(canvas.values())


def test_no_native_sway_without_mask(fixture,tmp_path):
    engine,template,source,depth=fixture
    with pytest.raises(ValueError,match='other'):
        generate(source,tmp_path/'out',depth_map=depth,engine_path=engine,overrides={'target':'wallpaper-engine','native_sway':True})


def test_native_bounded_pixel_mapping(fixture,tmp_path):
    engine,_,source,depth=fixture
    root,_=generate(source,tmp_path/'out',depth_map=depth,engine_path=engine,overrides={'target':'wallpaper-engine'})
    motion=read_json(root/'motion.json');scene=read_json(root/'wallpaper-engine/scene.json')
    scale=np.array(list(map(float,scene['objects'][0]['effects'][0]['passes'][0]['constantshadervalues']['scale']['value'].split())))
    amplitude=motion['parallax']['amplitude_px'];dimensions=np.array([128,96])
    # Algebra of packaged shader, not a claim of native GPU rendering.
    for pointer in [[-1,-1],[1,1],[-3,4],[0,0]]:
        p=np.clip(pointer,-1,1)
        near=p*np.array([-1,1])*scale*dimensions
        far=near*.2
        assert np.max(np.abs(near))<=amplitude+1e-9
        assert np.allclose(far*5,near)
        assert np.allclose(near*0,0)
    constants=scene['objects'][0]['effects'][0]['passes'][0]['constantshadervalues']
    constants['scale']['value']='1 1'
    write_json(root/'wallpaper-engine/scene.json',scene)
    with pytest.raises(ValueError,match='幅度'):we.validate_native(root)
