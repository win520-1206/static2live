"""Offline source-mask editor; generated motion weights are never edited."""
import base64
import io
import json
from importlib.resources import files
from pathlib import Path
from .regions import canonical_image,load_regions
from .storage import allocate_version,sha256,write_json
from .effects import REGIONS
from . import __version__


def export_editor(input_path,output='annotations',max_edge=2048,regions_path=None):
    source=Path(input_path).resolve(strict=True)
    if not 64<=max_edge<=8192: raise ValueError('max_edge 需 64–8192')
    if any(Path(p).resolve().is_relative_to(Path(output).resolve()) for p in [source,regions_path] if p):
        raise ValueError('标注输出目录不能包含输入')
    image,original_size=canonical_image(source,max_edge);original_hash=sha256(source)
    masks,records={},{}
    if regions_path: masks,records,_=load_regions(regions_path,image.size,original_hash)
    def uri(image):
        stream=io.BytesIO();image.save(stream,format='PNG');return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode('ascii')
    boot={'version':'0.4','editor_version':'0.5','input_sha256':original_hash,'coordinates':'top-left-normalized',
          'editable_regions':[k for k in REGIONS if not k.endswith('_sway')],
          'canvas':{'width':image.width,'height':image.height},'original_size':list(original_size),'image':uri(image),
          'regions':[{**records[k],'asset':uri(v)} for k,v in masks.items()]}
    root=allocate_version(output,source.stem)
    template=files('static2live').joinpath('web')
    (root/'editor.js').write_text(template.joinpath('editor.js').read_text(encoding='utf8'),encoding='utf8')
    html=template.joinpath('editor.html').read_text(encoding='utf8').replace('BOOT_DATA',json.dumps(boot,ensure_ascii=True).replace('<','\\u003c'))
    (root/'index.html').write_text(html,encoding='utf8')
    write_json(root/'manifest.json',{'generator':'static2live','static2live_version':__version__,'editor_version':'0.5','artifact':'region-editor',
         'input_sha256':original_hash,'resources':{n:sha256(root/n) for n in ['index.html','editor.js']}})
    if sha256(source)!=original_hash: raise ValueError('生成期间输入改变')
    return root
