"""V1 automatic planning is grounded in sourced masks, never RGB fake semantics."""
import json
import os
import sys
import subprocess
from copy import deepcopy
import numpy as np
import pytest
from PIL import Image,ImageDraw
from static2live.analyzer import prepare_assets
from static2live.pipeline import generate
from static2live.storage import read_json,write_json,sha256
from static2live.validator import validate_output
from static2live.config import load_config
from static2live.planning import plans_equal,make_plan
from test_v02 import source,bundle
from test_v03 import fixture
from test_v04 import inputs
from test_v06 import fixture_image


def test_rgb_is_not_semantics(source,tmp_path,monkeypatch):
    for backend in ('ModelDepth','ModelSegmentation','ModelHumanParsing'):
        monkeypatch.setattr('static2live.analyzer.'+backend+'.predict',lambda *a:pytest.fail('No model should run'))
    before=sha256(source)
    result=prepare_assets(source,overrides={'parallax_enabled':False})
    assert result.planning['selected_preset']=='general_balanced'
    assert not result.planning['features']['region_coverage'] and not result.masks
    assert result.planning['recommendation']['deferred']
    assert result.report()['generated'] is False and sha256(source)==before
    assert not (tmp_path/'output').exists()


def test_planner_roundoff_not_rgb_or_parameter_tolerance(source):
    expected=prepare_assets(source,overrides={'parallax_enabled':False}).planning
    small=deepcopy(expected);small['features']['luminance_std']+=1e-16
    assert plans_equal(small,expected)
    for field,value in [('luminance_std',expected['features']['luminance_std']+1e-6),('rgb_pixel_sha256','0'*64)]:
        changed=deepcopy(expected);changed['features'][field]=value;assert not plans_equal(changed,expected)
    changed=deepcopy(expected);changed['selected_preset']='snow_soft';assert not plans_equal(changed,expected)


def test_hair_visibility_revision_keeps_legacy_reproducible():
    image=Image.new('RGB',(768,512),(150,110,80))
    hair=Image.new('L',image.size);ImageDraw.Draw(hair).rectangle((80,10,660,480),fill=255)
    guard=Image.new('L',image.size);ImageDraw.Draw(guard).rectangle((250,50,450,250),fill=255)
    masks={'hair':hair,'protected':guard}
    config=load_config()
    old=make_plan(image,masks,config,version='1.0')
    new=make_plan(image,masks,config)
    assert old['recommendation']['suggestions']['hair_sway']['amplitude_px']==1.5
    assert new['version']=='1.1' and new['recommendation']['suggestions']['hair_sway']['amplitude_px']==2.5
    with pytest.raises(ValueError):make_plan(image,masks,config,version='future')


def test_known_person_auto_guard_and_priority(source,tmp_path):
    regions=tmp_path/'regions.json';bundle(source,regions,('person',))
    before=sha256(source)
    analyzed=prepare_assets(source,regions_path=regions,overrides={'parallax_enabled':False})
    assert analyzed.config['preset']=='warm_portrait'
    assert analyzed.records['protected']['source']=='rule'
    assert not analyzed.config['hair_sway']['enabled']
    assert np.all(np.asarray(analyzed.masks['protected'])[np.asarray(analyzed.masks['person'])>0]==255)
    root,report=generate(source,tmp_path/'out',regions_path=regions,overrides={'parallax_enabled':False})
    assert report['structural_status']=='passed' and report['status']=='not_tested'
    assert sha256(source)==before and read_json(root/'manifest.json')['planner']['version']=='1.1'
    overridden=prepare_assets(source,regions_path=regions,overrides={'parallax_enabled':False,'preset':'snow_soft','effects':[]})
    assert overridden.config['preset']=='snow_soft' and overridden.config['effects']==[] and overridden.planning['explicit_preset']
    disabled=prepare_assets(source,regions_path=regions,overrides={'parallax_enabled':False,'auto_plan':False})
    assert disabled.config['preset']=='general_balanced' and 'protected' not in disabled.masks


def test_hands_without_face_does_not_disable_whole_person_guard(source,tmp_path):
    regions=tmp_path/'regions.json';bundle(source,regions,('person','hands'))
    result=prepare_assets(source,regions_path=regions,overrides={'parallax_enabled':False})
    assert result.records['protected']['source_regions']==['person']
    assert np.all(np.asarray(result.masks['protected'])[np.asarray(result.masks['person'])>0]==255)


def test_imported_hair_auto_motion_but_explicit_zero_wins(tmp_path):
    source,regions=inputs(tmp_path)
    auto=prepare_assets(source,regions_path=regions,overrides={'parallax_enabled':False})
    assert auto.config['hair_sway']['enabled']
    assert auto.config['hair_sway']['amplitude_px']==min(2.5,min(auto.image.size)*.005)
    explicit=prepare_assets(source,regions_path=regions,overrides={'parallax_enabled':False,'hair_sway':{'enabled':False,'amplitude_px':0}})
    assert explicit.config['hair_sway']['enabled'] is False and explicit.config['hair_sway']['amplitude_px']==0
    root,report=generate(source,tmp_path/'out',regions_path=regions,overrides={'parallax_enabled':False})
    assert report['structural_status']=='passed' and read_json(root/'motion.json')['sways']
    # Rehashing invented recommendations must not make the planner validator pass.
    analysis=read_json(root/'analysis.json');analysis['planning']['recommendation']['preset']='rainy_city'
    write_json(root/'analysis.json',analysis);manifest=read_json(root/'manifest.json')
    manifest['resources']['analysis.json']=sha256(root/'analysis.json');write_json(root/'manifest.json',manifest)
    report=validate_output(root,write=False)
    assert next(c for c in report['checks'] if c['name']=='automatic_planning')['status']=='failed'


def test_water_recommendation_and_explicit_shader_off(tmp_path):
    source,regions=fixture_image(tmp_path)
    auto=prepare_assets(source,regions_path=regions,overrides={'parallax_enabled':False})
    assert auto.config['preset']=='landscape_soft' and auto.config['shader']['preset']=='water_ripple'
    off=prepare_assets(source,regions_path=regions,overrides={'parallax_enabled':False,'shader':{'preset':'none'},'effects':[]})
    assert off.config['shader']['preset']=='none' and off.config['effects']==[]


@pytest.mark.parametrize('preset',['anime_chill','snow_forest','cyberpunk'])
def test_recommended_style_presets_are_real_generation(tmp_path,preset):
    source,regions=fixture_image(tmp_path)
    root,report=generate(source,tmp_path/'out',regions_path=regions,overrides={'preset':preset,'parallax_enabled':False})
    assert report['structural_status'] in ('passed','warning')
    assert load_config(root/'config.yaml')['preset']==preset
    if preset=='cyberpunk':assert read_json(root/'motion.json')['runtime']['shader']['preset']=='neon_pulse'


def test_protected_only_native_depth(source,tmp_path,fixture):
    engine,_,_,_=fixture
    regions=tmp_path/'regions.json';bundle(source,regions,('person',))
    depth=tmp_path/'matching-depth.png';Image.fromarray(np.tile(np.arange(256,dtype='uint8'),(192,1))).save(depth)
    root,report=generate(source,tmp_path/'out',depth_map=depth,regions_path=regions,engine_path=engine,
        overrides={'target':'wallpaper-engine','effects':[{'type':'dust','exclude_person':True}]})
    assert report['structural_status']=='passed'
    plan=read_json(root/'native-plan.json');assert plan['protected_motion'] and not plan['human_sways']
    scene=read_json(root/'wallpaper-engine/scene.json')
    assert scene['objects'][0]['effects'][0]['file']=='effects/s2l_human/effect.json'
    cover_path=root/'wallpaper-engine/materials/s2l_person_cover.png'
    with Image.open(cover_path) as cover:alpha=cover.getchannel('A').copy()
    changed=Image.new('RGBA',alpha.size,(255,0,255,255));changed.putalpha(alpha);changed.save(cover_path)
    manifest=read_json(root/'manifest.json');manifest['resources']['wallpaper-engine/materials/s2l_person_cover.png']=sha256(cover_path);write_json(root/'manifest.json',manifest)
    assert next(c for c in validate_output(root,write=False)['checks'] if c['name']=='native_scene_structure')['status']=='failed'


def test_analyze_cli_read_only(source,tmp_path):
    result=subprocess.run([sys.executable,'-X','utf8','-m','static2live.cli','analyze','--input',str(source),'--no-parallax'],cwd=tmp_path,capture_output=True,text=True,encoding='utf8')
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout);assert not report['generated'] and report['runtime_status']=='not_tested'
    assert not (tmp_path/'output').exists()


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='browser opt-in')
def test_auto_guard_rigid_nonzero_under_pointer(source,tmp_path):
    from playwright.sync_api import sync_playwright
    from test_v06 import read_pixels
    from test_v02 import browser_launch
    regions=tmp_path/'regions.json';bundle(source,regions,('person',))
    depth=tmp_path/'matching-depth.png';Image.fromarray(np.tile(np.arange(256,dtype='uint8'),(192,1))).save(depth)
    root,_=generate(source,tmp_path/'out',depth_map=depth,regions_path=regions,overrides={'effects':[]})
    with sync_playwright() as pw:
        browser=browser_launch(pw);page=browser.new_page(viewport={'width':256,'height':192})
        page.goto((root/'index.html').as_uri());page.wait_for_function('static2live.status==="ready"')
        page.evaluate('static2live.setPointer(-1,0)');page.wait_for_function('static2live.pointer[0]<-.999');left=read_pixels(page)
        page.evaluate('static2live.setPointer(1,0)');page.wait_for_function('static2live.pointer[0]>.999');right=read_pixels(page)
        # Whole person translates coherently; freezing it hid the mouse effect.
        # This fixture is a smooth RGB gradient: rigid translation preserves
        # its internal horizontal differences (allow one quantisation level).
        a=left[35:95,115:140,:3].astype(int);b=right[35:95,115:140,:3].astype(int)
        assert not np.array_equal(a,b)
        assert np.max(np.abs(np.diff(a,axis=1)-np.diff(b,axis=1)))<=1
        assert not np.array_equal(left,right)
        browser.close()
