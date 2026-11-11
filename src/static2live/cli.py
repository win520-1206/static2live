import argparse
import json
import sys

from . import __version__
from .browser_check import check_browser, record_visual
from .depth import prepare_model
from .pipeline import generate
from .validator import validate_output
from .editor import export_editor
from .effects import KINDS
from .segmentation import prepare_segmentation
from .human_parser import prepare_human_parser
from .model_download import ENDPOINTS
from .analyzer import prepare_assets
from .storage import read_json


def parser():
    root = argparse.ArgumentParser(description="Static2Live：本地Lite / Smart、自动规划开发接口、Web与原生Adapter；版本与视觉验收分别报告")
    root.add_argument("--version",action="version",version=__version__)
    commands = root.add_subparsers(dest="command",required=True)
    gen = commands.add_parser("generate",help="生成版本化 Web / 原生 Wallpaper Engine 壁纸")
    gen.add_argument("--input",required=True)
    for key in ["preset","config","target","depth-map","model-cache","device","mode","regions","engine-path","we-template"]:
        gen.add_argument("--"+key)
    gen.add_argument("--output",default="output")
    gen.add_argument("--max-edge",type=int)
    gen.add_argument('--crop-aspect',help='显式裁切为W:H，例如16:9或3440:1440；默认不裁切')
    gen.add_argument('--crop-anchor',choices=['center','top','bottom'],help='裁切纵向锚点；top优先保留头顶，横向保持居中')
    gen.add_argument("--strength",type=float,help="最大位移/画布短边，范围 0–0.01")
    gen.add_argument("--overwrite",action="store_true",help="--output 必须是具体的受管理 vNNN 目录；旧版本保留备份")
    gen.add_argument('--effect',action='append',choices=KINDS,help='可重复；详细参数用 YAML effects 列表')
    gen.add_argument('--seed',type=int)
    planning=gen.add_mutually_exclusive_group()
    planning.add_argument('--auto-plan',dest='auto_plan',action='store_true',default=None,help='按真实区域证据自动推荐Preset与局部运动；默认开启，不自动下载模型')
    planning.add_argument('--no-auto-plan',dest='auto_plan',action='store_false',default=None)
    gen.add_argument('--performance-profile',choices=['inherit','eco','balanced','quality'],help='V0.6 Web运行时帧率/像素/粒子预算；音频及跨屏参数用YAML')
    gen.add_argument('--human-parsing',action='store_true',default=None,help='V0.4开发中：Smart本地人物解析，需显式准备human-parsing权重')
    gen.add_argument('--native-sway',action='store_true',default=None,help='仅原生：对显式确认的 other 区域映射 Foliage Sway，不自动识别发梢')
    gen.add_argument('--sway-amplitude-px',type=float,help='原生手选区域摇摆上界，0–4画布像素')
    toggle=gen.add_mutually_exclusive_group()
    toggle.add_argument('--no-parallax',dest='parallax_enabled',action='store_false',default=None,help='明确关闭视差，不读取或推理深度；Lite 可完全无模型')
    toggle.add_argument('--parallax',dest='parallax_enabled',action='store_true',default=None)
    analyze=commands.add_parser('analyze',help='只分析与推荐，不创建壁纸或记录视觉通过；与生成共用本地分析器')
    analyze.add_argument('--input',required=True)
    for key in ['config','preset','depth-map','model-cache','device','mode','regions']:analyze.add_argument('--'+key)
    analyze.add_argument('--max-edge',type=int)
    analyze.add_argument('--crop-aspect')
    analyze.add_argument('--crop-anchor',choices=['center','top','bottom'])
    analyze.add_argument('--human-parsing',action='store_true',default=None)
    analyze.add_argument('--no-parallax',dest='parallax_enabled',action='store_false',default=None)
    models = commands.add_parser("models",help="显式联网准备本地模型").add_subparsers(dest="models_command",required=True)
    prep = models.add_parser("prepare")
    prep.add_argument("--model-cache")
    prep.add_argument("--revision",default="main")
    prep.add_argument('--kind',choices=['depth','segmentation','human-parsing'],default='depth')
    prep.add_argument('--download-endpoint',choices=ENDPOINTS,help='慢速下载可显式改用国内镜像；仍校验官方 revision/哈希')
    prep.add_argument('--accept-model-license',action='store_true',help='已阅读并接受 SegFormer 单独的非商业研究/评估许可')
    annotate=commands.add_parser('annotate',help='生成离线蒙版编辑器：画笔/擦除/保护/运动源/撤销/缩放')
    annotate.add_argument('--input',required=True)
    annotate.add_argument('--output',default='annotations')
    annotate.add_argument('--max-edge',type=int,default=2048)
    annotate.add_argument('--regions',help='加载已有标注，亦可修正 Smart 的 assets/regions.json')
    val = commands.add_parser("validate",help="验证生成资源与真实浏览器")
    val.add_argument("path")
    val.add_argument("--browser",action="store_true")
    visual = commands.add_parser("record-visual",help="仅在实际观察后记录人工验收，不自动推断通过")
    visual.add_argument("path")
    visual.add_argument("--note",required=True)
    preview=commands.add_parser('preview-native',help='在独立 QA 窗口预览原生工程，不替换桌面，不自动判定通过')
    preview.add_argument('path');preview.add_argument('--engine-path')
    preview.add_argument('--qa-cache',help='显式指定独立ASCII目录，保留校验后的原生QA副本以兼容中文工程路径；不应用桌面')
    native=commands.add_parser('record-native',help='仅在真实原生观察之后记录验收')
    native.add_argument('path');native.add_argument('--note',required=True)
    native.add_argument('--check',action='append',default=[],choices=['load','mouse','edges','properties','particles','sway','audio','shader'])
    return root


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and not argv[0].startswith("-") and argv[0] not in ["generate","analyze","models","validate","record-visual","annotate","preview-native","record-native"]:
        argv = ["generate","--input",argv[0],*argv[1:]]
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.command == "generate":
            overrides = {key:getattr(args,key) for key in ["preset","target","device","max_edge","mode","seed","parallax_enabled","native_sway","sway_amplitude_px","human_parsing","performance_profile","auto_plan"]}
            if args.strength is not None:
                overrides["parallax"]={"fraction":args.strength}
            if args.effect is not None: overrides['effects']=[{'type':kind} for kind in args.effect]
            if args.crop_aspect is not None or args.crop_anchor is not None:
                overrides['framing']={k:v for k,v in {'aspect':args.crop_aspect,'anchor':args.crop_anchor}.items() if v is not None}
            destination, report = generate(args.input,args.output,args.config,overrides,args.depth_map,args.model_cache,args.overwrite,args.regions,args.engine_path,args.we_template)
            print(json.dumps({"output":str(destination),"structural_status":report["structural_status"],"status":report["status"],
                              "planning":read_json(destination/'analysis.json')['planning'],
                              "message":"文件生成完成；完整验收状态请查看 validation.json"},ensure_ascii=False))
            return 0
        if args.command=='analyze':
            overrides={key:getattr(args,key) for key in ['preset','device','max_edge','mode','human_parsing','parallax_enabled']}
            if args.crop_aspect is not None or args.crop_anchor is not None:
                overrides['framing']={k:v for k,v in {'aspect':args.crop_aspect,'anchor':args.crop_anchor}.items() if v is not None}
            print(json.dumps(prepare_assets(args.input,args.config,overrides,args.depth_map,args.model_cache,args.regions).report(),ensure_ascii=False));return 0
        if args.command == "models":
            if args.kind=='human-parsing':
                print(prepare_human_parser(args.model_cache,args.revision,args.accept_model_license,args.download_endpoint));return 0
            print(prepare_segmentation(args.model_cache,args.revision,args.accept_model_license,args.download_endpoint) if args.kind=='segmentation'
                  else prepare_model(args.model_cache,args.revision,args.download_endpoint)); return 0
        if args.command=='annotate':
            print(export_editor(args.input,args.output,args.max_edge,args.regions));return 0
        if args.command=='preview-native':
            from .wallpaper_engine import preview_native
            print(json.dumps(preview_native(args.path,args.engine_path,args.qa_cache),ensure_ascii=False));return 0
        if args.command=='record-native':
            from .wallpaper_engine import record_native
            report=record_native(args.path,args.note,args.check)
        elif args.command == "record-visual":
            report=record_visual(args.path,args.note)
        else:
            report=check_browser(args.path) if args.browser else validate_output(args.path)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 1 if report["status"] == "failed" else 0
    except Exception as error:
        print(f"Static2Live: {error}",file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
