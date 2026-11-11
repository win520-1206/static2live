"""V0.5 offline editing; browser fixtures are synthetic, not photo visual QA."""
import json
import os
import re
import numpy as np
import pytest
from PIL import Image
from static2live import __version__
from static2live.editor import export_editor
from static2live.pipeline import generate
from static2live.regions import load_regions
from static2live.storage import read_json, write_json, sha256
from test_v04 import inputs, config
from test_v02 import browser_launch


def test_editor_human_bundle_and_hashes(tmp_path):
    source, regions = inputs(tmp_path)
    before = sha256(source)
    out = export_editor(source, tmp_path/'annotations', regions_path=regions)
    manifest = read_json(out/'manifest.json')
    assert manifest['editor_version'] == '0.5'
    assert manifest['static2live_version'] == __version__
    assert all(sha256(out/k) == v for k,v in manifest['resources'].items())
    boot = json.loads(re.search(r'<script id="editor-data" type="application/json">(.*?)</script>', (out/'index.html').read_text('utf8')).group(1))
    assert 'protected' in boot['editable_regions'] and 'hair_sway' not in boot['editable_regions']
    assert {r['id'] for r in boot['regions']} == {'hair','protected'}
    assert sha256(source) == before


@pytest.mark.skipif(os.getenv('STATIC2LIVE_BROWSER_TESTS') != '1', reason='browser opt-in')
def test_human_editor_roundtrip(tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright
    source, regions = inputs(tmp_path); before = sha256(source)
    editor = export_editor(source,tmp_path/'annotations',regions_path=regions)
    for backend in ('ModelHumanParsing','ModelSegmentation','ModelDepth'):
        monkeypatch.setattr('static2live.pipeline.'+backend+'.predict', lambda *a,**k: pytest.fail('Lite inferred'))
    with sync_playwright() as pw:
        browser = browser_launch(pw); page = browser.new_page(viewport={'width':1100,'height':1000})
        errors = []; page.on('pageerror',lambda e: errors.append(str(e)))
        page.goto((editor/'index.html').as_uri()); page.wait_for_function('window.static2liveEditor?.ready')
        original = page.evaluate('static2liveEditor.exportBundle()')
        assert {r['id'] for r in original['regions']} == {'hair','protected'}
        page.select_option('#category','hair'); page.select_option('#tool','animate')
        page.locator('#paint').scroll_into_view_if_needed()
        box = page.locator('#paint').bounding_box()
        page.mouse.click(box['x']+box['width']*.2,box['y']+box['height']*.75)
        edited = page.evaluate('static2liveEditor.exportBundle()')
        assert edited != original
        page.click('#undo'); assert page.evaluate('static2liveEditor.exportBundle()') == original
        page.click('#redo'); assert page.evaluate('static2liveEditor.exportBundle()') == edited
        page.select_option('#tool','protect'); page.locator('#paint').scroll_into_view_if_needed()
        box = page.locator('#paint').bounding_box()
        page.mouse.click(box['x']+box['width']*.3,box['y']+box['height']*.4)
        protected = page.evaluate('static2liveEditor.exportBundle()')
        assert next(r for r in protected['regions'] if r['id']=='protected')['asset'] != next(r for r in original['regions'] if r['id']=='protected')['asset']
        page.select_option('#category','hair'); page.click('#clear')
        empty = page.evaluate('static2liveEditor.exportBundle()')
        path = tmp_path/'empty.json'; write_json(path,empty)
        masks,_,_ = load_regions(path,(256,192),before)
        assert np.asarray(masks['hair']).max() == 0
        page.click('#undo'); assert page.evaluate('static2liveEditor.exportBundle()') == protected
        for zoom in ['1','2','4','fit']:
            page.select_option('#zoom',zoom)
            box = page.locator('#paint').bounding_box()
            uv = page.evaluate('([x,y])=>static2liveEditor.normalizedPoint(x,y)',[box['x']+box['width']*.3,box['y']+box['height']*.4])
            assert np.allclose(uv,[.3,.4])
        # Invalid import is atomic; no partially decoded masks leak into current work.
        wrong = {**protected,'input_sha256':'0'*64}
        with pytest.raises(Exception): page.evaluate('(b)=>static2liveEditor.importBundle(b)',wrong)
        assert page.evaluate('static2liveEditor.exportBundle()') == protected
        # A later invalid region cannot commit earlier decoded regions.
        partial = {**protected, 'regions':[protected['regions'][0], {**protected['regions'][1], 'asset':'data:image/png;base64,broken'}]}
        with pytest.raises(Exception): page.evaluate('(b)=>static2liveEditor.importBundle(b)',partial)
        assert page.evaluate('static2liveEditor.exportBundle()') == protected
        # Derived weights never become paintable sources or get re-exported.
        with_derived = {**protected, 'regions':[*protected['regions'], {**protected['regions'][0], 'id':'hair_sway'}]}
        page.evaluate('(b)=>static2liveEditor.importBundle(b)',with_derived)
        assert page.evaluate('static2liveEditor.exportBundle()') == protected
        assert '派生' in page.locator('#status').inner_text()
        saved = tmp_path/'edited.json'; write_json(saved,protected)
        with page.expect_download() as download: page.click('#save')
        download.value.save_as(str(tmp_path/'download.json'))
        assert read_json(tmp_path/'download.json') == protected
        assert not errors
        browser.close()
    root,report = generate(source,tmp_path/'wallpapers',overrides=config(),regions_path=saved)
    assert report['structural_status'] == 'passed' and report['status'] == 'not_tested'
    with Image.open(root/'assets/masks/protected.png') as p, Image.open(root/'assets/masks/hair_sway.png') as w:
        assert not np.any(np.asarray(w)[np.asarray(p)>0])
    assert sha256(source) == before
