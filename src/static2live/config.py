from copy import deepcopy
import math
from importlib.resources import files
from pathlib import Path

import jsonschema
import yaml
from .effects import complete_effect, validate_effects
from .runtime_options import DEFAULTS as RUNTIME_DEFAULTS, SCHEMAS as RUNTIME_SCHEMAS, validate_options
from .framing import DEFAULT as FRAMING_DEFAULT, SCHEMA as FRAMING_SCHEMA, aspect_ratio

DEFAULTS = {"preset": "general_balanced", "target": "web", "max_edge": 2048,
            "device": "cpu", "parallax": {"fraction": 0.003, "response_seconds": 0.15},
            "mode":"lite","parallax_enabled":True,"seed":1337,"effects":[],
            "native_sway":False,"sway_amplitude_px":1,"human_parsing":False,"auto_plan":True,
            "hair_sway":{"enabled":False,"amplitude_px":2,"period_seconds":5.5,"phase":0.3},
            "cloth_sway":{"enabled":False,"amplitude_px":0.5,"period_seconds":6.5,"phase":1.3}}
DEFAULTS.update(deepcopy(RUNTIME_DEFAULTS))
DEFAULTS['framing']=deepcopy(FRAMING_DEFAULT)
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": list(DEFAULTS),
    "properties": {
        "preset": {"enum": ["portrait_subtle", "general_balanced", "landscape_soft","warm_portrait","rainy_city","snow_soft","anime_chill","snow_forest","cyberpunk"]},
        "target": {"enum": ["web", "wallpaper-engine"]}, "device": {"enum": ["cpu", "cuda"]},
        "max_edge": {"type": "integer", "minimum": 64, "maximum": 8192},
        "mode":{"enum":["lite","smart"]},"parallax_enabled":{"type":"boolean"},
        "seed":{"type":"integer","minimum":0,"maximum":4294967295},
        "effects":{"type":"array","maxItems":6},
        "native_sway":{"type":"boolean"},"sway_amplitude_px":{"type":"number","minimum":0,"maximum":4},
        "human_parsing":{"type":"boolean"},
        "auto_plan":{"type":"boolean"},
        "hair_sway":{"type":"object"},"cloth_sway":{"type":"object"},
        "parallax": {"type": "object", "additionalProperties": False,
                     "required": ["fraction", "response_seconds"], "properties": {
                         "fraction": {"type": "number", "minimum": 0, "maximum": 0.01},
                         "response_seconds": {"type": "number", "minimum": 0.01, "maximum": 2}}}
    }
}
SCHEMA['properties'].update(RUNTIME_SCHEMAS)
SCHEMA['properties']['framing']=FRAMING_SCHEMA


def merge(base, update):
    result = deepcopy(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def explicit_config(config_path=None,overrides=None):
    user = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) if config_path else {}
    user = {} if user is None else user
    if not isinstance(user, dict):
        raise ValueError("配置必须是 YAML 对象")
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    return user,overrides


def load_config(config_path=None, overrides=None, recommended_preset=None, suggestions=None):
    user,overrides=explicit_config(config_path,overrides)
    preset = overrides.get("preset", user.get("preset", recommended_preset or DEFAULTS["preset"]))
    if preset not in SCHEMA["properties"]["preset"]["enum"]:
        raise ValueError(f"未知 preset: {preset}")
    preset_config = yaml.safe_load(files("static2live").joinpath(f"presets/{preset}.yaml").read_text())
    result = merge(merge(merge(merge(DEFAULTS,suggestions or {}), preset_config), user), overrides)
    if result.get("target") not in ['web','wallpaper-engine']:
        raise ValueError("V0.3 仅支持 web / wallpaper-engine；其他目标尚未实现")
    jsonschema.validate(result, SCHEMA)
    if result['framing']['aspect'] is not None:aspect_ratio(result['framing']['aspect'])
    elif result['framing']['anchor']!='center':raise ValueError('crop anchor 需要同时设置 crop aspect；未设置比例时不裁切')
    validate_options(result)
    if not all(math.isfinite(value) for value in result["parallax"].values()):
        raise ValueError("视差参数必须为有限数值")
    result['effects']=[complete_effect(raw) for raw in result['effects']]
    validate_effects(result['effects'])
    if not math.isfinite(result['sway_amplitude_px']):raise ValueError('摇摆幅度必须有限')
    if result['native_sway'] and result['target']!='wallpaper-engine':raise ValueError('native_sway 仅用于原生 Adapter，不宣称 Web 支持此效果')
    from .sway import validate_sway
    for kind in ('hair','cloth'):
        validate_sway(result[kind+'_sway'],(8192,8192))
    if result['human_parsing'] and result['mode']!='smart':
        raise ValueError('Lite 不下载或调用人物解析模型；手工导入hair/cloth/protected蒙版即可')
    return result
