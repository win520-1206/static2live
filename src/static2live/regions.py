"""Import masks without guessing identity, orientation or semantic meaning."""
import base64
import io
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from .effects import REGIONS
from .storage import read_json, safe_resource, sha256, write_json
from .framing import crop_box, frame_record


def canonical_image(path,max_edge,framing=None):
    with Image.open(path) as opened:
        opened.load()
        corrected=ImageOps.exif_transpose(opened).convert('RGBA')
        original_size=corrected.size
        flattened=Image.new('RGBA',original_size,(0,0,0,255));flattened.alpha_composite(corrected)
        image=flattened.convert('RGB')
        box=crop_box(original_size,framing)
        if box is not None:image=image.crop(box)
        image.thumbnail((max_edge,max_edge),Image.Resampling.LANCZOS)
    return image,original_size


def load_regions(path,image_size,source_sha,original_size=None,crop=None):
    path=Path(path)
    bundle=read_json(path)
    if bundle.get('version') not in ('0.2','0.4') or bundle.get('coordinates')!='top-left-normalized':
        raise ValueError('区域文件必须是 0.2/0.4 且采用 top-left-normalized 坐标')
    if bundle.get('input_sha256')!=source_sha:
        raise ValueError('区域绑定的输入哈希与当前图片不匹配')
    canvas=bundle.get('canvas',{})
    size=(canvas.get('width'),canvas.get('height'))
    if any(type(x)!=int or not 1<=x<=8192 for x in size):
        raise ValueError('区域画布尺寸无效')
    already_framed='input_frame' in bundle
    if already_framed and bundle['input_frame']!=frame_record(original_size,crop):
        raise ValueError('已裁切标注与当前裁切框不一致，不能重建缺失区域；请导入原始全图标注')
    reference=image_size if already_framed or crop is None else original_size
    if abs(size[0]/size[1]-reference[0]/reference[1])>max(1/size[1],1/reference[1]):
        raise ValueError('区域画布比例与输入不匹配，不猜测裁切或错位')
    entries=bundle.get('regions')
    if not isinstance(entries,list) or len(entries)>len(REGIONS):
        raise ValueError('区域列表无效')
    masks,records={},{}
    for item in entries:
        key=item.get('id')
        if key not in REGIONS or key in masks:
            raise ValueError('区域类别无效或重复')
        origin=item.get('source')
        if origin not in ['manual','imported','rule','model']:
            raise ValueError('必须记录区域来源')
        if item.get('confirmed') is not True:
            raise ValueError('区域或规则候选未确认，不能应用')
        asset=item.get('asset','')
        if asset.startswith('data:image/png;base64,'):
            raw=base64.b64decode(asset.split(',',1)[1],validate=True)
            if len(raw)>64*1024*1024: raise ValueError('蒙版超过大小限制')
            data=io.BytesIO(raw)
        else: data=safe_resource(path.parent,asset)
        with Image.open(data) as opened:
            if opened.size!=size: raise ValueError('蒙版与标注画布尺寸不匹配')
            if opened.mode in ['RGB','RGBA']:
                array=np.asarray(opened)
                if not np.array_equal(array[:,:,0],array[:,:,1]) or not np.array_equal(array[:,:,0],array[:,:,2]):
                    raise ValueError('蒙版须为灰度而非彩色标注截图')
                if opened.mode=='RGBA' and not np.all(array[:,:,3]==255):
                    raise ValueError('导入灰度 PNG 须不透明，白为选中黑为未选中')
                opened=opened.convert('L')
            if opened.mode!='L': raise ValueError('蒙版须为 8 位灰度')
            mask=opened
            if crop is not None and not already_framed:
                # Boundaries use the same normalized source frame, including
                # lower-resolution imported masks. Never infer a new region.
                scaled=tuple(round(v*size[i%2]/original_size[i%2]) for i,v in enumerate(crop))
                if scaled[2]<=scaled[0] or scaled[3]<=scaled[1]:raise ValueError('标注分辨率不足以表达裁切区域')
                mask=opened.crop(scaled)
            masks[key]=mask.resize(image_size,Image.Resampling.BILINEAR).copy()
        records[key]={k:v for k,v in item.items() if k!='asset'}
    return masks,records,{'backend':'imported-regions','file_sha256':sha256(path)}


def save_regions(root,masks,records,input_sha,size,input_frame=None):
    root=Path(root);directory=root/'assets/masks';directory.mkdir(parents=True,exist_ok=True)
    output={}
    for key,mask in masks.items():
        relative=f'assets/masks/{key}.png';mask.save(root/relative)
        output[key]={**records[key],'asset':relative,'coverage':float(np.asarray(mask).mean()/255)}
    bundle={'version':'0.2','coordinates':'top-left-normalized','input_sha256':input_sha,
            'canvas':{'width':size[0],'height':size[1]},'regions':[]}
    if input_frame is not None:bundle['input_frame']=input_frame
    # Paths are relative to assets/regions.json, not wallpaper root.
    bundle['regions']=[{**r,'asset':f'masks/{k}.png'} for k,r in output.items()]
    write_json(root/'assets/regions.json',bundle)
    return output
