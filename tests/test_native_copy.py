"""QA-copy inspection reports changes, never turns them into visual approval."""
import importlib.util
from pathlib import Path
import shutil

import pytest
from static2live.pipeline import generate
from static2live.storage import read_json,write_json,sha256
from test_v03 import fixture

spec=importlib.util.spec_from_file_location('inspect_copy',Path(__file__).parents[1]/'examples/inspect_native_copy.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def test_json_leaf_comparison_is_exact():
    changes=helper.json_changes({'a':1,'b':[True],'old':2},{'a':1+1e-9,'b':[1],'new':3})
    assert {c['path'] for c in changes}=={'$.a','$.b[0]','$.old','$.new'}
    assert helper.json_changes({'x':[1]},{'x':[1,2]})[0]['change']=='array_length'


def test_native_copy_inspection_readonly_and_no_implicit_equivalence(tmp_path,fixture):
    engine,_,source,_=fixture
    root,_=generate(source,tmp_path/'out',engine_path=engine,
                    overrides={'target':'wallpaper-engine','parallax_enabled':False})
    copy=tmp_path/'qa';shutil.copytree(root/'wallpaper-engine',copy)
    original=sha256(root/'manifest.json')
    result=helper.inspect_copy(root,copy)
    assert result['identical_resources'] and not result['different_resources']
    assert result['runtime_status']=='not_tested'
    scene=read_json(copy/'scene.json');scene['general']['zoom']=.999999999
    write_json(copy/'scene.json',scene);before=sha256(copy/'scene.json')
    result=helper.inspect_copy(root,copy)
    assert len(result['different_resources'])==1
    assert result['different_resources'][0]['json_changes'][0]['path']=='$.general.zoom'
    assert result['runtime_status']=='not_tested' and sha256(root/'manifest.json')==original
    assert sha256(copy/'scene.json')==before
    (copy/'project.json').unlink()
    result=helper.inspect_copy(root,copy)
    assert any(c.get('change')=='missing' for c in result['different_resources'])
    (root/'wallpaper-engine/scene.json').write_text('{}')
    with pytest.raises(ValueError,match='Source resource'):helper.inspect_copy(root,copy)
