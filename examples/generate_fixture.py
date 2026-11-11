"""CC0 synthetic grid and explicit depth, NOT a substitute for model inference."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image


def create_fixture(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    y, x = np.indices((256, 512))
    # Smooth, non-periodic vertical bands facilitate subpixel displacement tests.
    value = (127 + 70*np.sin(x*.13) + 45*np.sin(x*.037)).clip(0,255).astype('uint8')
    rgb = np.stack([value, (value.astype(float)*.7).astype('uint8'), 255-value], axis=2)
    Image.fromarray(rgb).save(directory/'grid.png')
    depth = np.where(y < 128, 255, 0).astype('uint8')
    Image.fromarray(depth).save(directory/'depth.png')
    return directory/'grid.png', directory/'depth.png'


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='local-acceptance/fixture')
    args=parser.parse_args()
    print(create_fixture(args.output))
