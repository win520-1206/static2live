"""CC0 procedural landscape + explicit known masks. Not a real/model-analyzed photo."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
import yaml
from static2live.storage import sha256,write_json
from static2live.pipeline import generate


def create_scene(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    w,h=768,512;y,x=np.indices((h,w));gradient=y/h
    rgb=np.stack([38+gradient*40,64+gradient*55,105+gradient*50],axis=2).astype('uint8')
    image=Image.fromarray(rgb);draw=ImageDraw.Draw(image)
    masks={k:Image.new('L',(w,h),0) for k in ['sky','water','cloud','glow']}
    ImageDraw.Draw(masks['sky']).rectangle((0,0,w,330),fill=255)
    ImageDraw.Draw(masks['water']).rectangle((0,330,w,h),fill=255)
    draw.polygon([(0,330),(0,275),(170,200),(285,305),(450,250),(610,315),(768,230),(768,330)],fill='#253a48')
    draw.rectangle((0,330,w,h),fill='#416473')
    for row in range(337,h,9):
        for start in range(0,w,90):
            offset=int(15*np.sin(row*.14+start*.05));draw.line((start+offset,row,start+offset+45,row),fill='#597c88',width=1)
    for cx,cy in [(150,90),(325,140),(610,72)]:
        for dx,dy,rx,ry in [(-42,8,45,19),(0,-4,42,24),(40,7,47,17)]:
            box=(cx+dx-rx,cy+dy-ry,cx+dx+rx,cy+dy+ry)
            draw.ellipse(box,fill='#c4d3dc');ImageDraw.Draw(masks['cloud']).ellipse(box,fill=255)
    draw.ellipse((472,126,512,166),fill='#f4c88b');ImageDraw.Draw(masks['glow']).ellipse((472,126,512,166),fill=255)
    source=root/'landscape.png';image.save(source)
    entries=[]
    for key,mask in masks.items():
        name=f'{key}.png';mask.save(root/name)
        entries.append({'id':key,'asset':name,'source':'imported','confirmed':True,'note':'explicit CC0 procedural fixture; not automatic segmentation'})
    regions=root/'regions.json';write_json(regions,{'version':'0.2','coordinates':'top-left-normalized','input_sha256':sha256(source),
        'canvas':{'width':w,'height':h},'regions':entries})
    return source,regions


def demo(root):
    root=Path(root);source,regions=create_scene(root/'source');outputs={}
    for kind in ['rain','snow','dust','fog','glow','cloud_drift']:
        effect={'type':kind}
        if kind=='fog':effect.update(region='sky',intensity=.3)
        if kind=='glow':effect.update(intensity=.7,color='#fff5ce')
        if kind=='cloud_drift':effect.update(amplitude_px=3,intensity=.7)
        config={'mode':'lite','parallax_enabled':False,'effects':[effect]}
        cfg=root/f'{kind}.yaml';cfg.write_text(yaml.safe_dump(config),encoding='utf8')
        output,report=generate(source,root/'wallpapers'/kind,config_path=cfg,regions_path=regions)
        outputs[kind]={'output':str(output.resolve()),'status':report['status']}
    write_json(root/'outputs.json',outputs)
    return outputs


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='local-acceptance/v02-demo')
    print(demo(parser.parse_args().output))
