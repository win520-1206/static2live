"""Read-only native hair transport diagnostics for explicitly supplied folders.

Usage: python diagnose_hair.py VERSION_OR_NATIVE_FOLDER [ANOTHER_FOLDER ...]
No engine discovery, writes, UI operations or runtime acceptance records.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from static2live.storage import sha256


def inspect(folder):
    root=Path(folder).resolve(strict=True)
    if (root/'wallpaper-engine').is_dir():root=root/'wallpaper-engine'
    resources={}
    for relative in ['shaders/effects/s2l_human.vert','shaders/effects/s2l_human.frag',
                     'materials/s2l_hair_weight.png','materials/s2l_hair_weight.tex',
                     'materials/s2l_protected.png']:
        path=root/relative
        entry={'sha256':sha256(path)}
        if path.suffix=='.png':
            with Image.open(path) as im:a=np.asarray(im.convert('L'))
            nonzero=a[a>0]
            entry.update(size=list(a.shape[::-1]),nonzero=len(nonzero),maximum=int(a.max()),
                percentiles=np.percentile(nonzero,[10,50,90,99]).tolist() if len(nonzero) else [])
            entry['row_bands']=[{'range':[lo,hi],
                'active':int(np.count_nonzero(a[int(a.shape[0]*lo):int(a.shape[0]*hi)])),
                'maximum':int(a[int(a.shape[0]*lo):int(a.shape[0]*hi)].max())}
                for lo,hi in [(0,.3),(.3,.5),(.5,.75),(.75,1)]]
        resources[relative]=entry
    scene=json.loads((root/'scene.json').read_text(encoding='utf8'))
    props=json.loads((root/'project.json').read_text(encoding='utf8'))['general']['properties']
    return {'folder':str(root),'resources':resources,
        'images':[{'image':o['image'],'visible':o.get('visible'),'scale':o.get('scale'),
                   'effects':o.get('effects')} for o in scene['objects'] if 'image' in o],
        'hair_properties':{k:v for k,v in props.items() if 'hair' in k},
        'runtime_status':'not_tested','note':'File data only; actual GPU motion and visibility require observation'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folders',nargs='+')
    args=parser.parse_args()
    print(json.dumps([inspect(p) for p in args.folders],ensure_ascii=False,indent=2))
