"""Explicit, non-generative input framing in EXIF-oriented source coordinates."""
import re


DEFAULT = {'aspect': None, 'anchor': 'center'}
SCHEMA = {'type': 'object', 'additionalProperties': False,
    'required': ['aspect', 'anchor'], 'properties': {
        'aspect': {'type': ['string', 'null']},
        'anchor': {'enum': ['center', 'top', 'bottom']}}}


def aspect_ratio(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,3}:[1-9][0-9]{0,3}', value):
        raise ValueError('crop aspect 必须为正整数 W:H，例如16:9或3440:1440')
    width, height = map(int, value.split(':'))
    return width / height


def crop_box(size, framing=None):
    framing = framing or DEFAULT
    if framing['aspect'] is None:
        return None
    ratio = aspect_ratio(framing['aspect'])
    width, height = size
    if width / height > ratio:
        cropped_width, cropped_height = max(1, min(width, round(height * ratio))), height
    else:
        cropped_width, cropped_height = width, max(1, min(height, round(width / ratio)))
    left = (width - cropped_width) // 2
    top = {'top': 0, 'center': (height - cropped_height) // 2,
        'bottom': height - cropped_height}[framing['anchor']]
    return (left, top, left + cropped_width, top + cropped_height)


def frame_record(size, box):
    return None if box is None else {'original_size': list(size), 'crop_box': list(box),
        'coordinates': 'exif-oriented-source-pixels'}
