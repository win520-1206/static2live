"""Generate shareable synthetic native QA inputs; refuses existing output folders."""
import argparse
import math
from pathlib import Path
import numpy as np
from PIL import Image
import yaml
from static2live.storage import sha256
from static2live.regions import save_regions
from static2live.primitives import SHADER_MODES


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    parser.add_argument('--shader',choices=SHADER_MODES,default='neon_pulse')
    parser.add_argument('--with-audio',action='store_true',help='Explicitly include host audio response; does not play sound')
    diagnostic=parser.add_mutually_exclusive_group()
    diagnostic.add_argument('--diagnostic-grid',action='store_true',help='High-contrast grid for observing small local UV displacements; synthetic QA only')
    diagnostic.add_argument('--diagnostic-flat',action='store_true',help='Uniform dark RGB for isolating temporal light changes from texture/chromatic shifts')
    parser.add_argument('--amplitude-px',type=float,default=1.5,help='Canvas pixels, 0..3.6 (short-side 1%%); default 1.5')
    args=parser.parse_args()
    if not math.isfinite(args.amplitude_px) or not 0<=args.amplitude_px<=3.6:
        parser.error('--amplitude-px must be finite and within 0..3.6 canvas pixels')
    root=Path(args.output);root.mkdir(parents=True,exist_ok=False);(root/'assets').mkdir()
    width,height=640,360;y,x=np.mgrid[:height,:width]
    pixels=np.stack((40+x*120/width,35+y*110/height,45+(x+y)%120),axis=2).astype('uint8')
    if args.diagnostic_grid:
        # Thin lines reveal sub-grid motion against stationary outside/protected
        # areas. This changes only the procedural input, not renderer behavior.
        pixels[:]=[28,42,56]
        pixels[(x%16<2)|(y%16<2)]=[225,232,238]
        pixels[(x%64<2)|(y%64<2)]=[250,170,70]
    elif args.diagnostic_flat:
        pixels[:]=[12,12,12]
    Image.fromarray(pixels).save(root/'demo.png')
    masks={}
    for key in ('glow','water','other','protected'):
        a=np.zeros((height,width),dtype='uint8')
        selected=(x>width*.08)&(x<width*.92)&(y>height*.12)&(y<height*.88)
        if key=='protected':selected=(x>width*.42)&(x<width*.58)&(y>height*.32)&(y<height*.68)
        a[selected]=255;masks[key]=Image.fromarray(a)
    records={k:{'id':k,'source':'imported','confirmed':True,'note':'Procedural QA fixture, not semantic recognition'} for k in masks}
    save_regions(root,masks,records,sha256(root/'demo.png'),(width,height))
    config={'mode':'lite','target':'wallpaper-engine','parallax_enabled':False,'auto_plan':False,'effects':[],
        'shader':{'preset':args.shader,'strength':.7,'amplitude_px':args.amplitude_px,'period_seconds':4},
        'audio':{'enabled':args.with_audio,'strength':.15,'response_seconds':.15,'region':'glow'}}
    (root/'config.yaml').write_text(yaml.safe_dump(config),encoding='utf8')
    print(root.resolve())


if __name__=='__main__':main()
