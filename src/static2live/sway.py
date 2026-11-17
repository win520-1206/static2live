"""Bounded V0.4 sway planning shared by renderers; no image-specific coordinates."""
import math
import numpy as np
from PIL import Image, ImageChops, ImageFilter


def validate_sway(parameters, size):
    if set(parameters) != {'enabled', 'amplitude_px', 'period_seconds', 'phase'}:
        raise ValueError('sway参数必须明确enabled、amplitude_px、period_seconds、phase')
    if type(parameters['enabled']) != bool:
        raise ValueError('sway.enabled须为布尔值')
    numbers = [parameters[k] for k in ('amplitude_px', 'period_seconds', 'phase')]
    if any(type(n) not in (int, float) or not math.isfinite(n) for n in numbers):
        raise ValueError('sway数值须有限')
    if not 0 <= parameters['amplitude_px'] <= min(4, min(size) * .01):
        raise ValueError('sway幅度不能超过4画布像素或短边1%')
    if not 2 <= parameters['period_seconds'] <= 120:
        raise ValueError('sway周期须为2–120秒')
    if not 0 <= parameters['phase'] <= 2 * math.pi:
        raise ValueError('sway相位须为0–2π弧度')


def build_sway_weight(mask, protected, amplitude_px, kind='hair', policy='distal-linear-v1'):
    """Anchor roots, weight distal silhouette, add bounded sampling support.

    Semantic masks remain untouched. Hair uses an edge band, not a translation
    of the whole hair mass. Local weighting is relative to the selected mask's
    bounds. Protection is applied last and includes a displacement guard so
    inverse sampling cannot pull animated pixels into the protected interior.
    """
    if kind not in ('hair', 'cloth'):
        raise ValueError('仅支持hair/cloth sway权重')
    if policy not in ('distal-linear-v1','tip-edge-v2','cloth-bend-v2'):
        raise ValueError('未知sway权重策略')
    if policy == 'cloth-bend-v2' and kind != 'cloth':
        raise ValueError('cloth-bend-v2仅适用于衣料')
    if mask.mode != 'L' or protected.mode != 'L' or mask.size != protected.size:
        raise ValueError('sway和保护蒙版须同尺寸8位灰度')
    if type(amplitude_px) not in (int, float) or not math.isfinite(amplitude_px) or not 0 <= amplitude_px <= min(4, min(mask.size) * .01):
        raise ValueError('sway幅度无效')
    bbox = mask.getbbox()
    if bbox is None or amplitude_px == 0:
        return Image.new('L', mask.size, 0)
    top, bottom = bbox[1], bbox[3]
    row = np.clip((np.arange(mask.height) - top) / max(1, bottom - top - 1), 0, 1)
    # Top portion is anchored, with increasing bending towards lower tips.
    taper = np.clip((row - .2) / .8, 0, 1)
    # A squared hair ramp virtually suppresses upper side tips. Keep roots
    # anchored and the narrow silhouette band, but allow a gradual linear
    # bend on hair. Cloth retains a gentler quadratic ramp.
    if kind == 'cloth':
        if policy == 'cloth-bend-v2':
            # A quadratic ramp concentrates motion at the cropped bottom hem.
            # Anchor the upper garment, then bend the visible mid-garment too.
            bend = np.clip((row - .2) / .45, 0, 1)
            taper = bend * bend * (3 - 2 * bend)
        else:
            taper = taper ** 2
    elif policy == 'tip-edge-v2':
        # A whole-head linear ramp suppresses side tips halfway down the head.
        # Keep the upper 20% anchored, then ease to full weight at 55% height.
        # Only the narrow silhouette band moves: neither the dense interior
        # nor the protected face is promoted to a translating hair slab.
        bend = np.clip((row - .2) / .35, 0, 1)
        taper = bend * bend * (3 - 2 * bend)
    selected = mask
    if kind == 'hair':
        width = max(1, min(12, round(min(mask.size) * .012)))
        inner = mask.filter(ImageFilter.MinFilter(2 * width + 1))
        selected = ImageChops.subtract(mask, inner)
    array = np.asarray(selected, dtype=np.float32) * taper[:, None]
    weighted = Image.fromarray(np.round(array).astype('uint8'))
    radius = math.ceil(amplitude_px) + 2
    support = weighted.filter(ImageFilter.MaxFilter(2 * radius + 1)).filter(ImageFilter.GaussianBlur(1))
    guard = protected.filter(ImageFilter.MaxFilter(2 * radius + 1))
    return ImageChops.subtract(support, guard)


def sway_displacement(weight, time_seconds, parameters):
    """Reference canvas-pixel field; GPU implementation must use same formula.

    This is a deterministic test oracle, not a second offline-video renderer.
    """
    validate_sway(parameters, weight.size)
    if not math.isfinite(time_seconds):
        raise ValueError('sway时间须有限')
    amplitude = parameters['amplitude_px'] if parameters['enabled'] else 0
    height, width = weight.height, weight.width
    yy, xx = np.mgrid[:height, :width]
    # Small spatial phase offsets let neighboring tips bend rather than slide.
    phase = parameters['phase'] + .6 * xx / width + .35 * yy / height
    return amplitude * (np.asarray(weight, dtype=np.float32) / 255) * np.sin(
        2 * math.pi * time_seconds / parameters['period_seconds'] + phase)


def cloth_breath_geometry(mask):
    """Normalized garment centre and half extents, derived from its source mask."""
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError('呼吸形变需要非空衣料区域')
    left, top, right, bottom = bounds
    return [(left + right) / (2 * mask.width), (top + bottom) / (2 * mask.height),
            (right - left) / (2 * mask.width), (bottom - top) / (2 * mask.height)]


def validate_cloth_geometry(geometry):
    if not isinstance(geometry, list) or len(geometry) != 4:
        raise ValueError('衣料呼吸几何参数无效')
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in geometry):
        raise ValueError('衣料呼吸几何参数须有限')
    x, y, rx, ry = geometry
    if rx <= 0 or ry <= 0 or x-rx < -1e-12 or y-ry < -1e-12 or x+rx > 1+1e-12 or y+ry > 1+1e-12:
        raise ValueError('衣料呼吸几何参数超出画布')
    return geometry


def cloth_breath_displacement(weight, time_seconds, parameters, geometry, policy='cloth-breath-v1'):
    """Canvas-pixel test oracle for the versioned two-dimensional cloth field."""
    x, y, rx, ry = validate_cloth_geometry(geometry)
    yy, xx = np.mgrid[:weight.height, :weight.width]
    nx = np.clip((xx / weight.width - x) / rx, -1, 1)
    ny = np.clip((yy / weight.height - y) / ry, -1, 1)
    scalar = sway_displacement(weight, time_seconds, parameters)
    if policy == 'cloth-breath-v2':
        # Lifting the fabric keeps the central folds responsive. The old
        # centre-based expansion cancelled motion through the garment centre.
        return np.stack((nx * .35 * scalar, -.9 * scalar), axis=-1)
    if policy != 'cloth-breath-v1':
        raise ValueError('未知衣料运动策略')
    return np.stack((nx * .5 * scalar, ny * .7 * scalar), axis=-1)


def cloth_breath_glsl(motion):
    region = (motion or {}).get('regions', {}).get('cloth_sway', {})
    policy = region.get('motion_policy')
    if policy is None:
        return ''
    if policy not in ('cloth-breath-v1', 'cloth-breath-v2'):
        raise ValueError('未知衣料运动策略')
    x, y, rx, ry = validate_cloth_geometry(region.get('breath_geometry'))
    direction = 'vec2(local.x * 0.35, -0.9)' if policy == 'cloth-breath-v2' else 'local * vec2(0.5, 0.7)'
    return f'''vec2 s2lClothBreath(vec2 position) {{
        vec2 local = clamp((position - vec2({x:.12g}, {y:.12g})) / vec2({rx:.12g}, {ry:.12g}), vec2(-1.0, -1.0), vec2(1.0, 1.0));
        return {direction};
    }}'''


def cloth_native_fragment(base, motion):
    """Apply the new garment deformation only to explicitly versioned outputs."""
    function = cloth_breath_glsl(motion)
    if not function:
        return base
    lines = ['offset.x -= hair + cloth;', 'offset.x-=hair+cloth;']
    matches = [line for line in lines if base.count(line) == 1]
    if len(matches) != 1 or base.count('void main() {') != 1:
        raise ValueError('衣料Shader公式不符合版本化适配契约')
    aspect = motion['canvas']['width'] / motion['canvas']['height']
    replacement = ('offset.x -= hair;\n    vec2 clothDirection = s2lClothBreath(uv);\n'
                   f'    offset += vec2(clothDirection.x, clothDirection.y * {aspect:.12g}) * cloth;')
    return base.replace('void main() {', function + '\nvoid main() {').replace(matches[0], replacement)


def cloth_web_runtime(base, motion):
    function = cloth_breath_glsl(motion)
    if not function:
        return base
    old = 'shifted.x-=(h+c)/imageSize.x;'
    if base.count(old) != 1 or base.count('/*S2L_PRIMITIVE_GLSL*/') != 1:
        raise ValueError('Web衣料公式不符合版本化适配契约')
    replacement = ('shifted.x-=h/imageSize.x;\n'
                   '      vec2 clothDirection=s2lClothBreath(vec2(base.x,1.0-base.y));\n'
                   '      shifted+=vec2(clothDirection.x,-clothDirection.y)*c/imageSize;')
    return base.replace('/*S2L_PRIMITIVE_GLSL*/',function+'\n/*S2L_PRIMITIVE_GLSL*/').replace(old,replacement)
