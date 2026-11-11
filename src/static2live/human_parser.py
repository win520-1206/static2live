"""V0.4 human parsing foundation; genuine local models, not face heuristics.

The backend emits labels and masks only. It never repaints RGB, downloads at
inference time, or claims that semantic hair is already a refined strand matte.
"""
from abc import ABC, abstractmethod
from pathlib import Path
import urllib.request

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageDraw, ImageOps

from .segmentation import ModelSegmentation, MODEL_FILES, LICENSE_URL
from .model_download import download_snapshot
from .storage import default_model_cache, sha256, write_json

MODEL_ID = 'fashn-ai/fashn-human-parser'
CACHE_NAME = 'fashn-human-parser'
LABELS = ('background', 'face', 'hair', 'top', 'dress', 'skirt', 'pants',
          'belt', 'bag', 'hat', 'scarf', 'glasses', 'arms', 'hands', 'legs',
          'feet', 'torso', 'jewelry')


class HumanParsingBackend(ABC):
    @abstractmethod
    def predict(self, image):
        """Return image-aligned class IDs, label table and provenance."""


def prepare_human_parser(cache=None, revision='main', accept_license=False, endpoint=None):
    if not accept_license:
        raise ValueError('人物解析权重使用 NVIDIA SegFormer 单独许可（非商业研究/评估）；须 --accept-model-license')
    directory = Path(cache or default_model_cache()) / CACHE_NAME
    resolved, endpoint = download_snapshot(MODEL_ID, revision, directory, MODEL_FILES, endpoint)
    with urllib.request.urlopen(LICENSE_URL, timeout=30) as response:
        license_text = response.read().decode('utf8')
    if 'NVIDIA Source Code License for SegFormer' not in license_text:
        raise ValueError('无法验证人物解析模型许可文本，不可推理')
    (directory / 'LICENSE.txt').write_text(license_text, encoding='utf8')
    record = {'model_id': MODEL_ID, 'revision': resolved, 'download_endpoint': endpoint,
              'license': 'NVIDIA SegFormer (non-commercial research/evaluation)',
              'license_url': LICENSE_URL,
              'files': {name: sha256(directory / name) for name in [*MODEL_FILES, 'LICENSE.txt']}}
    write_json(directory / 'static2live-model.json', record)
    return directory


class ModelHumanParsing(ModelSegmentation, HumanParsingBackend):
    model_id = MODEL_ID
    cache_name = CACHE_NAME
    backend_name = 'fashn-human-parser'
    prepare_kind = 'human-parsing'

    def predict(self, image):
        labels, table, provenance = super().predict(image)
        expected = dict(enumerate(LABELS))
        if table != expected:
            raise ValueError('人物解析类别表与已验证模型不一致，不猜测类别编号')
        provenance['limitations'] = [
            'semantic masks, not alpha matting or individual hair strands',
            'HF processor uses the published local configuration, not cv2 INTER_AREA training preprocessing',
            'eyes are protected through face class, not separately detected',
        ]
        return labels, table, provenance


def human_regions(labels, table, protection_margin_px=2):
    """Create semantic masks plus a conservative union protection mask.

    The halo is a protection guard, not a fake prediction. It is separately
    recorded and subtracts from every proposed deformable mask. A supplied
    backend must expose the actual labels; absent classes are errors, not guesses.
    """
    array = np.asarray(labels)
    if array.ndim != 2 or not np.issubdtype(array.dtype, np.integer) or array.size == 0:
        raise ValueError('人物解析标签必须是非空二维整数数组')
    if not set(np.unique(array)) <= set(table):
        raise ValueError('人物解析输出存在未知类别')
    names = {str(name).strip().lower(): key for key, name in table.items()}
    if len(names) != len(table):
        raise ValueError('人物解析类别名称重复')
    required = {'background', 'face', 'hair', 'hands', 'jewelry', 'glasses',
                'top', 'dress', 'skirt', 'pants', 'scarf', 'belt', 'bag',
                'hat', 'arms', 'legs', 'feet', 'torso'}
    if not required <= names.keys():
        raise ValueError('人物解析类别表缺少必需语义，不能伪造保护区')
    if type(protection_margin_px) != int or not 0 <= protection_margin_px <= 32:
        raise ValueError('保护区外扩须为0–32整数画布像素')
    groups = {
        'face': {'face'}, 'hands': {'hands'}, 'hair': {'hair'},
        'cloth': {'top', 'dress', 'skirt', 'pants', 'scarf'},
        'body': {'arms', 'hands', 'legs', 'feet', 'torso'},
        'person': required - {'background'},
        'protected': {'face', 'hands', 'jewelry', 'glasses', 'belt', 'bag', 'hat'},
    }
    masks, records = {}, {}
    for key, group in groups.items():
        ids = [names[name] for name in sorted(group)]
        mask = Image.fromarray(np.isin(array, ids).astype('uint8') * 255)
        masks[key] = mask
        records[key] = {'id': key, 'source': 'model', 'confirmed': True,
                        'labels': {str(i): table[i] for i in ids}}
    # Background islands enclosed by the person's silhouette are not reliable
    # transparent holes (real inference can label eyes/mouth as background).
    # Preserve class labels, but conservatively protect these islands and cover
    # particles there. Never extend this guard into edge-connected background.
    padded = ImageOps.expand(masks['person'], border=1, fill=0)
    ImageDraw.floodfill(padded, (0, 0), 128)
    islands = Image.fromarray((np.asarray(padded)[1:-1, 1:-1] == 0).astype('uint8') * 255)
    masks['person'] = ImageChops.lighter(masks['person'], islands)
    masks['protected'] = ImageChops.lighter(masks['protected'], islands)
    records['person']['enclosed_background_policy'] = '4-connected silhouette holes covered; raw labels unchanged'
    records['protected']['enclosed_background_guard_px'] = int(np.count_nonzero(np.asarray(islands)))
    if protection_margin_px:
        masks['protected'] = masks['protected'].filter(ImageFilter.MaxFilter(2 * protection_margin_px + 1))
    records['protected']['guard_px'] = protection_margin_px
    records['protected']['eyes_policy'] = 'covered by face; no separate eye detection'
    for key in ('hair', 'cloth'):
        masks[key] = ImageChops.subtract(masks[key], masks['protected'])
        records[key]['protection_subtracted'] = True
    return masks, records
