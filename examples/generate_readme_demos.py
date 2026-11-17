"""Capture real Web runtime demos from the published photo/AI preview assets.

The depth map was estimated by Depth Anything V2 Small. Portrait masks were
imported from the accepted model-derived, user-corrected regions. See the asset
notes for image permissions. Reproduction needs dev dependencies and Chromium.
"""
import argparse
import io
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence
from playwright.sync_api import sync_playwright

from static2live.pipeline import generate
from static2live.storage import read_json, sha256, write_json


def write_gif(frames, destination, durations):
    width = min(768, frames[0].width)
    size = (width, round(width * 9 / 16))
    thumbnails = [frame.resize(size, Image.Resampling.LANCZOS) for frame in frames]
    palette = thumbnails[0].quantize(colors=128)
    encoded = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in thumbnails]
    encoded[0].save(destination, save_all=True, append_images=encoded[1:],
                    duration=durations, loop=0, optimize=True)


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
        frames.append(Image.open(io.BytesIO(page.screenshot())).convert('RGB'))
    difference = float(np.abs(np.asarray(frames[0], dtype=float)
                              - np.asarray(frames[15], dtype=float)).mean())
    if difference == 0:
        raise ValueError('Runtime capture has no motion: ' + kind)
    webp = destination.with_suffix('.webp')
    frames[0].save(webp, save_all=True, append_images=frames[1:],
                   duration=[80, 80, 90] * 20, loop=0, quality=90, method=4, minimize_size=True)
    with Image.open(webp) as animation:
        gif_frames, durations = [], []
        for frame in ImageSequence.Iterator(animation):
            gif_frames.append(frame.convert('RGB'))
            durations.append(frame.info['duration'])
    write_gif(gif_frames, destination, durations)
    return {'frames': len(frames), 'duration_seconds': 5,
            'mean_frame_difference': difference, 'sha256': sha256(destination),
            'webp_sha256': sha256(webp)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', default='assets/demo')
    parser.add_argument('--work', default='local-acceptance/readme-demos')
    parser.add_argument('--output', default='assets/demo')
    parser.add_argument('--width', type=int, default=960)
    args = parser.parse_args()
    assets, work, output = (Path(value).resolve() for value in (args.assets, args.work, args.output))
    output.mkdir(parents=True, exist_ok=True)
    common = {'auto_plan': False, 'mode': 'lite', 'effects': [], 'parallax_enabled': False}
    projects = {}
    projects['depth'], _ = generate(assets / 'landscape-source.png', work / 'depth',
        depth_map=assets / 'depth-map.png', overrides={**common,
            'parallax_enabled': True, 'parallax': {'fraction': .006}})
    # Match the accepted 2048x1152 portrait amplitudes at the public preview size.
    with Image.open(assets / 'portrait-source.png') as image:
        scale = image.width / 2048
    portrait_options = {**common,
        'hair_sway': {'enabled': True, 'amplitude_px': 2.5 * scale, 'period_seconds': 5.5, 'phase': .3},
        'cloth_sway': {'enabled': True, 'amplitude_px': 3 * scale, 'period_seconds': 6.5, 'phase': 1.3},
        'effects': [{'type': 'dust', 'count': 72, 'intensity': .35,
                     'speed_px_s': 9 * scale, 'size_px': 2 * scale, 'exclude_person': True}]}
    projects['portrait'], _ = generate(assets / 'portrait-source.png', work / 'portrait',
        regions_path=assets / 'portrait-regions.json', overrides=portrait_options)
    projects['particles'], _ = generate(assets / 'particle-source.png', work / 'particles',
        overrides={**common, 'effects': [{'type': 'snow', 'count': 110,
            'intensity': .7, 'speed_px_s': 55, 'size_px': 3}]})
    metadata = {'runtime': 'Static2Live Web', 'dimensions': [args.width, round(args.width * 9 / 16)],
        'gif_dimensions': [min(768, args.width), round(min(768, args.width) * 9 / 16)],
        'capture': 'Chromium + SwiftShader; 60 actual rendered frames; 12 FPS; 5 seconds',
        'depth_source': 'Depth Anything V2 Small model inference; supplied map for reproduction',
        'depth_model': read_json(assets / 'depth-provenance.json'),
        'portrait_regions': 'Model-derived, user-corrected regions imported into Lite',
        'image_sources': {'landscape': 'AI-generated image, built-in image_gen',
            'particles': 'AI-generated image, built-in image_gen',
            'portrait': 'User-supplied photograph; authorized project README display'},
        'source_sha256': {name: sha256(assets / name) for name in
            ['landscape-source.png', 'particle-source.png', 'portrait-source.png', 'depth-map.png']},
        'demos': {}}
    names = {'depth': 'depth-parallax.gif', 'portrait': 'portrait-motion.gif',
             'particles': 'particle-effects.gif'}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        page = browser.new_page(viewport={'width': args.width, 'height': round(args.width * 9 / 16)})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for kind, project in projects.items():
            metadata['demos'][kind] = capture(page, project, output / names[kind], kind)
            metadata['demos'][kind]['manifest_sha256'] = sha256(project / 'manifest.json')
        browser.close()
    if errors:
        raise ValueError(errors)
    write_json(output / 'provenance.json', metadata)
    print(output)


if __name__ == '__main__':
    main()
