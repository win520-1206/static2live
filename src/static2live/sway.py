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
    if policy not in ('distal-linear-v1','tip-edge-v2'):
        raise ValueError('未知sway权重策略')
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
