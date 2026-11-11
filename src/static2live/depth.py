from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
from PIL import Image

from .storage import default_model_cache, read_json, sha256, write_json, safe_resource
from .model_download import download_snapshot

MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf"


class DepthBackend(ABC):
    @abstractmethod
    def predict(self, image):
        """Return float32 near-white relative depth in [0,1] and provenance."""


def normalize_depth(raw):
    raw = np.asarray(raw, dtype=np.float32)
    if raw.ndim != 2 or not np.isfinite(raw).all():
        raise ValueError("深度必须是有限的二维数组")
    lo, hi = float(raw.min()), float(raw.max())
    return np.zeros_like(raw) if hi - lo < 1e-8 else (raw - lo) / (hi - lo)


class SuppliedDepth(DepthBackend):
    def __init__(self, path, original_size, crop=None):
        self.path, self.original_size = Path(path), original_size
        self.crop=crop

    def predict(self, image):
        with Image.open(self.path) as source:
            if source.size != self.original_size:
                raise ValueError("用户深度图尺寸必须与 EXIF 转正后的输入图片一致")
            if source.mode not in ("L", "I", "I;16", "F"):
                raise ValueError("用户深度图必须是单通道灰度；白色表示更近")
            raw = np.asarray(source, dtype=np.float32)
        depth = normalize_depth(raw)
        canonical=Image.fromarray(depth, "F")
        if self.crop is not None:canonical=canonical.crop(self.crop)
        resized = canonical.resize(image.size, Image.Resampling.BILINEAR)
        record={"backend": "supplied", "sha256": sha256(self.path), "near_white": True}
        if self.crop is not None:record['crop_box']=list(self.crop)
        return np.clip(np.asarray(resized), 0, 1), record


def prepare_model(cache=None, revision="main", endpoint=None):
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as error:
        raise ValueError("请先安装可选依赖: pip install -e '.[depth]'") from error
    cache = Path(cache or default_model_cache())
    names = ["config.json", "preprocessor_config.json", "model.safetensors", "README.md"]
    snapshot=cache/'depth-anything-v2-small'
    resolved,endpoint=download_snapshot(MODEL_ID,revision,snapshot,names,endpoint)
    for name in names:
        if not (snapshot / name).is_file():
            raise ValueError(f"模型快照缺少 {name}")
    record = {"model_id": MODEL_ID, "revision": resolved, "download_endpoint":endpoint, "license": "Apache-2.0",
              "files": {name: sha256(snapshot / name) for name in names}}
    write_json(snapshot / "static2live-model.json", record)
    return snapshot


class ModelDepth(DepthBackend):
    def __init__(self, cache=None, device="cpu"):
        self.directory = Path(cache or default_model_cache()) / "depth-anything-v2-small"
        self.device = device

    def predict(self, image):
        if not (self.directory / "static2live-model.json").is_file():
            raise ValueError("本地模型未准备。运行 static2live models prepare（可指定 --model-cache），或使用 --depth-map。生成不会联网。")
        record = read_json(self.directory / "static2live-model.json")
        required = {"config.json", "preprocessor_config.json", "model.safetensors", "README.md"}
        if record.get("model_id") != MODEL_ID or not required <= set(record.get("files", {})):
            raise ValueError("本地模型记录缺少官方模型身份或必需文件")
        for name, digest in record["files"].items():
            if sha256(safe_resource(self.directory, name)) != digest:
                raise ValueError(f"模型文件校验失败: {name}")
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        except ImportError as error:
            raise ValueError("深度推理需要可选依赖: pip install -e '.[depth]'") from error
        if self.device == "cuda" and not torch.cuda.is_available():
            raise ValueError("请求 CUDA，但当前 PyTorch 无可用 CUDA")
        torch.manual_seed(0)
        processor = AutoImageProcessor.from_pretrained(self.directory, local_files_only=True, use_fast=False)
        model = AutoModelForDepthEstimation.from_pretrained(self.directory, local_files_only=True).to(self.device).eval()
        inputs = {k: v.to(self.device) for k, v in processor(images=image, return_tensors="pt").items()}
        with torch.inference_mode():
            prediction = model(**inputs).predicted_depth
            prediction = torch.nn.functional.interpolate(prediction.unsqueeze(1), size=image.size[::-1],
                                                          mode="bicubic", align_corners=False)[0, 0]
        # This official checkpoint predicts relative inverse depth (larger = nearer).
        return normalize_depth(prediction.cpu().numpy()), {"backend": "depth-anything-v2-small", **record,
                                                          "device": self.device, "torch": torch.__version__, "near_white": True}
