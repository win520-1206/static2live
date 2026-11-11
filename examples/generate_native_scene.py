"""CC0 native foliage fixture; explicit imported mask, not automatic parsing."""
from pathlib import Path
from PIL import Image,ImageDraw
from generate_scene import create_scene
from static2live.storage import read_json,write_json,sha256
from static2live.pipeline import generate

def demo(root):
    root=Path(root);source,regions=create_scene(root/'source')
    with Image.open(source) as opened:image=opened.convert('RGB')
    draw=ImageDraw.Draw(image);draw.rectangle((98,275,108,365),fill='#634631')
    leaves=Image.new('L',image.size,0);mask=ImageDraw.Draw(leaves)
    for box in [(60,240,125,310),(88,225,151,295),(90,268,156,320)]:
        draw.ellipse(box,fill='#50734e');mask.ellipse(box,fill=255)
    image.save(source);leaves.save(source.parent/'other.png')
    bundle=read_json(regions);bundle['input_sha256']=sha256(source)
    bundle['regions'].append({'id':'other','source':'imported','asset':'other.png','confirmed':True,
        'note':'CC0 procedural explicit foliage mask, not automatic plant/hair detection'})
    write_json(regions,bundle)
    output,report=generate(source,root/'wallpapers',regions_path=regions,
        overrides={'target':'wallpaper-engine','parallax_enabled':False,'native_sway':True,'sway_amplitude_px':1,
            'effects':[{'type':'dust'}]})
    print(output,report['structural_status'],report['status'])

if __name__=='__main__':demo('local-acceptance/v03-foliage')
