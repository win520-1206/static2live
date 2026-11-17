"""Capture real Web runtime demos from the published photo/AI preview assets.

The depth map was estimated by Depth Anything V2 Small. Portrait masks were
imported from the accepted model-derived, user-corrected regions. See the asset
notes for image permissions. Reproduction needs dev dependencies and Chromium.
"""
import argparse
import io
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
    duration = {'depth': 8, 'portrait': 5, 'particles': 5}[kind]
    for frame in range(duration * 12):
        seconds = frame / 12
        page.evaluate('t=>{static2live.setTime(t);static2live.setPointer(0,0);}', seconds)
        page.wait_for_function('t=>Math.abs(static2live.time-t)<.0001 && static2live.pointer.every(v=>Math.abs(v)<.001)', arg=seconds)
        page.wait_for_timeout(85)
        frames.append(Image.open(io.BytesIO(page.screenshot())).convert('RGB'))
    difference = float(np.abs(np.asarray(frames[0], dtype=float)
                              - np.asarray(frames[15], dtype=float)).mean())
    if difference == 0:
        raise ValueError('Runtime capture has no motion: ' + kind)
    webp = destination.with_suffix('.webp')
    frames[0].save(webp, save_all=True, append_images=frames[1:],
                   duration=[80, 80, 90] * (len(frames) // 3), loop=0, quality=90, method=4, minimize_size=True)
    with Image.open(webp) as animation:
        gif_frames, durations = [], []
        for frame in ImageSequence.Iterator(animation):
            gif_frames.append(frame.convert('RGB'))
            durations.append(frame.info['duration'])
    write_gif(gif_frames, destination, durations)
    return {'frames': len(frames), 'duration_seconds': duration,
            'mean_frame_difference': difference, 'sha256': sha256(destination),
            'webp_sha256': sha256(webp)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', default='assets/demo')
    parser.add_argument('--work', default='local-acceptance/readme-demos')
    parser.add_argument('--output', default='assets/demo')
    parser.add_argument('--width', type=int, default=960)
    parser.add_argument('--only', choices=['depth', 'portrait', 'particles'], help='Update one demo and retain other provenance entries')
    args = parser.parse_args()
    assets, work, output = (Path(value).resolve() for value in (args.assets, args.work, args.output))
    output.mkdir(parents=True, exist_ok=True)
    common = {'auto_plan': False, 'mode': 'lite', 'effects': [], 'parallax_enabled': False}
    projects = {}
    projects['depth'], _ = generate(assets / 'landscape-source.png', work / 'depth',
        depth_map=assets / 'depth-map.png', regions_path=assets / 'landscape-regions.json',
        overrides={**common, 'parallax_enabled': True, 'parallax': {'fraction': .002},
            'shader': {'preset': 'water_ripple', 'strength': .9, 'amplitude_px': 4, 'period_seconds': 4},
            'effects': [{'type': 'cloud_drift', 'intensity': .9, 'amplitude_px': 8, 'period_seconds': 8},
                        {'type': 'foliage_sway', 'intensity': .9, 'amplitude_px': 4, 'period_seconds': 8/3}]})
    # Match the accepted 2048x1152 portrait amplitudes at the public preview size.
    with Image.open(assets / 'portrait-source.png') as image:
        scale = image.width / 2048
    portrait_options = {**common,
        'hair_sway': {'enabled': True, 'amplitude_px': 2.5 * scale, 'period_seconds': 5.5, 'phase': .3},
        'cloth_sway': {'enabled': True, 'amplitude_px': 3 * scale, 'period_seconds': 6.5, 'phase': 1.3},
        'effects': [{'type': 'dust', 'count': 90, 'intensity': .8, 'softness': .8,
                     'speed_px_s': 9 * scale, 'size_px': 8 * scale, 'exclude_person': True}]}
    projects['portrait'], _ = generate(assets / 'portrait-source.png', work / 'portrait',
        regions_path=assets / 'portrait-regions.json', overrides=portrait_options)
    projects['particles'], _ = generate(assets / 'particle-source.png', work / 'particles',
        overrides={**common, 'effects': [{'type': 'snow', 'count': 110,
            'intensity': .7, 'speed_px_s': 55, 'size_px': 3}]})
    previous = read_json(output / 'provenance.json') if (output / 'provenance.json').exists() else {}
    metadata = {'runtime': 'Static2Live Web', 'dimensions': [args.width, round(args.width * 9 / 16)],
        'gif_dimensions': [min(768, args.width), round(min(768, args.width) * 9 / 16)],
        'capture': 'Chromium + SwiftShader; 12 FPS fixed-time samples; duration recorded per demo',
        'lake_regions': 'Manually defined water, distant cloud/mist, and protected foreground/cabin',
        'lake_preview_pointer': 'Centered to demonstrate autonomous water and cloud motion',
        'depth_source': 'Depth Anything V2 Small model inference; supplied map for reproduction',
        'depth_model': read_json(assets / 'depth-provenance.json'),
        'portrait_regions': 'Model-derived, user-corrected regions imported into Lite',
        'image_sources': {'landscape': 'AI-generated image, built-in image_gen',
            'particles': 'AI-generated image, built-in image_gen',
            'portrait': 'User-supplied photograph; authorized project README display'},
        'source_sha256': {name: sha256(assets / name) for name in
            ['landscape-source.png', 'particle-source.png', 'portrait-source.png', 'depth-map.png']},
        'demos': previous.get('demos', {})}
    names = {'depth': 'depth-parallax.gif', 'portrait': 'portrait-motion.gif',
             'particles': 'particle-effects.gif'}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        page = browser.new_page(viewport={'width': args.width, 'height': round(args.width * 9 / 16)})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for kind, project in projects.items():
            if args.only and kind != args.only:
                continue
            metadata['demos'][kind] = capture(page, project, output / names[kind], kind)
            metadata['demos'][kind]['manifest_sha256'] = sha256(project / 'manifest.json')
        browser.close()
    if errors:
        raise ValueError(errors)
    write_json(output / 'provenance.json', metadata)
    print(output)


if __name__ == '__main__':
    main()
