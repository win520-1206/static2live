import jsonschema
import math
from copy import deepcopy
from .effects import validate_effects, REGIONS
from .primitives import DISPLACING

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["version", "canvas", "assets", "depth", "parallax"],
    "properties": {
        "version": {"const": "0.1"},
        "canvas": {"type": "object", "additionalProperties": False, "required": ["width", "height"],
                   "properties": {key: {"type": "integer", "minimum": 1} for key in ["width", "height"]}},
        "assets": {"type": "object", "additionalProperties": False, "required": ["image", "depth"],
                   "properties": {key: {"type": "string", "minLength": 1} for key in ["image", "depth"]}},
        "depth": {"type": "object", "additionalProperties": False, "required": ["near_white", "range"],
                  "properties": {"near_white": {"const": True}, "range": {"const": [0, 1]}}},
        "parallax": {"type": "object", "additionalProperties": False,
                     "required": ["amplitude_px", "response_seconds", "overscan_px"], "properties": {
                         "amplitude_px": {"type": "number", "minimum": 0},
                         "response_seconds": {"type": "number", "minimum": 0.01, "maximum": 2},
                         "overscan_px": {"type": "number", "minimum": 0}}}
    }
}


SCHEMA_V2=deepcopy(SCHEMA)
SCHEMA_V2['properties']['version']={'const':'0.2'}
SCHEMA_V2['required']+=['mode','seed','regions','effects','parallax_enabled']
SCHEMA_V2['properties'].update(mode={'enum':['lite','smart']},seed={'type':'integer','minimum':0,'maximum':4294967295},
    regions={'type':'object','propertyNames':{'enum':REGIONS},'additionalProperties':{'type':'object'}},
    effects={'type':'array','maxItems':6},parallax_enabled={'type':'boolean'})
SCHEMA_V2['properties']['assets']['properties']['depth']={'type':['string','null']}

SCHEMA_V4=deepcopy(SCHEMA_V2)
SCHEMA_V4['properties']['version']={'const':'0.4'}
SCHEMA_V4['required']+=['sways']
SCHEMA_V4['properties']['sways']={'type':'array','maxItems':2,'items':{'type':'object'}}
SCHEMA_V6=deepcopy(SCHEMA_V4)
SCHEMA_V6['properties']['version']={'const':'0.6'}
SCHEMA_V6['required']+=['runtime']
SCHEMA_V6['properties']['runtime']={'type':'object'}


def create_motion(size, config, regions=None, depth_present=True):
    enabled=config.get('parallax_enabled',True)
    amplitude = min(size) * config["parallax"]["fraction"] if enabled else 0
    effects=deepcopy(config.get('effects',[]))
    regions=regions or {}
    for effect in effects:
        region=effect['region']
        if region!='full' and (region not in regions or regions[region]['coverage']==0): effect['enabled']=False
    cloud=next((e['amplitude_px']*e['intensity'] for e in effects if e['type']=='cloud_drift' and e['enabled']),0)
    result = {"version": "0.2", "canvas": {"width": size[0], "height": size[1]},
            'mode':config.get('mode','lite'),'seed':config.get('seed',1337),'regions':regions,'effects':effects,'parallax_enabled':enabled,
            "assets": {"image": "assets/image.png", "depth": "assets/depth.png" if depth_present else None},
            "depth": {"near_white": True, "range": [0, 1]},
            "parallax": {"amplitude_px": amplitude, "response_seconds": config["parallax"]["response_seconds"],
                         "overscan_px": amplitude + cloud + 2 if amplitude+cloud else 0}}
    sways=[]
    for kind in ('hair','cloth'):
        params=config.get(kind+'_sway',{})
        if params.get('enabled'):
            region=regions.get(kind+'_sway')
            if not region or region['coverage']==0:
                continue
            sways.append({'kind':kind,'weight_region':kind+'_sway',**deepcopy(params)})
    if sways:
        result['version']='0.4';result['sways']=sways
        result['parallax']['overscan_px']+=sum(s['amplitude_px'] for s in sways)+2
    from .runtime_options import enabled, create_runtime
    if enabled(config):
        result.update(version='0.6',sways=sways,runtime=create_runtime(config,regions,size))
        shader=result['runtime']['shader']
        if shader['preset'] in DISPLACING:
            result['parallax']['overscan_px']+=shader['amplitude_px']*shader['strength']+2
    return result


def validate_motion(motion):
    jsonschema.validate(motion, SCHEMA_V6 if motion.get('version')=='0.6' else SCHEMA_V4 if motion.get('version')=='0.4' else SCHEMA_V2 if motion.get('version')=='0.2' else SCHEMA)
    if not all(math.isfinite(value) for value in motion["parallax"].values()):
        raise ValueError("Motion 参数必须为有限数值")
    amplitude = motion["parallax"]["amplitude_px"]
    if amplitude > min(motion["canvas"].values()) * 0.01:
        raise ValueError("视差超过短边 1% 安全上限")
    if motion["parallax"]["overscan_px"] < amplitude:
        raise ValueError("边缘留量小于最大位移")
    if motion['version'] in ('0.2','0.4','0.6'):
        validate_effects(motion['effects'])
        if not motion['parallax_enabled'] and amplitude!=0: raise ValueError('关闭视差仍存在位移')
        if motion['parallax_enabled'] and motion['assets']['depth'] is None: raise ValueError('启用视差必须有真实深度资源')
        for key,region in motion['regions'].items():
            if region.get('id')!=key or region.get('source') not in ['manual','imported','rule','model'] or region.get('confirmed') is not True:
                raise ValueError('区域身份/来源/确认状态无效')
            coverage=region.get('coverage')
            if not isinstance(coverage,(float,int)) or not math.isfinite(coverage) or not 0<=coverage<=1 or not isinstance(region.get('asset'),str):
                raise ValueError('区域资源或覆盖率无效')
        for effect in motion['effects']:
            if effect['enabled'] and effect['region']!='full' and effect['region'] not in motion['regions']:
                raise ValueError('启用效果引用缺失区域')
        cloud=next((e['amplitude_px']*e['intensity'] for e in motion['effects'] if e['type']=='cloud_drift' and e['enabled']),0)
        if cloud>min(motion['canvas'].values())*.01: raise ValueError('云层位移超过短边 1%')
        if motion['parallax']['overscan_px']<amplitude+cloud: raise ValueError('边缘留量未包括云层位移')
    if motion.get('sways'):
        from .sway import validate_sway
        if 'protected' not in motion['regions'] or motion['regions']['protected']['coverage']==0:
            raise ValueError('人物摇摆必须有非空保护区')
        kinds=set()
        for sway in motion['sways']:
            if set(sway)!={'kind','weight_region','enabled','amplitude_px','period_seconds','phase'}:
                raise ValueError('sway Manifest 字段无效')
            kind=sway['kind']
            if kind not in ('hair','cloth') or kind in kinds or sway['weight_region']!=kind+'_sway':
                raise ValueError('sway区域身份无效或重复')
            kinds.add(kind)
            region=motion['regions'].get(sway['weight_region'])
            if not region or region['coverage']==0: raise ValueError('sway权重不存在或为空')
            validate_sway({k:v for k,v in sway.items() if k not in ('kind','weight_region')},tuple(motion['canvas'].values()))
        if motion['parallax']['overscan_px']<amplitude+cloud+sum(s['amplitude_px'] for s in motion['sways']):
            raise ValueError('边缘留量未包含人物摇摆')
    if motion['version']=='0.6':
        from .runtime_options import validate_runtime
        validate_runtime(motion['runtime'],motion['regions'],tuple(motion['canvas'].values()))
        shader=motion['runtime']['shader']
        extra=shader['amplitude_px']*shader['strength'] if shader['preset'] in DISPLACING else 0
        if motion['parallax']['overscan_px']<amplitude+cloud+sum(s['amplitude_px'] for s in motion['sways'])+extra:
            raise ValueError('边缘留量未包括高级Shader位移')
