import tempfile
from datetime import datetime, timezone
from pathlib import Path
import importlib.metadata
import hashlib
import json

import numpy as np
import yaml
from PIL import Image, ImageOps

from . import __version__
from .config import load_config
from .depth import ModelDepth, SuppliedDepth
from .motion import create_motion
from .renderer import export_web
from .storage import allocate_version, check_overwrite, sha256, write_json
from .validator import validate_output
from .regions import load_regions,save_regions
from .segmentation import ModelSegmentation,semantic_regions
from .human_parser import ModelHumanParsing,human_regions
from .sway import build_sway_weight,validate_sway
from .analyzer import prepare_assets
from .framing import frame_record


def generate(input_path, output="output", config_path=None, overrides=None, depth_map=None, model_cache=None, overwrite=False, regions_path=None, engine_path=None, template_path=None):
    source = Path(input_path).resolve(strict=True)
    load_config(config_path, overrides)
    destination = check_overwrite(output, [source, depth_map, config_path,regions_path,template_path]) if overwrite else None
    if not overwrite and any(Path(p).resolve().is_relative_to(Path(output).resolve()) for p in [source, depth_map, config_path] if p):
        raise ValueError("输出根目录不能包含输入文件")
    prepared=prepare_assets(source,config_path,overrides,depth_map,model_cache,regions_path)
    original_hash=prepared.original_hash;config=prepared.config;image=prepared.image;original_size=prepared.original_size
    depth=prepared.depth;provenance=prepared.provenance;masks=prepared.masks;records=prepared.records
    labels=prepared.labels;table=prepared.table;segmentation=prepared.segmentation
    human=prepared.human;human_labels=prepared.human_labels;human_table=prepared.human_table
    for kind in ('hair','cloth'):
        params=config[kind+'_sway']
        if params['enabled']:
            validate_sway(params,image.size)
            if kind not in masks or 'protected' not in masks or not np.asarray(masks['protected']).any():
                raise ValueError('人物摇摆需hair/cloth及非空protected蒙版；启用Smart人物解析或Lite导入，不自动猜测保护区')
            policy='tip-edge-v2' if kind=='hair' else 'distal-linear-v1'
            masks[kind+'_sway']=build_sway_weight(masks[kind],masks['protected'],params['amplitude_px'],kind,policy)
            if params['amplitude_px'] > 0 and not np.asarray(masks[kind+'_sway']).any():
                raise ValueError(f'{kind}摇摆没有可运动像素：区域为空或被保护区完全覆盖；请修正蒙版，不输出假动态')
            records[kind+'_sway']={'id':kind+'_sway','source':records[kind]['source'],'confirmed':True,
                                  'derivation':'distal taper + bounded sampling halo - protected guard',
                                  'weight_policy':policy,'parameters':params}
    root = Path(tempfile.mkdtemp(prefix=f".{destination.name}-build-", dir=destination.parent)) if overwrite else allocate_version(output, source.stem)
    try:
        (root / "assets").mkdir()
        image.save(root / "assets/image.png")
        if depth is not None: Image.fromarray(np.round(depth * 255).astype(np.uint8), "L").save(root / "assets/depth.png")
        if labels is not None: Image.fromarray(labels).save(root/'assets/labels.png')
        if human_labels is not None: Image.fromarray(human_labels).save(root/'assets/human-labels.png')
        region_assets=save_regions(root,masks,records,original_hash,image.size,frame_record(original_size,prepared.crop))
        warnings=[]
        for effect in config['effects']:
            if effect['enabled'] and effect['region']!='full' and (effect['region'] not in masks or not np.asarray(masks[effect['region']]).any()):
                warnings.append(f"{effect['type']}: 缺少非空 {effect['region']} 区域，已关闭该效果；使用 annotate 绘制后 --regions 重新生成")
            if effect['enabled'] and effect['exclude_person'] and 'person' not in masks:
                warnings.append(f"{effect['type']}: 未提供人物蒙版，无法排除人物；不宣称人物保护")
        (root / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=True), encoding="utf-8")
        write_json(root / "analysis.json", {"original_size": list(original_size), "output_size": list(image.size),
                                           "crop": list(prepared.crop) if prepared.crop is not None else None, "depth": provenance,'segmentation':segmentation,'label_table':table,'warnings':warnings,
                                           'human_parsing':human,'human_label_table':human_table,'planning':prepared.planning,
                                           'rgb_pixel_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
                                           "rgb_policy": "EXIF orient, alpha flatten, explicit crop if configured, resize; no generative repaint"})
        motion = create_motion(image.size, config,region_assets,depth is not None)
        write_json(root / "motion.json", motion)
        export_web(root, motion)
        adapter={'requested':config['target'],'actual':'web','runtime_status':'not_applicable'}
        if config['target']=='wallpaper-engine':
            from .wallpaper_engine import export_native,AdapterUnavailable
            try:
                adapter=export_native(root,motion,config,engine_path,template_path)
            except AdapterUnavailable as error:
                warnings.append(str(error))
                adapter.update(runtime_status='not_tested',fallback_reason=str(error))
            if adapter.get('warnings'): warnings.extend(adapter['warnings'])
            analysis=json.loads((root/'analysis.json').read_text(encoding='utf8'))
            analysis['warnings']=warnings
            write_json(root/'analysis.json',analysis)
        resources = {p.relative_to(root).as_posix(): sha256(p) for p in sorted(root.rglob("*")) if p.is_file()}
        manifest = {"generator":"static2live", "static2live_version": __version__,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "input": {"name":source.name,"sha256":original_hash}, "model": provenance,
                    'segmentation':segmentation,'mode':config['mode'],'human_parsing':human,
                    'planner':{'version':prepared.planning['version'],'enabled':config['auto_plan']},
                    'adapter':adapter,
                    "runtime": {"version":motion['version'] if motion['version'] in ('0.4','0.6') else "0.3", "type":"webgl-depth-uv+canvas-effects"}, "config":"config.yaml",
                    "motion_manifest":"motion.json", "resources":resources,
                    "dependencies": {name:importlib.metadata.version(name) for name in ["Pillow","numpy","PyYAML","jsonschema"]}}
        write_json(root / "manifest.json", manifest)
        report = validate_output(root)
        if sha256(source) != original_hash:
            raise ValueError("输入文件在生成期间发生变化")
        if report["structural_status"] == "failed":
            raise ValueError("结构验收失败；保留输出供检查")
        if overwrite:
            # Never recursively delete user data. Preserve replaced managed output.
            backup = destination.with_name(destination.name + ".backup-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"))
            destination.rename(backup)
            try:
                root.rename(destination)
            except Exception:
                backup.rename(destination)
                raise
            root = destination
        return root, report
    except Exception as error:
        write_json(root / "generation-error.json", {"status":"failed", "error":str(error)})
        raise
