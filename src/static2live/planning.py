"""Deterministic V1 planning from measured pixels and explicitly sourced masks.

RGB statistics inform palette, never pretend to recognize people/sky/water.
"""
import hashlib
from copy import deepcopy
import numpy as np
from PIL import Image,ImageChops,ImageDraw,ImageFilter,ImageOps
from .sway import build_sway_weight

VERSION='1.1'
SUPPORTED_VERSIONS=('1.0',VERSION)


def plans_equal(actual,expected):
    """Only palette statistics tolerate numeric roundoff; resources stay exact."""
    normalized=deepcopy(actual)
    try:
        for key in ('mean_rgb','mean_luminance','luminance_std'):
            a=actual['features'][key];b=expected['features'][key]
            values=a if isinstance(a,list) else [a]
            if any(type(v) not in (int,float) for v in values):return False
            aa=np.asarray(a,dtype=np.float64);bb=np.asarray(b,dtype=np.float64)
            if aa.shape!=bb.shape or not np.isfinite(aa).all() or not np.allclose(aa,bb,rtol=0,atol=1e-12):return False
            normalized['features'][key]=b
    except (KeyError,TypeError,ValueError):return False
    return normalized==expected


def conservative_protection(masks):
    """Derive a safety guard, not a fine face/hair prediction; never replace a mask."""
    if 'protected' in masks:return None,None
    if 'face' in masks and np.asarray(masks['face']).any():
        keys=[k for k in ('face','hands') if k in masks and np.asarray(masks[k]).any()]
    elif 'person' in masks and np.asarray(masks['person']).any():keys=['person']
    else:keys=['hands'] if 'hands' in masks and np.asarray(masks['hands']).any() else []
    if not keys:return None,None
    result=Image.new('L',next(iter(masks.values())).size)
    for key in keys:result=ImageChops.lighter(result,masks[key])
    # Fill only enclosed silhouette holes, not edge-connected background.
    padded=ImageOps.expand(result.point(lambda v:255 if v else 0),1,fill=0)
    ImageDraw.floodfill(padded,(0,0),128)
    holes=Image.fromarray((np.asarray(padded)[1:-1,1:-1]==0).astype('uint8')*255)
    result=ImageChops.lighter(result,holes).filter(ImageFilter.MaxFilter(9))
    return result,{'id':'protected','source':'rule','confirmed':True,'derivation':'conservative-planner-guard-v1',
        'source_regions':keys,'guard_px':4,'enclosed_background_guard_px':int(np.asarray(holes).astype(bool).sum()),
        'confirmation':'automatic safety policy; not user visual approval or a face detector'}


def analyze_features(image,masks):
    probe=image.copy();probe.thumbnail((512,512),Image.Resampling.LANCZOS)
    rgb=np.asarray(probe,dtype=np.float64)/255
    luminance=rgb@np.array([.2126,.7152,.0722])
    selected={k:float(np.asarray(v).mean()/255) for k,v in sorted(masks.items()) if not k.endswith('_sway')}
    return {'canvas':{'width':image.width,'height':image.height},
        'rgb_pixel_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
        'palette_probe_max_edge':512,
        'mean_rgb':[float(x) for x in rgb.mean(axis=(0,1))],
        'mean_luminance':float(luminance.mean()),'luminance_std':float(luminance.std()),
        'region_coverage':selected,'semantic_policy':'Only supplied/model masks establish region identity; RGB is palette evidence only'}


def recommend(features,masks,version=VERSION):
    if version not in SUPPORTED_VERSIONS:raise ValueError('Unsupported planning algorithm version')
    coverage=features['region_coverage'];reasons=[];deferred=[];suggestions={}
    human=any(coverage.get(k,0)>.005 for k in ('person','face','hair'))
    if human:
        warm=features['mean_rgb'][0]-features['mean_rgb'][2]>.025 and coverage.get('person',0)>0
        preset='warm_portrait' if warm else 'portrait_subtle'
        reasons.append('known human region; restrained portrait motion'+('; measured warm palette' if warm else ''))
    elif any(coverage.get(k,0)>.02 for k in ('sky','water','cloud')):
        preset='landscape_soft';reasons.append('known sky/water/cloud region; no weather inferred')
    else:
        preset='general_balanced';reasons.append('no reliable scene identity available; generic bounded depth response')
        deferred.append('Semantic understanding requires Smart or explicitly drawn/imported regions; brightness is not recognition')
    protected=masks.get('protected');short=min(features['canvas'].values())
    for kind,amplitude,period,phase in [('hair',min(1.5 if version=='1.0' else 2.5,short*.005),5.5,.3),('cloth',min(.35,short*.002),6.5,1.3)]:
        if kind in masks and protected is not None and np.asarray(protected).any():
            weight=build_sway_weight(masks[kind],protected,amplitude,kind)
            if np.asarray(weight).any():
                suggestions[kind+'_sway']={'enabled':True,'amplitude_px':amplitude,'period_seconds':period,'phase':phase}
                reasons.append(kind+' source plus protection admits bounded distal motion')
            else:deferred.append(kind+' has no movable pixels after protection; automatic sway remains off')
        elif human:deferred.append(kind+' sway requires a source mask and nonempty protection; not fabricated')
    if coverage.get('water',0)>.02:
        suggestions['shader']={'preset':'water_ripple','strength':.15,'amplitude_px':min(1,short*.005),'period_seconds':10}
        reasons.append('known water region permits a local ripple')
    return {'preset':preset,'reasons':reasons,'deferred':deferred,'suggestions':suggestions}


def make_plan(image,masks,config,explicit_preset=False,version=VERSION):
    features=analyze_features(image,masks);recommendation=recommend(features,masks,version)
    return {'version':version,'enabled':config['auto_plan'],'features':features,'recommendation':recommendation,
        'selected_preset':config['preset'],'explicit_preset':explicit_preset,
        'policy':'CLI > user config > selected Preset > automatic suggestions > defaults; no downloads or mode changes'}
