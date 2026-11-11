"""Shared local asset analysis for generation and the read-only analyze CLI."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from .config import load_config,explicit_config
from .depth import ModelDepth,SuppliedDepth
from .segmentation import ModelSegmentation,semantic_regions
from .human_parser import ModelHumanParsing,human_regions
from .regions import canonical_image,load_regions
from .storage import sha256
from .planning import conservative_protection,analyze_features,recommend,make_plan
from .framing import crop_box


@dataclass
class PreparedAssets:
    source:Path
    original_hash:str
    config:dict
    image:object
    original_size:tuple
    depth:object
    provenance:dict
    masks:dict
    records:dict
    labels:object
    table:dict
    segmentation:dict
    human_labels:object
    human_table:dict
    human:dict
    planning:dict
    crop:object=None

    def report(self):
        return {'input':{'name':self.source.name,'sha256':self.original_hash},'original_size':list(self.original_size),
            'output_size':list(self.image.size),'planning':self.planning,'config':self.config,
            'depth':self.provenance,'segmentation':self.segmentation,'human_parsing':self.human,
            'crop':list(self.crop) if self.crop is not None else None,
            'generated':False,'runtime_status':'not_tested'}


def prepare_assets(input_path,config_path=None,overrides=None,depth_map=None,model_cache=None,regions_path=None):
    source=Path(input_path).resolve(strict=True);original_hash=sha256(source)
    initial=load_config(config_path,overrides);image,original_size=canonical_image(source,initial['max_edge'],initial['framing'])
    crop=crop_box(original_size,initial['framing'])
    depth=None;provenance={'backend':'disabled','reason':'explicit parallax_enabled=false; no depth inference performed'}
    if initial['parallax_enabled']:
        backend=SuppliedDepth(depth_map,original_size,crop) if depth_map else ModelDepth(model_cache,initial['device'])
        depth,provenance=backend.predict(image);depth=np.asarray(depth,np.float32)
        if depth.shape!=(image.height,image.width) or not np.isfinite(depth).all() or depth.min()<0 or depth.max()>1:
            raise ValueError('深度后端返回了无效数组')
    masks,records={},{};segmentation={'backend':'none','mode':initial['mode']};labels=None;table={}
    if initial['mode']=='smart':
        labels,table,segmentation=ModelSegmentation(model_cache,initial['device']).predict(image)
        masks,records=semantic_regions(labels,table)
    human={'backend':'disabled'};human_labels=None;human_table={}
    if initial['human_parsing']:
        human_labels,human_table,human=ModelHumanParsing(model_cache,initial['device']).predict(image)
        parsed,parsed_records=human_regions(human_labels,human_table);masks.update(parsed);records.update(parsed_records)
    if regions_path:
        imported,metadata,origin=load_regions(regions_path,image.size,original_hash,original_size,crop)
        for key in imported:
            if key in records:metadata[key]['previous_source']=records[key]
        masks.update(imported);records.update(metadata);segmentation['user_override']=origin
    config=initial
    if config['auto_plan']:
        guard,record=conservative_protection(masks)
        if guard is not None:masks['protected']=guard;records['protected']=record
        proposal=recommend(analyze_features(image,masks),masks)
        config=load_config(config_path,overrides,proposal['preset'],proposal['suggestions'])
        for key in ('mode','max_edge','device','parallax_enabled','human_parsing','framing'):
            if config[key]!=initial[key]:raise ValueError('自动规划不得静默切换分析后端、尺寸或视差状态')
    user,cli=explicit_config(config_path,overrides)
    plan=make_plan(image,masks,config,'preset' in user or 'preset' in cli)
    if sha256(source)!=original_hash:raise ValueError('分析期间输入文件改变')
    return PreparedAssets(source,original_hash,config,image,original_size,depth,provenance,masks,records,labels,table,
        segmentation,human_labels,human_table,human,plan,crop)
