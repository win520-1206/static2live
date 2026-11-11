"""Smart backend: explicit prepare only, local-only inference, no Lite fallback."""
from abc import ABC,abstractmethod
from pathlib import Path
import urllib.request
import numpy as np
from PIL import Image
from .storage import default_model_cache,read_json,write_json,sha256,safe_resource
from .model_download import download_snapshot

MODEL_ID='nvidia/segformer-b0-finetuned-ade-512-512'
LICENSE_URL='https://raw.githubusercontent.com/NVlabs/SegFormer/master/LICENSE'
MODEL_FILES=['config.json','preprocessor_config.json','model.safetensors','README.md']


class SegmentationBackend(ABC):
    @abstractmethod
    def predict(self,image):
        """Return class IDs, actual label table and recorded provenance."""


def resize_class_logits(logits,size):
    """Exact classwise interpolation with bounded channel batches, not fake masks."""
    import torch
    best=torch.full(size,float('-inf'),device=logits.device)
    ids=torch.zeros(size,dtype=torch.uint8,device=logits.device)
    batch=max(1,min(8,32_000_000//(size[0]*size[1])))
    for start in range(0,logits.shape[1],batch):
        resized=torch.nn.functional.interpolate(logits[:,start:start+batch],size=size,mode='bilinear',align_corners=False)[0]
        values,indices=resized.max(0);improved=values>best
        ids[improved]=(indices[improved]+start).to(torch.uint8);best[improved]=values[improved]
    return ids


def prepare_segmentation(cache=None,revision='main',accept_license=False,endpoint=None):
    if not accept_license:
        raise ValueError('先阅读 NVIDIA SegFormer 许可（仅非商业研究/评估）；显式准备须 --accept-model-license')
    directory=Path(cache or default_model_cache())/'segformer-b0-ade'
    resolved,endpoint=download_snapshot(MODEL_ID,revision,directory,MODEL_FILES,endpoint)
    with urllib.request.urlopen(LICENSE_URL,timeout=30) as response:
        license_text=response.read().decode('utf8')
    if 'NVIDIA Source Code License for SegFormer' not in license_text:
        raise ValueError('无法验证模型许可文本')
    (directory/'LICENSE.txt').write_text(license_text,encoding='utf8')
    record={'model_id':MODEL_ID,'revision':resolved,'download_endpoint':endpoint,'license':'NVIDIA SegFormer (non-commercial research/evaluation)',
            'license_url':LICENSE_URL,'files':{n:sha256(directory/n) for n in [*MODEL_FILES,'LICENSE.txt']}}
    write_json(directory/'static2live-model.json',record)
    return directory


class ModelSegmentation(SegmentationBackend):
    model_id=MODEL_ID
    cache_name='segformer-b0-ade'
    backend_name='segformer-b0-ade'
    prepare_kind='segmentation'

    def __init__(self,cache=None,device='cpu'):
        self.directory=Path(cache or default_model_cache())/self.cache_name;self.device=device

    def predict(self,image):
        if not (self.directory/'static2live-model.json').is_file():
            raise ValueError(f'模型未准备。显式运行 static2live models prepare --kind {self.prepare_kind} --accept-model-license；不会自动下载或回退 Lite。')
        record=read_json(self.directory/'static2live-model.json')
        if record.get('model_id')!=self.model_id or not set([*MODEL_FILES,'LICENSE.txt'])<=set(record.get('files',{})):
            raise ValueError('分割模型记录身份或必需文件无效')
        for name,digest in record['files'].items():
            if sha256(safe_resource(self.directory,name))!=digest: raise ValueError(f'分割模型哈希失败: {name}')
        try:
            import torch
            from transformers import AutoImageProcessor,AutoModelForSemanticSegmentation
        except ImportError as error:
            raise ValueError('Smart 需要 smart 可选依赖；Lite 不需要') from error
        if self.device=='cuda' and not torch.cuda.is_available(): raise ValueError('请求 CUDA 但不可用')
        processor=AutoImageProcessor.from_pretrained(self.directory,local_files_only=True,use_fast=False)
        model=AutoModelForSemanticSegmentation.from_pretrained(self.directory,local_files_only=True).to(self.device).eval()
        inputs={k:v.to(self.device) for k,v in processor(images=image,return_tensors='pt').items()}
        with torch.inference_mode():
            logits=model(**inputs).logits
            labels=resize_class_logits(logits,image.size[::-1]).cpu().numpy()
        table={int(k):v.strip().lower() for k,v in model.config.id2label.items()}
        if not set(np.unique(labels))<=set(table): raise ValueError('模型输出类别与类别表不一致')
        return labels,table,{**record,'backend':self.backend_name,'device':self.device,'torch':torch.__version__,
                             'preprocessing':'recorded local AutoImageProcessor; no remote code'}


def semantic_regions(labels,table):
    groups={'person':{'person'},'sky':{'sky'},'water':{'water','sea','river','lake','swimming pool'}}
    masks,records={},{}
    for key,names in groups.items():
        ids=[i for i,name in table.items() if name in names]
        if not ids: raise ValueError(f'模型类别表缺少 {key}，不能伪造类别')
        mask=np.isin(labels,ids).astype('uint8')*255
        if mask.any():
            masks[key]=Image.fromarray(mask)
            records[key]={'id':key,'source':'model','confirmed':True,'labels':{str(i):table[i] for i in ids}}
    return masks,records
