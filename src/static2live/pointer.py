"""Source-mask-derived pointer guards; no semantic inference or RGB repaint."""
import math
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter

RIGID_POLICY = 'subject-rigid-v2'
POINTER_POLICIES = ('subject-anchored-v1', RIGID_POLICY)


def validate_pointer_policy(policy, legacy_bool=False):
    if policy is None or (legacy_bool and type(policy) is bool):
        return
    if type(policy) is not str or policy not in POINTER_POLICIES:
        raise ValueError('未知人物鼠标策略 / pointer policy')


def human_fragment(base, policy):
    """Versioned transport: a uniform nonzero subject displacement, not a lock."""
    validate_pointer_policy(policy)
    if policy != RIGID_POLICY:
        return base
    old='clamp(texSample2D(g_Texture1, uv).r, 0.2, 1.0) * (1.0 - protectedWeight)'
    if base.count(old) != 1:
        raise ValueError('人物Shader公式 / formula 不符合版本化适配契约')
    return base.replace(old, 'mix(clamp(texSample2D(g_Texture1, uv).r, 0.2, 1.0), 0.85, protectedWeight)')


def has_subject(motion):
    return motion.get('regions',{}).get('person',{}).get('coverage',0)>0


def subject_pointer_guard(root,motion):
    size=(motion['canvas']['width'],motion['canvas']['height'])
    guard=Image.new('L',size,0)
    for key in ('person','hair','cloth','protected'):
        region=motion.get('regions',{}).get(key)
        if region:
            with Image.open(Path(root)/region['asset']) as mask:
                binary=mask.convert('L').point(lambda value:255 if value else 0)
                guard=ImageChops.lighter(guard,binary)
    radius=math.ceil(motion['parallax']['amplitude_px']+max(
        [s['amplitude_px'] for s in motion.get('sways',[])]+[0]))+2
    expanded=guard.filter(ImageFilter.MaxFilter(radius*2+1))
    return ImageChops.lighter(expanded,expanded.filter(ImageFilter.GaussianBlur(2)))
