"""Capture deterministic review frames for an explicitly supplied local output."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

p=argparse.ArgumentParser();p.add_argument('directory');args=p.parse_args()
root=Path(args.directory).resolve()
with sync_playwright() as pw:
    browser=pw.chromium.launch(args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    page=browser.new_page(viewport={'width':960,'height':540})
    page.goto((root/'index.html').as_uri())
    page.wait_for_function('window.static2live?.status === "ready"')
    page.evaluate('static2live.setParallaxEnabled(false)')
    for t in (0,2):
        page.evaluate('(t)=>static2live.setTime(t)',t);page.wait_for_timeout(150)
        page.screenshot(path=str(root/f'review-time-{t}.png'))
    browser.close()
