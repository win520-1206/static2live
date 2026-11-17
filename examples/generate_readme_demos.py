"""Record actual Web runtime GIFs from CC0 procedural fixtures.

The supplied depth and regions are explicit test data. Reproduction requires
the dev extra and an installed Playwright Chromium, but no model downloads.
"""
import argparse
import io
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from generate_scene import create_scene
from static2live.pipeline import generate
from static2live.storage import sha256, write_json


def create_portrait(root):
    root.mkdir(parents=True, exist_ok=True)
    size = (768, 512)
    image = Image.new('RGB', size, '#b39a82')
    draw = ImageDraw.Draw(image)
    for x in range(0, 768, 32):
        draw.rectangle((x, 0, x + 15, 512), fill='#ad937b')
    draw.ellipse((35, 55, 230, 250), fill='#d2b99a')
    draw.rounded_rectangle((40, 370, 350, 430), radius=14, fill='#6c5949')
    draw.rectangle((82, 428, 100, 512), fill='#655346')
    masks = {name: Image.new('L', size) for name in ('hair', 'cloth', 'protected')}
    hair_shape = [(421, 115), (455, 59), (545, 43), (624, 78), (657, 159),
                  (645, 260), (677, 347), (640, 421), (583, 430), (555, 364),
                  (482, 374), (414, 434), (385, 390), (397, 308), (395, 210)]
    cloth_shape = [(458, 350), (552, 344), (607, 377), (669, 512), (345, 512), (401, 389)]
    draw.polygon(cloth_shape, fill='#f2e5cf')
    ImageDraw.Draw(masks['cloth']).polygon(cloth_shape, fill=255)
    for start in range(385, 640, 22):
        draw.line((500, 367, start, 512), fill='#d4c3aa', width=2)
    draw.polygon(hair_shape, fill='#4b3229')
    ImageDraw.Draw(masks['hair']).polygon(hair_shape, fill=255)
    draw.rounded_rectangle((484, 273, 555, 372), radius=20, fill='#d8aa8d')
    draw.ellipse((447, 112, 602, 317), fill='#e8bda0')
    for x in (483, 558):
        draw.arc((x - 18, 196, x + 17, 217), 180, 350, fill='#563b31', width=3)
        draw.ellipse((x - 5, 203, x + 3, 215), fill='#322b28')
    draw.line((522, 213, 517, 250, 527, 251), fill='#c49377', width=2)
    draw.arc((492, 250, 552, 282), 15, 165, fill='#a65d50', width=3)
    draw.polygon([(439, 169), (456, 106), (519, 79), (583, 104),
                  (610, 159), (559, 144), (522, 113), (481, 147)], fill='#5c3b2c')
    for offset in range(0, 42, 5):
        draw.line([(447 + offset // 2, 132), (416 + offset // 3, 248),
                   (421 + offset // 2, 331), (392 + offset, 413)], fill='#956746', width=2)
        draw.line([(578 + offset, 145), (619 + offset // 3, 250),
                   (611 + offset, 340), (587 + offset, 421)], fill='#8c6042', width=2)
    guard = ImageDraw.Draw(masks['protected'])
    guard.ellipse((443, 108, 606, 323), fill=255)
    guard.rectangle((480, 285, 559, 377), fill=255)
    source = root / 'portrait-source.png'
    image.save(source)
    entries = []
    for kind, mask in masks.items():
        mask.save(root / (kind + '.png'))
        entries.append({'id': kind, 'asset': kind + '.png', 'source': 'manual',
                        'confirmed': True, 'note': 'CC0 procedural fixture; explicit geometry'})
    regions = root / 'regions.json'
    write_json(regions, {'version': '0.4', 'coordinates': 'top-left-normalized',
                        'input_sha256': sha256(source), 'canvas': {'width': 768, 'height': 512},
                        'regions': entries})
    return source, regions


def capture(page, project, destination, kind):
    page.goto((project / 'index.html').as_uri())
    page.wait_for_function('window.static2live?.status === "ready"')
    frames = []
    for frame in range(60):
        seconds = frame / 12
        pointer = math.sin(seconds * 2 * math.pi / 5) if kind == 'depth' else 0
        page.evaluate('([t,x])=>{static2live.setTime(t);static2live.setPointer(x,0);}',
                      [seconds, pointer])
        page.wait_for_function('x=>Math.abs(static2live.pointer[0]-x)<.001', arg=pointer)
        page.wait_for_timeout(85)
        screenshot = page.screenshot()
        frames.append(Image.open(io.BytesIO(screenshot)).convert('RGB'))
    difference = np.abs(np.asarray(frames[0], dtype=float) - np.asarray(frames[15], dtype=float)).mean()
    if difference == 0:
        raise ValueError('Runtime capture has no motion: ' + kind)
    # Frames are captured from the renderer. Pillow only encodes the GIF.
    palette = frames[0].quantize(colors=128)
    encoded = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    encoded[0].save(destination, save_all=True, append_images=encoded[1:],
                    duration=[80, 80, 90] * 20, loop=0, optimize=True)
    return {'frames': len(frames), 'duration_seconds': 5,
            'mean_frame_difference': float(difference), 'sha256': sha256(destination)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', default='local-acceptance/readme-demos')
    parser.add_argument('--output', default='assets/demo')
    args = parser.parse_args()
    work, output = Path(args.work).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source, _ = create_scene(work / 'landscape')
    yy, _ = np.indices((512, 768))
    depth = np.where(yy < 210, 15, np.where(yy < 330, 90, 160 + 95 * (yy - 330) / 182))
    depth_path = work / 'landscape/depth.png'
    Image.fromarray(depth.astype('uint8')).save(depth_path)
    portrait, regions = create_portrait(work / 'portrait')
    common = {'auto_plan': False, 'mode': 'lite', 'effects': [], 'parallax_enabled': False}
    projects = {}
    projects['depth'], _ = generate(source, work / 'depth', depth_map=depth_path,
        overrides={**common, 'parallax_enabled': True, 'parallax': {'fraction': .01}})
    projects['portrait'], _ = generate(portrait, work / 'portrait-project', regions_path=regions,
        overrides={**common, 'hair_sway': {'enabled': True, 'amplitude_px': 3.5, 'period_seconds': 5}})
    projects['particles'], _ = generate(source, work / 'particles', overrides={**common,
        'effects': [{'type': 'snow', 'count': 96, 'intensity': .7, 'speed_px_s': 22}]})
    Image.open(source).save(output / 'landscape-source.png')
    Image.open(portrait).save(output / 'portrait-source.png')
    metadata = {'license': 'CC0-1.0', 'runtime': 'Static2Live Web',
                'depth': 'explicit synthetic depth', 'regions': 'explicit procedural masks',
                'capture': 'Chromium + SwiftShader; 768x512; 60 actual rendered frames', 'demos': {}}
    names = {'depth': 'depth-parallax.gif', 'portrait': 'portrait-motion.gif',
             'particles': 'particle-effects.gif'}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        page = browser.new_page(viewport={'width': 768, 'height': 512})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for kind, project in projects.items():
            metadata['demos'][kind] = capture(page, project, output / names[kind], kind)
        browser.close()
    if errors:
        raise ValueError(errors)
    write_json(output / 'provenance.json', metadata)
    print(output)


if __name__ == '__main__':
    main()
