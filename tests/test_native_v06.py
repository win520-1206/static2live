"""Native adapter fixtures are not evidence of actual GPU/SceneScript execution."""
import os
import pytest
from PIL import Image
from static2live.pipeline import generate
from static2live.storage import read_json,write_json
from static2live.wallpaper_engine import validate_native,record_native
from static2live.native_runtime import audio_script
from test_v03 import fixture
from test_v06 import fixture_image
from test_v04 import inputs,config


def test_command_path_is_same_file(tmp_path):
    from pathlib import Path
    from static2live.wallpaper_engine import command_path
    parent=tmp_path/'中文';parent.mkdir();entry=parent/'project.json';entry.write_text('{}')
    selected,strategy=command_path(entry)
    assert Path(selected).samefile(entry)
    assert strategy in ('original','existing-ascii-short-path','unicode-host-dependent')
    if strategy=='existing-ascii-short-path':assert selected.isascii()
    assert entry.read_text()=='{}'  # Conversion never renames or edits data.


def test_explicit_ascii_staging(tmp_path,fixture,monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    import tempfile
    from static2live.wallpaper_engine import preview_native
    engine,_,source,_=fixture
    root,_=generate(source,tmp_path/'out',engine_path=engine,overrides={'target':'wallpaper-engine','parallax_enabled':False})
    # Temp directory may have non-ASCII ancestors on a user's machine. Test the
    # ASCII staging logic with the actual project-owned ASCII workspace when set.
    cache=tmp_path/'qa'
    if not str(cache).isascii():
        with pytest.raises(ValueError,match='ASCII'):preview_native(root,engine,cache)
        cache=Path(os.environ.get('STATIC2LIVE_ASCII_TEST_CACHE',tempfile.gettempdir()))/'static2live-test-qa'
        if not str(cache).isascii():pytest.skip('Need explicit writable ASCII test cache to exercise staging copy')
    commands=[]
    monkeypatch.setattr('static2live.wallpaper_engine.subprocess.Popen',lambda command,**kwargs:(commands.append(command) or SimpleNamespace(pid=1,poll=lambda:None)))
    result=preview_native(root,engine,cache)
    assert result['command_entry'].isascii() and result['qa_copy'] and '-playInWindow' in commands[0]
    entry=Path(result['command_entry']);assert entry.exists()
    assert read_json(entry.parent.parent/'qa-source.json')['resources']
    second=preview_native(root,engine,cache);assert second['qa_copy']!=result['qa_copy']
    assert entry.exists()  # Never overwrite the previous QA copy.


@pytest.mark.parametrize('preset',['warm_glow','water_ripple','neon_pulse'])
def test_native_runtime_binding(tmp_path,fixture,preset):
    engine,_,_,_=fixture;source,regions=fixture_image(tmp_path)
    root,report=generate(source,tmp_path/'out',regions_path=regions,engine_path=engine,
        overrides={'target':'wallpaper-engine','parallax_enabled':False,'audio':{'enabled':True,'region':'glow'},'shader':{'preset':preset}})
    assert report['structural_status']=='passed' and report['status']=='not_tested'
    plan=read_json(root/'native-plan.json');assert not plan['unsupported'] and plan['runtime_effect']['shader']['preset']==preset
    scene=read_json(root/'wallpaper-engine/scene.json');effect=scene['objects'][0]['effects'][0]
    assert effect['file']=='effects/s2l_runtime/effect.json' and len(effect['passes'][0]['textures'])==7
    assert len(scene['objects'][0]['effects'])==1
    # Native pass must keep source alpha for the particle occlusion layer.
    with Image.open(root/'assets/image.png') as original,Image.open(root/'wallpaper-engine/materials/s2l_image.png') as transported:
        assert original.convert('RGBA').tobytes()==transported.tobytes()
    with pytest.raises(ValueError,match='audio|shader'):
        record_native(root,'Mock fixture is not actual observation',['load','properties','edges'])
    # Rehashing a moved protection mask cannot bypass the semantic transport check.
    Image.new('RGBA',(256,192),(0,0,0,255)).save(root/'wallpaper-engine/materials/s2l_protected.png')
    with pytest.raises(ValueError,match='蒙版传输'):validate_native(root)


def test_combined_sway_and_shader_not_postprocess(tmp_path,fixture):
    engine,_,_,_=fixture;source,regions=inputs(tmp_path)
    # Audio full needs no invented glow mask; protect/sway sources are explicit.
    root,report=generate(source,tmp_path/'out',regions_path=regions,engine_path=engine,
        overrides={**config(),'target':'wallpaper-engine','audio':{'enabled':True},'effects':[{'type':'dust','exclude_person':True}]})
    assert report['structural_status'] in ('passed','warning')
    scene=read_json(root/'wallpaper-engine/scene.json')
    assert all(len(o.get('effects',[]))==1 for o in scene['objects'] if 'image' in o)
    assert read_json(root/'native-plan.json')['human_sways']
    assert validate_native(root)


@pytest.mark.parametrize('enabled',[False,True])
def test_native_audio_capability_flag_tracks_configuration(tmp_path,fixture,enabled):
    engine,template,source,_=fixture
    # A template's stale capability must not leak to an audio-disabled export.
    template_project=read_json(template/'project.json')
    template_project['general']={'supportsaudioprocessing':True}
    write_json(template/'project.json',template_project)
    root,report=generate(source,tmp_path/'out',engine_path=engine,
        overrides={'target':'wallpaper-engine','auto_plan':False,
                   'parallax_enabled':False,'audio':{'enabled':enabled}})
    assert report['structural_status']=='passed'
    path=root/'wallpaper-engine/project.json';project=read_json(path)
    assert project['general'].get('supportsaudioprocessing',False) is enabled
    assert validate_native(root)
    project['general']['supportsaudioprocessing']=not enabled
    write_json(path,project)
    with pytest.raises(ValueError,match='supportsaudioprocessing'):validate_native(root)
    # Numeric truthiness is not a valid JSON Boolean capability declaration.
    project['general']['supportsaudioprocessing']=int(enabled)
    write_json(path,project)
    with pytest.raises(ValueError,match='supportsaudioprocessing'):validate_native(root)


def test_record_native_capabilities_are_scoped_and_fresh(tmp_path,fixture):
    engine,_,_,_=fixture;source,regions=fixture_image(tmp_path)
    root,_=generate(source,tmp_path/'out',regions_path=regions,engine_path=engine,
        overrides={'target':'wallpaper-engine','parallax_enabled':False,'audio':{'enabled':True,'region':'glow'},
                   'shader':{'preset':'warm_glow'},'performance_profile':'eco','display':{'viewport':[0,0,.5,1]}})
    # This is a recorder unit test only, not evidence of actual host playback.
    report=read_json(root/'validation.json')
    report['checks'].append({'name':'invented_check','status':'passed','detail':'not a current validator check'})
    write_json(root/'validation.json',report)
    report=record_native(root,'Recorder fixture; not actual host QA',['load','properties','edges','audio','shader'])
    checks={c['name']:c for c in report['checks']}
    for name in ('native_runtime','audio_runtime','advanced_shader_runtime'):
        assert checks[name]['status']=='passed' and checks[name]['detail']['target']=='native-scene'
    for name in ('browser_runtime','visual_acceptance','performance_runtime','multi_monitor_runtime'):
        assert checks[name]['status']=='not_tested'
    assert 'invented_check' not in checks and report['status']=='not_tested'


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS')!='1',reason='browser opt-in')
def test_audio_script_mock_contract():
    # Execute actual generated JS against a mocked API; never label as native host QA.
    from playwright.sync_api import sync_playwright
    script=audio_script({'strength':.2,'response_seconds':.15})
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page()
        result=page.evaluate('''script=>{
          let registrations=0,average=Array(64).fill(0);
          const engine={AUDIO_RESOLUTION_64:64,frametime:1/60,registerAudioBuffers(n){if(n!==64)throw Error('bands');registrations++;return {average};}};
          const api=new Function('engine',script.replaceAll('export function','function')+';return {update,applyUserProperties};')(engine);
          const quiet=api.update(0);average.fill(5);average[0]=NaN;
          let high=0;for(let i=0;i<120;i++)high=api.update(0);
          api.applyUserProperties({audioenabled:false});const off=api.update(0);
          api.applyUserProperties({audioenabled:true,audiostrength:50});for(let i=0;i<120;i++)api.update(0);const half=api.update(0);
          average.fill(0);for(let i=0;i<180;i++)api.update(0);const silent=api.update(0);
          return {registrations,quiet,high,off,half,silent};
        }''',script)
        assert result['registrations']==1 and result['quiet']==0 and result['off']==0
        assert 0<result['high']<=.2 and result['half']==pytest.approx(result['high']/2,abs=1e-5)
        assert result['silent']<1e-8
        browser.close()
