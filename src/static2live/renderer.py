import base64
import json
import io
from PIL import Image,ImageChops
from importlib.resources import files

from .motion import validate_motion
from .storage import safe_resource
from .primitives import GLSL, SHADER_MODES
from .pointer import has_subject, subject_pointer_guard


def export_web(root, motion):
    validate_motion(motion)
    def uri(relative):
        return "data:image/png;base64," + base64.b64encode(safe_resource(root, relative).read_bytes()).decode("ascii")
    blank=io.BytesIO();Image.new('L',(1,1),0).save(blank,format='PNG')
    black='data:image/png;base64,'+base64.b64encode(blank.getvalue()).decode('ascii')
    white=io.BytesIO();Image.new('L',(1,1),255).save(white,format='PNG')
    boot = {"motion": motion, "image": uri(motion["assets"]["image"]), "depth": uri(motion["assets"]["depth"]) if motion['assets']['depth'] else black,
            'regions':{key:uri(region['asset']) for key,region in motion.get('regions',{}).items()},'black':black,
            'white':'data:image/png;base64,'+base64.b64encode(white.getvalue()).decode('ascii')}
    if has_subject(motion):
        if motion['assets']['depth']:
            with Image.open(safe_resource(root,motion['assets']['depth'])) as depth:packed=depth.convert('RGBA')
        else:packed=Image.new('RGBA',(motion['canvas']['width'],motion['canvas']['height']))
        packed=Image.merge('RGBA',(packed.getchannel('R'),subject_pointer_guard(root,motion),
            packed.getchannel('B'),Image.new('L',packed.size,255)))
        output=io.BytesIO();packed.save(output,format='PNG')
        boot.update(pointer_policy='subject-rigid-v2',
            pointer_depth='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode('ascii'))
    cloud=next((e for e in motion.get('effects',[]) if e['type']=='cloud_drift' and e['enabled']),None)
    if cloud and cloud['exclude_person'] and 'person' in motion['regions']:
        with Image.open(safe_resource(root,motion['regions']['cloud']['asset'])) as c, Image.open(safe_resource(root,motion['regions']['person']['asset'])) as p:
            output=io.BytesIO();ImageChops.subtract(c,p).save(output,format='PNG')
            boot['cloud_texture']='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode('ascii')
    serialized = json.dumps(boot, ensure_ascii=True).replace("<", "\\u003c")
    template = files("static2live").joinpath("web")
    for name in ("runtime.js", "style.css",'effects.js','audio.js'):
        content=template.joinpath(name).read_text(encoding="utf-8")
        if name=='runtime.js':
            content=content.replace('/*S2L_PRIMITIVE_GLSL*/',GLSL).replace('/*S2L_SHADER_MODES*/',json.dumps(SHADER_MODES))
        (root / name).write_text(content, encoding="utf-8")
    (root / "index.html").write_text(
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Static2Live</title><link rel="stylesheet" href="style.css"></head>'
        '<body><canvas aria-label="深度视差壁纸"></canvas><canvas id="effects" aria-label="程序化效果"></canvas><img id="fallback" alt="静态壁纸" hidden>'
        '<p id="notice" hidden></p><details id="audio-controls" hidden><summary>音频响应</summary>'
        '<p>只播放手动选择的本地音频，不请求麦克风、不上传。</p><label>选择音频 <input id="audio-file" type="file" accept="audio/*"></label>'
        '<audio id="audio-player" controls></audio><button id="audio-stop">停止并释放</button><p id="audio-status" role="status"></p></details>'
        '<script id="static2live-data" type="application/json">'
        + serialized + '</script><script src="effects.js"></script><script src="audio.js"></script><script src="runtime.js"></script></body></html>', encoding="utf-8")
