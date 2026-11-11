"""Run explicitly with --browser-tests after installing Playwright Chromium."""
import os
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from static2live.pipeline import generate
from static2live.browser_check import check_browser

pytestmark=pytest.mark.skipif(os.environ.get('STATIC2LIVE_BROWSER_TESTS')!='1',reason='explicit browser opt-in required')


def fixture_images(tmp_path):
    spec=importlib.util.spec_from_file_location('fixture',Path(__file__).parents[1]/'examples/generate_fixture.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.create_fixture(tmp_path/'source')


def test_depth_driven_displacement(tmp_path):
    from playwright.sync_api import sync_playwright
    image,depth=fixture_images(tmp_path)
    root,_=generate(image,tmp_path/'out',depth_map=depth,overrides={'parallax':{'fraction':.01}})
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':512,'height':256})
        page.goto((root/'index.html').as_uri())
        page.wait_for_function("window.static2live && static2live.status==='ready'")
        def sample(x):
            page.mouse.move((x+1)*255.5,128)
            page.wait_for_function('([x])=>Math.abs(static2live.pointer[0]-x)<.003',arg=[x*.998046875])
            return np.array(page.evaluate('static2live.readPixels()'),dtype='uint8').reshape(256,512,4)
        center=sample(0);left=sample(-1);right=sample(1)
        def shift(frame,row):
            reference=center[row,:,0].astype(float)
            profile=frame[row,90:420,0].astype(float)
            axis=np.arange(90,420)
            candidates=np.arange(-6,6.01,.05)
            losses=[np.mean((np.interp(axis-d,np.arange(512),reference)-profile)**2) for d in candidates]
            return float(candidates[np.argmin(losses)])
        near_left,near_right=shift(left,180),shift(right,180)
        far_left,far_right=shift(left,70),shift(right,70)
        assert near_left < -2 and near_right > 2
        assert abs(far_left) < abs(near_left)/2 and abs(far_right) < abs(near_right)/2
        assert np.all(left[:,:,3]==255) and np.all(right[:,:,3]==255)
        browser.close()


@pytest.mark.parametrize('fraction',[0,.01])
def test_browser_acceptance(tmp_path,fraction):
    image,depth=fixture_images(tmp_path)
    root,_=generate(image,tmp_path/'out',depth_map=depth,overrides={'parallax':{'fraction':fraction}})
    report=check_browser(root)
    assert next(c for c in report['checks'] if c['name']=='browser_runtime')['status']=='passed',report
    assert report['status']=='not_tested' # Do not fabricate human visual approval.
