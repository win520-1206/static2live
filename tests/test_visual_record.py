"""Recorder invariants only; mocked evidence is not actual visual acceptance."""
import pytest

from static2live.browser_check import record_visual
from static2live.pipeline import generate
from static2live.storage import read_json, write_json, sha256
from test_v06 import fixture_image
from test_v03 import fixture


def prepared_report(tmp_path):
    source,regions=fixture_image(tmp_path)
    root,_=generate(source,tmp_path/'out',regions_path=regions,overrides={
        'parallax_enabled':False,'audio':{'enabled':True,'region':'glow'},
        'shader':{'preset':'warm_glow'},'performance_profile':'eco'})
    report=read_json(root/'validation.json')
    browser=next(c for c in report['checks'] if c['name']=='browser_runtime')
    browser.update(status='passed',detail={'manifest_sha256':sha256(root/'manifest.json'),'method':'unit fixture, not actual browser'})
    return root,report


def test_visual_record_rebuilds_current_checks(tmp_path):
    root,report=prepared_report(tmp_path)
    report['checks']=[c for c in report['checks'] if c['name'] not in (
        'audio_runtime','performance_runtime','advanced_shader_runtime')]
    report['checks'].append({'name':'invented_check','status':'passed','detail':'not a validator check'})
    write_json(root/'validation.json',report)
    result=record_visual(root,'Recorder fixture only, not actual observation')
    checks={c['name']:c for c in result['checks']}
    assert 'invented_check' not in checks
    for name in ('audio_runtime','performance_runtime','advanced_shader_runtime'):
        assert checks[name]['status']=='not_tested'
    assert checks['visual_acceptance']['status']=='passed'
    assert checks['browser_runtime']['status']=='passed'
    assert result['status']=='not_tested'


def test_visual_record_does_not_certify_native_for_web_output(tmp_path):
    root,report=prepared_report(tmp_path)
    forged={'target':'native-scene','manifest_sha256':sha256(root/'manifest.json'),
            'observed':['audio','shader']}
    report['checks'].append({'name':'native_runtime','status':'passed','detail':forged})
    for c in report['checks']:
        if c['name'] in ('audio_runtime','advanced_shader_runtime'):
            c.update(status='passed',detail=forged)
    write_json(root/'validation.json',report)
    result=record_visual(root,'Mock recorder test')
    checks={c['name']:c for c in result['checks']}
    assert 'native_runtime' not in checks
    assert checks['audio_runtime']['status']=='not_tested'
    assert checks['advanced_shader_runtime']['status']=='not_tested'


@pytest.mark.parametrize('detail',[None,'not structured',{}, {'manifest_sha256':'stale'}])
def test_visual_record_requires_current_structured_browser_evidence(tmp_path,detail):
    root,report=prepared_report(tmp_path)
    next(c for c in report['checks'] if c['name']=='browser_runtime')['detail']=detail
    write_json(root/'validation.json',report)
    before=(root/'validation.json').read_bytes()
    with pytest.raises(ValueError,match='结构/浏览器'):
        record_visual(root,'Recorder fixture only')
    assert (root/'validation.json').read_bytes()==before


@pytest.mark.parametrize('stale',[False,True])
def test_visual_record_preserves_only_current_scoped_native_evidence(tmp_path,fixture,stale):
    from static2live.wallpaper_engine import record_native
    engine,_,_,_=fixture
    source,regions=fixture_image(tmp_path)
    root,_=generate(source,tmp_path/'out',regions_path=regions,engine_path=engine,overrides={
        'target':'wallpaper-engine','parallax_enabled':False,
        'audio':{'enabled':True,'region':'glow'},'shader':{'preset':'warm_glow'},
        'performance_profile':'eco'})
    report=record_native(root,'Mock recorder evidence, not actual host observation',
                         ['load','properties','edges','audio','shader'])
    next(c for c in report['checks'] if c['name']=='browser_runtime').update(
        status='passed',detail={'manifest_sha256':sha256(root/'manifest.json'),'method':'mock browser'})
    if stale:
        for c in report['checks']:
            if c['name'] in ('native_runtime','audio_runtime','advanced_shader_runtime'):
                c['detail']['manifest_sha256']='stale'
    write_json(root/'validation.json',report)
    result=record_visual(root,'Unit recorder fixture; not actual visual QA')
    checks={c['name']:c for c in result['checks']}
    for name in ('native_runtime','audio_runtime','advanced_shader_runtime'):
        assert checks[name]['status']==('not_tested' if stale else 'passed')
    assert checks['performance_runtime']['status']=='not_tested'
    assert result['status']=='not_tested'
