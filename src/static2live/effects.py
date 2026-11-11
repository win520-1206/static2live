"""Shared, bounded effect parameters. Units always refer to exported canvas."""
from copy import deepcopy
import math
import jsonschema

REGIONS = ['person','sky','water','cloud','glow','other','face','hands','hair','cloth','body','protected','hair_sway','cloth_sway']
KINDS = ['rain','snow','dust','fog','glow','cloud_drift']
DEFAULT = dict(enabled=True,intensity=.35,count=60,speed_px_s=12.,size_px=2.,
               color='#ffd6a0',region='full',exclude_person=False,period_seconds=8.,amplitude_px=2.)
SCHEMA = {'type':'object','additionalProperties':False,'required':['type',*DEFAULT],
          'properties':{'type':{'enum':KINDS},'enabled':{'type':'boolean'},
            'intensity':{'type':'number','minimum':0,'maximum':1},
            'count':{'type':'integer','minimum':0,'maximum':256},
            'speed_px_s':{'type':'number','minimum':0,'maximum':600},
            'size_px':{'type':'number','minimum':.5,'maximum':40},
            'color':{'type':'string','pattern':'^#[0-9a-fA-F]{6}$'},
            'region':{'enum':['full',*REGIONS]},'exclude_person':{'type':'boolean'},
            'period_seconds':{'type':'number','minimum':2,'maximum':120},
            'amplitude_px':{'type':'number','minimum':0,'maximum':20}}}


def complete_effect(raw):
    if not isinstance(raw,dict) or raw.get('type') not in KINDS:
        raise ValueError('未知效果类型')
    effect=deepcopy(DEFAULT)
    if raw['type']=='rain': effect.update(color='#c0d8ef',speed_px_s=220,size_px=14)
    if raw['type']=='snow': effect.update(color='#ffffff',speed_px_s=35,size_px=3)
    if raw['type']=='fog': effect.update(count=8,size_px=30,speed_px_s=6,intensity=.15,color='#edf1f5')
    if raw['type']=='glow': effect.update(region='glow',count=0,intensity=.15)
    if raw['type']=='cloud_drift': effect.update(region='cloud',count=0,intensity=.5)
    effect.update(raw)
    validate_effect(effect)
    return effect


def validate_effect(effect):
    jsonschema.validate(effect,SCHEMA)
    if any(not math.isfinite(v) for v in effect.values() if isinstance(v,(int,float))):
        raise ValueError('效果数值必须有限')
    if effect['type']=='cloud_drift' and effect['region']!='cloud':
        raise ValueError('Cloud Drift 只允许确认的 cloud 区域，不等同 sky')


def validate_effects(effects):
    if not isinstance(effects,list) or len(effects)>6:
        raise ValueError('效果列表最多六项，每类一项')
    for effect in effects: validate_effect(effect)
    if len({e['type'] for e in effects})!=len(effects):
        raise ValueError('同一效果类型不能重复')
