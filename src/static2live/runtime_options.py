"""V0.6 runtime contract. No model, browser, or machine-specific dependencies."""
from copy import deepcopy
import math
import jsonschema
from .primitives import GEOMETRIC, DISPLACING

DEFAULTS = {
    'performance_profile':'inherit',
    'display':{'viewport':[0,0,1,1]},
    'audio':{'enabled':False,'strength':0.08,'response_seconds':0.15,'region':'full'},
    'shader':{'preset':'none','strength':0.25,'amplitude_px':1.0,'period_seconds':8.0},
}
PROFILES = {
    'inherit':{'fps':60,'pixel_ratio':2,'max_pixels':16777216,'particle_fraction':1},
    'eco':{'fps':15,'pixel_ratio':1,'max_pixels':2073600,'particle_fraction':0.5},
    'balanced':{'fps':30,'pixel_ratio':1.5,'max_pixels':4147200,'particle_fraction':0.75},
    'quality':{'fps':60,'pixel_ratio':2,'max_pixels':8294400,'particle_fraction':1},
}
SHADER_REGIONS = {'none':None,'warm_glow':'glow','water_ripple':'water','neon_pulse':'glow'}
SHADER_REGIONS.update({name:'other' for name in GEOMETRIC})
SCHEMAS = {
    'performance_profile':{'enum':list(PROFILES)},
    'display':{'type':'object','additionalProperties':False,'required':['viewport'], 'properties':{
        'viewport':{'type':'array','minItems':4,'maxItems':4,'items':{'type':'number','minimum':0,'maximum':1}}}},
    'audio':{'type':'object','additionalProperties':False,'required':list(DEFAULTS['audio']),'properties':{
        'enabled':{'type':'boolean'},'strength':{'type':'number','minimum':0,'maximum':0.2},
        'response_seconds':{'type':'number','minimum':0.01,'maximum':2},'region':{'type':'string'}}},
    'shader':{'type':'object','additionalProperties':False,'required':list(DEFAULTS['shader']),'properties':{
        'preset':{'enum':list(SHADER_REGIONS)},'strength':{'type':'number','minimum':0,'maximum':1},
        'amplitude_px':{'type':'number','minimum':0,'maximum':4},'period_seconds':{'type':'number','minimum':2,'maximum':120}}},
}


def validate_options(config):
    from .effects import REGIONS
    for key,schema in SCHEMAS.items(): jsonschema.validate(config[key],schema)
    for section in ('audio','shader'):
        if any(not math.isfinite(x) for x in config[section].values() if isinstance(x,(int,float))):
            raise ValueError('运行时参数必须有限')
    x,y,w,h=config['display']['viewport']
    if not all(math.isfinite(v) for v in (x,y,w,h)) or w<=0 or h<=0 or x+w>1+1e-9 or y+h>1+1e-9:
        raise ValueError('显示器viewport需在虚拟桌面[0,1]内且宽高大于0')
    if config['audio']['region'] not in ['full',*REGIONS]: raise ValueError('音频响应区域无效')


def enabled(config):
    return (config['performance_profile']!='inherit' or config['display']!=DEFAULTS['display']
            or config['audio']['enabled'] or config['shader']['preset']!='none')


def create_runtime(config,regions,size):
    validate_options(config)
    result={k:deepcopy(config[k]) for k in DEFAULTS}
    result['performance']=deepcopy(PROFILES[config['performance_profile']])
    shader=result['shader']; shader['region']=SHADER_REGIONS[shader['preset']]
    for required in [shader['region'],result['audio']['region'] if result['audio']['enabled'] else None]:
        if required and required!='full' and (required not in regions or regions[required]['coverage']==0):
            raise ValueError(f'高级效果需要非空 {required} 蒙版；先用 annotate 明确绘制')
    if shader['preset'] in DISPLACING and shader['amplitude_px']>min(size)*0.01:
        raise ValueError('高级Shader位移超过画布短边1%')
    return result


def validate_runtime(runtime,regions,size):
    config={k:deepcopy(runtime[k]) for k in DEFAULTS}
    config['shader'].pop('region',None)
    expected=create_runtime(config,regions,size)
    if runtime!=expected: raise ValueError('V0.6运行时档位或Shader区域绑定不一致')
