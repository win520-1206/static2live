"""Explicit model downloads with official metadata verification, including mirrors."""
import hashlib
from pathlib import Path
from .storage import sha256

ENDPOINTS=['https://huggingface.co','https://hf-mirror.com']


def download_snapshot(model_id,revision,directory,names,endpoint=None):
    from huggingface_hub import HfApi,snapshot_download
    endpoint=endpoint or ENDPOINTS[0]
    if endpoint not in ENDPOINTS: raise ValueError('下载源仅支持官方或 hf-mirror.com HTTPS')
    # The mirror must not select the revision or supply the expected hashes.
    info=HfApi(endpoint=ENDPOINTS[0]).model_info(model_id,revision=revision,files_metadata=True)
    metadata={s.rfilename:s for s in info.siblings}
    if not set(names)<=set(metadata): raise ValueError('官方快照缺少必需文件')
    directory=Path(directory)
    snapshot_download(model_id,revision=info.sha,local_dir=str(directory),allow_patterns=names,endpoint=endpoint)
    for name in names:
        path=directory/name;sibling=metadata[name]
        lfs=sibling.lfs
        if lfs:
            expected=lfs.get('sha256') if isinstance(lfs,dict) else lfs.sha256
            actual=sha256(path)
        else:
            raw=path.read_bytes();expected=sibling.blob_id
            actual=hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
        if not expected or actual!=expected: raise ValueError(f'官方文件校验失败: {name}；保留文件供检查，不可推理')
    return info.sha,endpoint
