import re
import json
import base64
import hashlib
import io
from pathlib import Path

import numpy as np
from PIL import Image

from .motion import validate_motion,create_motion
from .config import load_config
from .storage import read_json, safe_resource, sha256, write_json


def summary(checks):
    states = [c["status"] for c in checks]
    return "failed" if "failed" in states else "not_tested" if "not_tested" in states else "warning" if "warning" in states else "passed"


def validate_output(root, write=True):
    root = Path(root)
    checks = []
    def check(name, work):
        try:
            detail = work()
            checks.append({"name": name, "status": "passed", "detail": detail or "ok"})
        except Exception as error:
            checks.append({"name": name, "status": "failed", "detail": str(error)})
    def integrity():
        manifest = read_json(root / "manifest.json")
        if manifest.get("generator") != "static2live" or manifest.get("static2live_version") not in ["0.1.0","0.2.0","0.3.0"]:
            raise ValueError("manifest 来源或版本错误")
        required = {"index.html", "runtime.js", "style.css", "motion.json", "config.yaml", "analysis.json", "assets/image.png"}
        motion=read_json(root/'motion.json')
        if motion['assets']['depth']: required.add(motion['assets']['depth'])
        if motion['version'] in ('0.2','0.4','0.6'): required.update(['effects.js','assets/regions.json'])
        if motion['version']=='0.6': required.add('audio.js')
        if manifest.get('adapter',{}).get('actual')=='native-scene':required.update(['native-plan.json','wallpaper-engine/project.json','wallpaper-engine/scene.json'])
        if not required <= set(manifest["resources"]):
            raise ValueError("manifest 缺少必需资源")
        for relative, digest in manifest["resources"].items():
            if sha256(safe_resource(root, relative)) != digest:
                raise ValueError(f"资源哈希不符: {relative}")
        return "所有生成资源均存在，路径不越界且哈希匹配"
    check("resources_and_manifest", integrity)
    check("motion_schema_and_bounds", lambda: validate_motion(read_json(root / "motion.json")))
    def assets():
        motion = read_json(root / "motion.json")
        size = (motion["canvas"]["width"], motion["canvas"]["height"])
        with Image.open(safe_resource(root, motion["assets"]["image"])) as image:
            if image.size != size or image.mode != "RGB":
                raise ValueError("图像尺寸或 RGB 格式错误")
            analysis=read_json(root/'analysis.json')
            if analysis.get('rgb_pixel_sha256') and hashlib.sha256(image.tobytes()).hexdigest()!=analysis['rgb_pixel_sha256']:
                raise ValueError('原始规范 RGB 资源被修改')
        flat=False
        if motion['assets']['depth']:
            with Image.open(safe_resource(root, motion["assets"]["depth"])) as depth:
                if depth.size != size or depth.mode != "L":
                    raise ValueError("深度尺寸或格式错误")
                flat = np.ptp(np.asarray(depth)) == 0
        for region in motion.get('regions',{}).values():
            with Image.open(safe_resource(root,region['asset'])) as mask:
                if mask.mode!='L' or mask.size!=size: raise ValueError('区域格式或尺寸不一致')
                coverage=float(np.asarray(mask).mean()/255)
                if abs(coverage-region['coverage'])>1e-8: raise ValueError('区域覆盖率与资源不一致')
                if coverage==0 and any(e['enabled'] and e['region']==region['id'] for e in motion['effects']):
                    raise ValueError('空蒙版用于启用效果')
        if flat:
            return "深度为常量；不具备近远差异（另列 warning）"
    check("asset_dimensions", assets)
    def framing():
        from .framing import crop_box,frame_record
        config=load_config(root/'config.yaml');analysis=read_json(root/'analysis.json')
        original=analysis['original_size']
        if len(original)!=2 or any(type(v)!=int or v<1 for v in original):raise ValueError('原图尺寸记录无效')
        box=crop_box(original,config['framing'])
        expected=list(box) if box is not None else None
        if analysis.get('crop')!=expected:raise ValueError('裁切记录与配置/原图尺寸不一致')
        bundle=read_json(root/'assets/regions.json') if (root/'assets/regions.json').exists() else {}
        if bundle.get('input_frame')!=frame_record(original,box):raise ValueError('标注坐标框与输入裁切不一致')
        if box is not None:
            motion=read_json(root/'motion.json');w,h=motion['canvas'].values()
            cw,ch=box[2]-box[0],box[3]-box[1]
            if w>cw or h>ch or max(w,h)>config['max_edge'] or abs(w*ch-h*cw)>max(cw,ch):
                raise ValueError('裁切后输出尺寸/比例不一致')
        return 'explicit source-frame crop before inference; no repaint' if box is not None else 'not applicable: uncropped legacy/default input'
    check('input_framing',framing)
    def protection():
        motion=read_json(root/'motion.json')
        if not motion.get('sways'):return 'not applicable: no human sway'
        from .sway import build_sway_weight
        with Image.open(safe_resource(root,motion['regions']['protected']['asset'])) as protected:
            for sway in motion['sways']:
                with Image.open(safe_resource(root,motion['regions'][sway['kind']]['asset'])) as original, Image.open(safe_resource(root,motion['regions'][sway['weight_region']]['asset'])) as weight:
                    policy=motion['regions'][sway['weight_region']].get('weight_policy','distal-linear-v1')
                    expected=build_sway_weight(original,protected,sway['amplitude_px'],sway['kind'],policy)
                    if not np.array_equal(np.asarray(expected),np.asarray(weight)):
                        raise ValueError('sway权重与原区域、保护区及幅度不对应')
                    if np.any(np.asarray(weight)[np.asarray(protected)>0]):raise ValueError('保护区仍参与摇摆')
                    if sway['amplitude_px']>0 and not np.asarray(weight).any():raise ValueError('启用非零sway却没有可运动像素')
        return '保护区sway权重为零，衍生采样蒙版与参数一致；视觉形变仍需实际验收'
    check('human_sway_protection',protection)
    def planning():
        manifest=read_json(root/'manifest.json')
        if 'planner' not in manifest:return 'legacy output; no automatic planning contract'
        from .planning import make_plan,conservative_protection,plans_equal,SUPPORTED_VERSIONS
        config=load_config(root/'config.yaml');analysis=read_json(root/'analysis.json');motion=read_json(root/'motion.json')
        planning_version=manifest['planner'].get('version')
        if planning_version not in SUPPORTED_VERSIONS or manifest['planner']!={'version':planning_version,'enabled':config['auto_plan']}:raise ValueError('Planner版本或启用状态不匹配')
        masks={}
        for key,record in motion.get('regions',{}).items():
            if key.endswith('_sway'):continue
            with Image.open(safe_resource(root,record['asset'])) as mask:masks[key]=mask.copy()
        guard=motion.get('regions',{}).get('protected',{})
        if guard.get('derivation')=='conservative-planner-guard-v1' and guard.get('source')=='rule' and 'previous_source' not in guard:
            expected,metadata=conservative_protection({k:v for k,v in masks.items() if k!='protected'})
            if expected is None or not np.array_equal(np.asarray(expected),np.asarray(masks['protected'])):
                raise ValueError('自动保护区与来源区域不对应')
            if any(guard.get(k)!=v for k,v in metadata.items()):raise ValueError('自动保护策略或来源不一致')
        actual=analysis['planning']
        if type(actual.get('explicit_preset')) is not bool:raise ValueError('Preset来源字段错误')
        with Image.open(root/'assets/image.png') as image:
            expected=make_plan(image,masks,config,actual['explicit_preset'],planning_version)
        if not plans_equal(actual,expected):raise ValueError('图像分析、推荐依据或Preset选择无法从资源重现')
        return '从规范RGB与已来源化蒙版重算推荐；不冒充自动语义或视觉验收'
    check('automatic_planning',planning)
    try:
        with Image.open(root / "assets/depth.png") as d:
            if np.ptp(np.asarray(d)) == 0:
                checks.append({"name":"depth_variation","status":"warning","detail":"深度为常量，仅会产生整体位移"})
    except Exception:
        pass
    def embedded():
        html = (root / "index.html").read_text(encoding="utf-8")
        if html.count("data:image/png;base64,") < 2 or "static2live-data" not in html:
            raise ValueError("离线启动数据未完整嵌入")
        match = re.search(r'<script id="static2live-data" type="application/json">(.*?)</script>', html, re.S)
        boot = json.loads(match.group(1)) if match else {}
        motion = read_json(root / "motion.json")
        if boot.get("motion") != motion:
            raise ValueError("内嵌 Motion 与 motion.json 不一致，需重新导出")
        if 'pointer_policy' in boot or 'pointer_depth' in boot:
            from .pointer import has_subject, subject_pointer_guard
            if boot.get('pointer_policy') not in ('subject-anchored-v1','subject-rigid-v2') or not has_subject(motion):
                raise ValueError('内嵌人物鼠标保护策略/来源无效')
            raw=base64.b64decode(boot['pointer_depth'].split(',',1)[1],validate=True)
            with Image.open(io.BytesIO(raw)) as packed:
                if packed.mode!='RGBA' or packed.size!=(motion['canvas']['width'],motion['canvas']['height']):
                    raise ValueError('内嵌人物鼠标深度纹理格式错误')
                if not np.array_equal(np.asarray(packed.getchannel('G')),np.asarray(subject_pointer_guard(root,motion))):
                    raise ValueError('内嵌人物鼠标保护蒙版未绑定来源')
                if motion['assets']['depth']:
                    with Image.open(safe_resource(root,motion['assets']['depth'])) as depth:
                        if any(not np.array_equal(np.asarray(packed.getchannel(channel)),np.asarray(depth.convert('L'))) for channel in ('R','B')):
                            raise ValueError('内嵌人物鼠标深度值与原深度不同')
                if np.any(np.asarray(packed.getchannel('A'))!=255):raise ValueError('人物鼠标深度纹理必须不透明')
        if motion['version']=='0.6':
            for key,value in [('black',0),('white',255)]:
                data=base64.b64decode(boot[key].split(',',1)[1],validate=True)
                with Image.open(io.BytesIO(data)) as constant:
                    if constant.size!=(1,1) or constant.mode!='L' or constant.getpixel((0,0))!=value:
                        raise ValueError('运行时常量纹理错误')
            if read_json(root/'manifest.json')['runtime']['version']!='0.6':raise ValueError('运行时版本不对应V0.6 Motion')
        manifest = read_json(root / "manifest.json")
        for key in ("image", "depth"):
            relative = motion["assets"][key]
            if relative is None: continue
            if relative not in manifest["resources"]:
                raise ValueError("Motion 资源未被 Project Manifest 跟踪")
            raw = base64.b64decode(boot[key].split(',',1)[1], validate=True)
            if raw != safe_resource(root,relative).read_bytes():
                raise ValueError("内嵌纹理与磁盘资源不一致")
        for key,region in motion.get('regions',{}).items():
            relative=region['asset']
            if relative not in manifest['resources']: raise ValueError('区域资源未被跟踪')
            raw=base64.b64decode(boot['regions'][key].split(',',1)[1],validate=True)
            if raw!=safe_resource(root,relative).read_bytes(): raise ValueError('内嵌区域与资源不一致')
        js = (root / "runtime.js").read_text(encoding="utf-8")
        if (root/'effects.js').exists(): js+=(root/'effects.js').read_text(encoding='utf8')
        if (root/'audio.js').exists(): js+=(root/'audio.js').read_text(encoding='utf8')
        if re.search(r"\bfetch\s*\(|https?://", js):
            raise ValueError("运行时存在外部网络依赖")
    check("offline_embedding", embedded)
    try:
        adapter=read_json(root/'manifest.json').get('adapter',{})
    except Exception:adapter={}
    if adapter.get('actual')=='native-scene':
        from .wallpaper_engine import validate_native
        check('native_scene_structure',lambda:validate_native(root))
    try:
        analysis=read_json(root/'analysis.json')
        for warning in analysis.get('warnings',[]): checks.append({'name':'region_effect_warning','status':'warning','detail':warning})
        motion=read_json(root/'motion.json')
        if motion.get('version') in ('0.2','0.4','0.6'):
            config=load_config(root/'config.yaml')
            expected=create_motion((motion['canvas']['width'],motion['canvas']['height']),config,motion['regions'],motion['assets']['depth'] is not None)
            if expected!=motion: raise ValueError('配置参数未正确绑定至 Motion Manifest')
            manifest=read_json(root/'manifest.json')
            if manifest['mode']!=motion['mode']: raise ValueError('运行模式与 manifest 不一致')
            bundle=read_json(root/'assets/regions.json')
            if bundle['input_sha256']!=manifest['input']['sha256'] or bundle['canvas']!=motion['canvas']: raise ValueError('区域绑定错误')
            if set(r['id'] for r in bundle['regions'])!=set(motion['regions']): raise ValueError('区域清单不同步')
            if motion['mode']=='smart':
                if manifest['segmentation'].get('backend')!='segformer-b0-ade': raise ValueError('Smart 不能伪装规则来源')
                with Image.open(root/'assets/labels.png') as labels:
                    if labels.mode!='L' or labels.size!=(motion['canvas']['width'],motion['canvas']['height']): raise ValueError('标签尺寸/格式错误')
                    if not {str(int(x)) for x in np.unique(np.asarray(labels))}<=set(analysis['label_table']): raise ValueError('标签表引用无效')
            if config['human_parsing']:
                human=manifest.get('human_parsing',{})
                if human.get('backend')!='fashn-human-parser' or human.get('model_id')!='fashn-ai/fashn-human-parser' or human!=analysis.get('human_parsing'):
                    raise ValueError('人物解析模型来源缺失或不同步')
                if 'assets/human-labels.png' not in manifest['resources']:raise ValueError('人物标签未被跟踪')
                with Image.open(root/'assets/human-labels.png') as h:
                    if h.mode!='L' or h.size!=(motion['canvas']['width'],motion['canvas']['height']):raise ValueError('人物标签格式或尺寸无效')
                    if not {str(int(x)) for x in np.unique(np.asarray(h))}<=set(analysis['human_label_table']):raise ValueError('人物标签表引用无效')
                    from .human_parser import LABELS,human_regions
                    table={int(k):v for k,v in analysis['human_label_table'].items()}
                    if table!=dict(enumerate(LABELS)):raise ValueError('人物类别表与已验证解析后端不一致')
                    expected_masks,expected_records=human_regions(np.asarray(h),table)
                for key,expected_mask in expected_masks.items():
                    actual=motion['regions'].get(key)
                    if actual is None:raise ValueError('人物解析基础区域缺失')
                    # User-confirmed overrides have their own recorded source;
                    # only untouched model regions must equal label derivation.
                    if actual.get('source')!='model' or 'previous_source' in actual:continue
                    with Image.open(safe_resource(root,actual['asset'])) as mask:
                        if not np.array_equal(np.asarray(mask),np.asarray(expected_mask)):
                            raise ValueError(f'人物区域{key}与原始标签及保守保护规则不对应')
                    for field,value in expected_records[key].items():
                        if actual.get(field)!=value:raise ValueError(f'人物区域{key}来源/保护策略不同步')
            checks.append({'name':'regions_and_mode','status':'passed','detail':'区域绑定、模式和标签对应；非细粒度人物保护'})
    except Exception as error:
        checks.append({'name':'regions_and_mode','status':'failed','detail':str(error)})
    if motion.get('version')=='0.6':
        runtime=motion['runtime']
        if runtime['audio']['enabled']:checks.append({'name':'audio_runtime','status':'not_tested','detail':'需真实本地音频或目标引擎音频输入验证；模拟回调不等于宿主验证'})
        if runtime['performance_profile']!='inherit':checks.append({'name':'performance_runtime','status':'not_tested','detail':'需检查实际帧率、像素和粒子预算；不是硬件性能承诺'})
        if runtime['display']['viewport']!=[0,0,1,1]:checks.append({'name':'multi_monitor_runtime','status':'not_tested','detail':'需检查相邻窗口裁切接缝及真实多屏布局'})
        if runtime['shader']['preset']!='none':checks.append({'name':'advanced_shader_runtime','status':'not_tested','detail':'需检查局部动画、保护区、关闭及减少动态'})
    checks.append({"name":"browser_runtime","status":"not_tested","detail":"需执行 static2live validate PATH --browser"})
    checks.append({"name":"visual_acceptance","status":"not_tested","detail":"需人工观察实际图片的形变与视差幅度；自动测试不能替代"})
    not_applicable=['protected_regions','wallpaper_engine','video_export']
    if motion.get('regions',{}).get('protected',{}).get('coverage',0)>0:not_applicable.remove('protected_regions')
    if adapter.get('requested')=='wallpaper-engine':
        not_applicable.remove('wallpaper_engine')
        native_status='not_tested'
        native_detail=adapter.get('fallback_reason','原生运行、属性开关、鼠标边缘和视觉需实际 Wallpaper Engine 验收')
        checks.insert(-2,{'name':'native_runtime','status':native_status,'detail':native_detail})
    try:
        if motion.get('mode','lite')=='lite': not_applicable.append('model_segmentation')
        if not motion.get('parallax_enabled',True): not_applicable.extend(['depth_estimation','mouse_parallax'])
        if not motion.get('effects'): not_applicable.append('procedural_effects')
    except Exception: pass
    runtime_checks=['browser_runtime','visual_acceptance','native_runtime','audio_runtime','performance_runtime','multi_monitor_runtime','advanced_shader_runtime']
    report = {"structural_status": summary([c for c in checks if c['name'] not in runtime_checks]), "status": summary(checks), "checks": checks,
              "not_applicable": not_applicable}
    if write:
        write_json(root / "validation.json", report)
    return report
