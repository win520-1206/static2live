"""Synthetic pointer QA inputs, not model inference or runtime acceptance.

Left depth is far (black), right depth near (white), and the center is
protected. Thin grid lines reveal small pointer-driven displacements. No
time animation, particles, audio, private input, or model download is used.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image
import yaml

from static2live.regions import save_regions
from static2live.storage import sha256


def create(root, subject_anchor=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    (root / 'assets').mkdir()
    width, height = 640, 360
    y, x = np.mgrid[:height, :width]
    rgb = np.empty((height, width, 3), dtype='uint8')
    rgb[:] = (28, 42, 56)
    rgb[(x % 16 < 2) | (y % 16 < 2)] = (225, 232, 238)
    rgb[(x % 64 < 2) | (y % 64 < 2)] = (250, 170, 70)
    Image.fromarray(rgb).save(root / 'grid.png')
    depth = np.where(x < width // 2, 0, 255).astype('uint8')
    Image.fromarray(depth).save(root / 'depth.png')
    protected = np.zeros((height, width), dtype='uint8')
    protected[(x >= 272) & (x < 368) & (y >= 112) & (y < 248)] = 255
    masks={'protected':Image.fromarray(protected)}
    if subject_anchor:
        person=np.zeros((height,width),dtype='uint8');person[64:296,192:448]=255
        masks.update(person=Image.fromarray(person),glow=Image.new('L',(width,height),255))
    save_regions(root, masks,
        {key:{'id':key,'source':'imported','confirmed':True,
            'note':'Synthetic anchor fixture, not human parsing'} for key in masks},
        sha256(root / 'grid.png'), (width, height))
    config = {'mode': 'lite', 'target': 'wallpaper-engine', 'auto_plan': False,
        'parallax_enabled': True,
        'parallax': {'fraction': .01, 'response_seconds': .15},
        'effects': [], 'shader': {'preset': 'none'}, 'audio': {'enabled': False},
        'hair_sway': {'enabled': False}, 'cloth_sway': {'enabled': False}}
    if subject_anchor:
        # Select the combined native shader without time changes or audio.
        config['shader']={'preset':'warm_glow','strength':0,'amplitude_px':0}
    (root / 'config.yaml').write_text(yaml.safe_dump(config), encoding='utf8')
    return root.resolve()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--subject-anchor',action='store_true',help='Synthetic larger subject plus inner protection; selects combined shader at zero strength, no audio')
    args = parser.parse_args()
    print(create(args.output,args.subject_anchor))
