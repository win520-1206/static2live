"""Optional native adapter. Uses installed legal editor template and real compiler."""
from copy import deepcopy
from pathlib import Path
import math
import os
import shutil
import subprocess
import tempfile
import numpy as np
from PIL import Image, ImageFilter, ImageChops
from .storage import read_json, write_json, sha256, safe_resource
from .native_runtime import active as runtime_active, runtime_effect, export_resources as export_runtime_resources
from .native_runtime import properties as runtime_properties, validate_resources as validate_runtime_resources
from .pointer import has_subject, subject_pointer_guard, RIGID_POLICY, human_fragment, validate_pointer_policy

class AdapterUnavailable(ValueError):
    pass


def find_engine(explicit=None):
    if explicit:
        candidates=[Path(explicit)]
    elif os.name=='nt':
        candidates=[]
        if os.getenv('STATIC2LIVE_WE_PATH'): candidates.append(Path(os.environ['STATIC2LIVE_WE_PATH']))
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam') as key:
                steam=Path(winreg.QueryValueEx(key,'SteamPath')[0])
            candidates.append(steam/'steamapps/common/wallpaper_engine')
            import re
            vdf=steam/'steamapps/libraryfolders.vdf'
            if vdf.exists():
                for entry in re.findall(r'"path"\s+"([^"]+)"',vdf.read_text(encoding='utf8')):
                    candidates.append(Path(entry.replace('\\\\','\\'))/'steamapps/common/wallpaper_engine')
        except (OSError,ImportError): pass
        candidates.append(Path(os.getenv('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Steam/steamapps/common/wallpaper_engine')
    else: candidates=[]
    for root in candidates:
        root=root.resolve()
        if (root/'wallpaper64.exe').is_file() and (root/'bin/resourcecompiler64.exe').is_file(): return root
    raise AdapterUnavailable('未找到 Wallpaper Engine 与资源编译器；已保留 Web Export。使用 --engine-path 指定安装目录')


def copy_tree(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination): raise ValueError('模板与输出目录必须独立')
    for p in source.rglob('*'):
        if p.is_symlink() or not p.resolve().is_relative_to(source): raise ValueError('模板不允许符号链接或越界联接')
    shutil.copytree(source,destination)


def compile_texture(engine,path):
    path=Path(path).resolve();dest=path.with_suffix('.tex')
    write_json(path.with_suffix('.tex-json'),{'format':'rgba8888','clampuvs':True,'nonpoweroftwo':True,'nomip':True})
    run=subprocess.run([str(engine/'bin/resourcecompiler64.exe'),'-tex','-i',str(path),'-o',str(dest)],
        cwd=path.parent,timeout=60,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    log={'input':path.name,'returncode':run.returncode,'output':run.stdout.decode('utf8',errors='replace')}
    if run.returncode or not dest.exists() or dest.stat().st_size<16: raise ValueError('真实纹理编译失败: '+str(log))
    if not dest.read_bytes().startswith(b'TEXV'): raise ValueError('编译输出不是有效 TEX 头')
    return log


def scalar_script(key,base):
    return ("'use strict'; let factor=1; export function applyUserProperties(p){"
        f"if(p.hasOwnProperty('{key}')) factor=Math.max(0,Math.min(1,p.{key}/100));"
        f"}} export function update(value){{return {base:.12g}*factor;}}")


def sway_sampling_mask(mask, amplitude):
    """Expand inverse-sampling support, not the user's semantic region.

    A mask ending exactly on the silhouette pins every exterior destination
    pixel, so a solid-colour object can contract but cannot sway outward.
    Keep a full-strength halo for the bounded displacement, then feather it.
    """
    radius=math.ceil(amplitude)+2
    return mask.convert('L').filter(ImageFilter.MaxFilter(radius*2+1)).filter(ImageFilter.GaussianBlur(1))


def depth_effect(template_object,width,height,amplitude):
    effect={'file':'effects/s2l_depth/effect.json','id':32,'name':'Static2Live bounded depth UV'}
    effect['visible']={'user':'parallaxenabled','value':True}
    sx=amplitude/width;sy=amplitude/height
    script=("'use strict'; let factor=1; export function applyUserProperties(p){"
        "if(p.hasOwnProperty('parallaxstrength')) factor=Math.max(0,Math.min(1,p.parallaxstrength/100));}"
        f" export function update(value){{return new Vec2({sx:.12g}*factor,{sy:.12g}*factor);}}")
    effect['passes']=[{'id':33,'constantshadervalues':{
        'scale':{'value':f'{sx:.12g} {sy:.12g}','script':script}},'textures':[None,'s2l_depth']}]
    return effect


def human_effect(width,height,amplitude,sways,pointer_guard=False):
    """One sampling pass for depth and sway; protection precedes both motions."""
    sx,sy=amplitude/width,amplitude/height
    script=("'use strict'; let factor=1; let enabled=true; export function applyUserProperties(p){"
        "if(p.hasOwnProperty('parallaxstrength')) factor=Math.max(0,Math.min(1,p.parallaxstrength/100));"
        "if(p.hasOwnProperty('parallaxenabled')) enabled=p.parallaxenabled;}"
        f" export function update(value){{let f=enabled?factor:0;return new Vec2({sx:.12g}*f,{sy:.12g}*f);}}")
    constants={'scale':{'value':f'{sx:.12g} {sy:.12g}','script':script}}
    for kind in ('hair','cloth'):
        item=next((s for s in sways if s['kind']==kind),None)
        base=item['amplitude_px']/width if item else 0
        key=kind+'motionstrength';toggle=kind+'motionenabled'
        control=("'use strict'; let factor=1; let enabled=true; export function applyUserProperties(p){"
            f"if(p.hasOwnProperty('{key}')) factor=Math.max(0,Math.min(1,p.{key}/100));"
            f"if(p.hasOwnProperty('{toggle}')) enabled=p.{toggle};}}"
            f" export function update(value){{return enabled?{base:.12g}*factor:0;}}")
        constants.update({kind+'Amplitude':{'value':base,'script':control},
                          kind+'Rate':2*math.pi/item['period_seconds'] if item else 0,
                          kind+'Phase':item['phase'] if item else 0})
    return {'file':'effects/s2l_human/effect.json','id':32,'name':'Static2Live protected human motion',
            'passes':[{'id':33,'constantshadervalues':constants,
                       'textures':[None,'s2l_depth','s2l_hair_weight','s2l_cloth_weight','s2l_pointer_guard' if pointer_guard else 's2l_protected']}]}


def plan_native(motion,config):
    """Pure mapping, separately recorded; does not analyze the image."""
    effects=[];unsupported=[]
    if motion.get('runtime'):
        r=motion['runtime']
        if r['performance_profile']!='inherit': unsupported.append('performance profile: Web budget only; native engine owns FPS and render settings')
        if r['display']['viewport']!=[0,0,1,1]: unsupported.append('display viewport: Web spanning crop only; configure native monitor layout in engine')
    for e in motion.get('effects',[]):
        if not e['enabled'] or e['intensity']==0 or e['count']==0 and e['type'] in ['rain','snow','dust','fog']: continue
        if e['type'] not in ['rain','snow','dust','fog'] or e['region']!='full':
            unsupported.append(e['type']+': native V0.3 supports full-canvas particles only; use retained Web version')
        else: effects.append(deepcopy(e))
    sway=config.get('native_sway',False)
    region=motion.get('regions',{}).get('other')
    if sway and (not region or not region['confirmed'] or region['coverage']==0):
        raise ValueError('--native-sway 需要已确认、非空的 other 区域；不会自动识别发梢或植物')
    if sway and region['source']=='model': raise ValueError('Native Sway 只接受显式手画/导入/确认规则区域')
    if sway and config['sway_amplitude_px']>min(motion['canvas'].values())*.01:
        raise ValueError('Native Sway 超过画布短边1%')
    return {'version':'0.3','type':'native-scene','motion_version':motion['version'],
        'canvas':motion['canvas'],'parallax':motion['parallax'],'parallax_enabled':motion.get('parallax_enabled',True),
        'particles':effects,'sway':{'enabled':sway,'region':'other' if sway else None,'amplitude_px':config.get('sway_amplitude_px',1)},
        'unsupported':unsupported,'seed_policy':'Native engine owns particle randomness; not identical to Web seeded sequence',
        'depth_policy':('bounded-uv-v1: transported weight = 0.2 + 0.8 * canonical depth; clamped pointer * amplitude_px/canvas; white-near'
            if motion.get('parallax_enabled',True) else 'disabled explicitly; no depth inference; inactive texture placeholder only'),
        'human_sways':deepcopy(motion.get('sways',[])),
        'protected_motion':bool((has_subject(motion) or motion.get('regions',{}).get('protected',{}).get('coverage',0)>0) and motion['parallax']['amplitude_px']>0 and not motion.get('sways')),
        'runtime_effect':deepcopy(motion.get('runtime')) if runtime_active(motion.get('runtime')) else None,
        'particle_policy':'Native sprite particles; approximate Web appearance, not pixel-identical'}


def export_native(root,motion,config,engine_path=None,template_path=None):
    root=Path(root);engine=find_engine(engine_path)
    source=Path(template_path).resolve() if template_path else engine/'assets/effects/depthparallax/preview'
    if not source.is_dir(): raise AdapterUnavailable('合法 Depth Parallax 编辑器模板不存在；保留 Web Export')
    scene=read_json(source/'scene.json');project=read_json(source/'project.json')
    if project.get('type')!='scene' or project.get('file')!='scene.json': raise ValueError('模板不是有效 Scene 工程')
    base=next((o for o in scene.get('objects',[]) if any(e.get('file')=='effects/depthparallax/effect.json' for e in o.get('effects',[]))),None)
    if not base: raise ValueError('V0.3 模板须含官方 Depth Parallax 图像对象，不猜测其他模板结构')
    template_hashes={p.relative_to(source).as_posix():sha256(p) for p in source.rglob('*') if p.is_file()}
    plan=plan_native(motion,config);out=root/'wallpaper-engine';copy_tree(source,out)
    if (plan['human_sways'] or plan['protected_motion'] or plan['runtime_effect']) and has_subject(motion):
        plan['pointer_policy']=RIGID_POLICY
    # Our packaged shader avoids official occlusion parameters that can collapse
    # depth response. Keep installed template/assets untouched and independently licensed.
    (out/'effects/s2l_depth').mkdir(parents=True,exist_ok=True)
    (out/'materials/effects').mkdir(parents=True,exist_ok=True)
    (out/'shaders/effects').mkdir(parents=True,exist_ok=True)
    for suffix in ['vert','frag']:
        shutil.copy2(Path(__file__).parent/'native'/f's2l_depth.{suffix}',out/'shaders/effects'/f's2l_depth.{suffix}')
    write_json(out/'materials/effects/s2l_depth.json',{'passes':[{'shader':'effects/s2l_depth',
        'blending':'normal','depthtest':'disabled','depthwrite':'disabled','cullmode':'nocull'}]})
    write_json(out/'effects/s2l_depth/effect.json',{'version':1,'name':'Static2Live bounded depth UV','group':'distort',
        'passes':[{'material':'materials/effects/s2l_depth.json'}],
        'dependencies':['materials/effects/s2l_depth.json','shaders/effects/s2l_depth.vert','shaders/effects/s2l_depth.frag']})
    w,h=motion['canvas']['width'],motion['canvas']['height'];logs=[]
    def texture(name,image):
        path=out/'materials'/f'{name}.png';image.save(path);logs.append(compile_texture(engine,path))
    with Image.open(root/'assets/image.png') as im: image=im.convert('RGBA')
    texture('s2l_image',image)
    if motion['assets']['depth']:
        with Image.open(root/motion['assets']['depth']) as d: depth=np.asarray(d,dtype=np.float32)/255
        transported_depth=Image.fromarray(np.round((.2+.8*depth)*255).astype('uint8')).convert('RGBA')
    else: transported_depth=Image.new('RGBA',(w,h),(51,51,51,255))
    if plan['runtime_effect'] and has_subject(motion):
        transported_depth=Image.merge('RGBA',(transported_depth.getchannel('R'),subject_pointer_guard(root,motion),
            transported_depth.getchannel('B'),Image.new('L',(w,h),255)))
    texture('s2l_depth',transported_depth)
    if plan['runtime_effect']:
        if plan['sway']['enabled']:raise ValueError('原生V0.6保护流程不能叠加后置Foliage形变；请使用独立区域/配置版本')
        export_runtime_resources(root,out,motion,texture)
    if (plan['human_sways'] or plan['protected_motion']) and not plan['runtime_effect']:
        if plan['sway']['enabled']:raise ValueError('人物保护sway与手选Foliage不能叠加，避免后置形变绕过保护区')
        for key,name in [('hair_sway','s2l_hair_weight'),('cloth_sway','s2l_cloth_weight'),('protected','s2l_protected')]:
            region=motion['regions'].get(key)
            if region:
                with Image.open(root/region['asset']) as mask:texture(name,mask.convert('RGBA'))
            else:texture(name,Image.new('RGBA',(w,h),(0,0,0,255)))
        if plan.get('pointer_policy') in ('subject-anchored-v1',RIGID_POLICY):
            texture('s2l_pointer_guard',subject_pointer_guard(root,motion).convert('RGBA'))
        (out/'effects/s2l_human').mkdir(parents=True,exist_ok=True)
        for suffix in ('vert','frag'):
            shader_source=Path(__file__).parent/'native'/f's2l_human.{suffix}'
            target=out/'shaders/effects'/f's2l_human.{suffix}'
            target.write_text(human_fragment(shader_source.read_text(encoding='utf8'),plan.get('pointer_policy')),encoding='utf8') if suffix=='frag' else shutil.copy2(shader_source,target)
        write_json(out/'materials/effects/s2l_human.json',{'passes':[{'shader':'effects/s2l_human',
            'blending':'normal','depthtest':'disabled','depthwrite':'disabled','cullmode':'nocull'}]})
        write_json(out/'effects/s2l_human/effect.json',{'version':1,'name':'Static2Live protected human motion','group':'distort',
            'passes':[{'material':'materials/effects/s2l_human.json'}],
            'dependencies':['materials/effects/s2l_human.json','shaders/effects/s2l_human.vert','shaders/effects/s2l_human.frag']})
    material=read_json(safe_resource(source,read_json(safe_resource(source,base['image']))['material']))
    material['passes'][0]['textures']=['s2l_image']
    write_json(out/'materials/s2l_image.json',material)
    write_json(out/'models/s2l_image.json',{'autosize':True,'material':'materials/s2l_image.json'})
    obj=deepcopy(base);obj.update(id=28,name='Static2Live canonical image',image='models/s2l_image.json',
        origin=f'{w/2} {h/2} 0',size=f'{w} {h}',parallaxDepth='0 0',solid=True,visible=True,brightness=1,alpha=1,color='1 1 1')
    # Mathematical worst-case UV displacement + per-viewport room. No hidden-background reconstruction.
    margin=motion['parallax']['overscan_px']+ (config.get('sway_amplitude_px',1) if config.get('native_sway') else 0)+2
    if margin>=min(w,h)/2:raise ValueError('原生画布短边过小，无法提供安全留量；保留 Web 产物供检查')
    scale=1/(1-2*margin/min(w,h));obj['scale']=f'{scale} {scale} 1'
    obj['effects']=[depth_effect(base,w,h,motion['parallax']['amplitude_px'])] if plan['parallax_enabled'] else []
    if plan['human_sways'] or plan['protected_motion']:obj['effects']=[human_effect(w,h,motion['parallax']['amplitude_px'],plan['human_sways'],plan.get('pointer_policy') in ('subject-anchored-v1',RIGID_POLICY))]
    if plan['runtime_effect']:obj['effects']=[runtime_effect(w,h,motion['parallax']['amplitude_px'],plan['human_sways'],plan['runtime_effect'],plan.get('pointer_policy',False))]
    g=scene['general'];g.update(orthogonalprojection={'width':w,'height':h},cameraparallax=True,
        cameraparallaxamount=0,cameraparallaxmouseinfluence=1,cameraparallaxdelay=motion['parallax']['response_seconds'],
        camerashake=False,zoom=1,clearcolor='0 0 0',bloom=False)
    objects=[obj]
    properties={'parallaxenabled':{'type':'bool','text':'鼠标视差','value':plan['parallax_enabled'],'order':1},
        'parallaxstrength':{'type':'slider','text':'视差强度（%）','value':100,'min':0,'max':100,'order':2},
        'particlesenabled':{'type':'bool','text':'粒子效果','value':True,'order':3},
        'particleintensity':{'type':'slider','text':'粒子强度（%）','value':100,'min':0,'max':100,'order':4}}
    if plan['runtime_effect']:properties.update(runtime_properties(plan['runtime_effect']))
    if plan['human_sways']:
        for index,kind in enumerate(('hair','cloth')):
            active=any(s['kind']==kind for s in plan['human_sways'])
            properties[kind+'motionenabled']={'type':'bool','text':'发梢微动' if kind=='hair' else '衣料微动','value':active,'order':5+index*2}
            properties[kind+'motionstrength']={'type':'slider','text':('发梢' if kind=='hair' else '衣料')+'强度（%）','value':100,'min':0,'max':100,'order':6+index*2}
    yy,xx=np.indices((64,64));alpha=np.clip(1-np.hypot(xx-31.5,yy-31.5)/31.5,0,1)**.75
    sprite=np.ones((64,64,4),dtype='uint8')*255;sprite[:,:,3]=np.round(alpha*255).astype('uint8')
    if plan['particles']:
        texture('s2l_particle',Image.fromarray(sprite))
        write_json(out/'materials/s2l_particle.json',{'passes':[{'shader':'genericparticle','depthtest':'disabled',
            'depthwrite':'disabled','blending':'additive','cullmode':'nocull','textures':['s2l_particle']}]})
        # Dust must retain its warm colour against bright walls/tabletops.
        # Additive blending becomes indistinguishable against near-white RGB.
        if any(e['type']=='dust' for e in plan['particles']):
            write_json(out/'materials/s2l_dust.json',{'passes':[{'shader':'genericparticle','depthtest':'disabled',
                'depthwrite':'disabled','blending':'translucent','cullmode':'nocull','textures':['s2l_particle']}]})
    (out/'particles').mkdir(exist_ok=True)
    for index,e in enumerate(plan['particles']):
        particle_material='materials/s2l_dust.json' if e['type']=='dust' else 'materials/s2l_particle.json'
        if e['type']=='rain':
            rain=np.ones((64,64,4),dtype='uint8')*255
            rain[:,:,3]=0;rain[:,30:34,3]=np.round(np.sin(np.linspace(0,math.pi,64))*255).astype('uint8')[:,None]
            texture('s2l_rain',Image.fromarray(rain))
            write_json(out/'materials/s2l_rain.json',{'passes':[{'shader':'genericparticle','depthtest':'disabled',
                'depthwrite':'disabled','blending':'translucent','cullmode':'nocull','textures':['s2l_rain']}]})
            particle_material='materials/s2l_rain.json'
        color=' '.join(str(int(e['color'][i:i+2],16)) for i in [1,3,5]);speed=e['speed_px_s'];life=20 if e['type'] in ['dust','fog'] else (h+e['size_px']*2)/max(speed,1)
        alpha=min(1,e['intensity']*(.12 if e['type']=='fog' else 2.4 if e['type']=='dust' else .85))
        # Rain uses elongated sprites, not a point-emitter shower. Fog deliberately approximate.
        # Native sprite size is a diameter in canvas units. Tiny low-alpha dust
        # disappeared when a 2048px canvas was scaled to a desktop/editor preview.
        size=e['size_px']*(8 if e['type']=='fog' else 10 if e['type']=='dust' else 2)
        dust=e['type']=='dust'
        particle={'material':particle_material,'maxcount':e['count'],'starttime':life,
            'controlpoint':[{'id':0,'flags':0,'offset':'0 0 0'}],
            'emitter':[{'id':1,'name':'boxrandom','distancemax':f'{w/2} {h/2} 0','rate':e['count']/life}],
            'initializer':[{'id':2,'name':'lifetimerandom','min':life,'max':life},
                {'id':3,'name':'sizerandom','min':size*.7,'max':size},
                {'id':4,'name':'colorrandom','min':color,'max':color},
                {'id':5,'name':'alpharandom','min':alpha,'max':alpha},
                {'id':6,'name':'velocityrandom','min':f'{-speed*.3 if dust else -speed*.1} {-speed if e["type"] in ["rain","snow"] else speed*.6 if dust else speed*.2} 0',
                    'max':f'{speed*.3 if dust else speed*.1} {-speed if e["type"] in ["rain","snow"] else speed if dust else speed*.5} 0'}],
            'operator':[{'id':7,'name':'movement','gravity':'0 0 0','drag':0},
                {'id':8,'name':'alphafade','fadeintime':.1,'fadeouttime':.8 if dust else .2}], 'renderer':[{'id':9,'name':'sprite'}]}
        name=f's2l_{e["type"]}.json';write_json(out/'particles'/name,particle)
        objects.append({'id':100+index,'name':e['type'],'origin':f'{w/2} {h/2} 0','particle':'particles/'+name,
            'visible':{'user':'particlesenabled','value':True},
            'instanceoverride':{'count':1,'alpha':{'value':1,'script':scalar_script('particleintensity',1)}},
            'angles':'0 0 0','scale':'1 1 1','parallaxDepth':'0 0','solid':True})
    if any(e['exclude_person'] for e in plan['particles']) and 'person' in motion.get('regions',{}):
        # Same source pixels and same parallax effect, not a new segmented/repainted background.
        cover=image.copy()
        with Image.open(root/motion['regions']['person']['asset']) as mask:
            alpha=mask.copy()
        if 'protected' in motion['regions']:
            with Image.open(root/motion['regions']['protected']['asset']) as guard:alpha=ImageChops.lighter(alpha,guard)
        cover.putalpha(alpha)
        texture('s2l_person_cover',cover)
        covermat=deepcopy(material);covermat['passes'][0]['textures']=['s2l_person_cover']
        write_json(out/'materials/s2l_person_cover.json',covermat)
        write_json(out/'models/s2l_person_cover.json',{'autosize':True,'material':'materials/s2l_person_cover.json'})
        occluder=deepcopy(obj);occluder.update(id=120,name='Person particle occlusion (not reconstructed layer)',image='models/s2l_person_cover.json')
        objects.append(occluder)
        if any(not e['exclude_person'] for e in plan['particles']):plan['unsupported'].append('Mixed exclusion: cover excludes all native particles; Web retains per-effect semantics')
    if plan['sway']['enabled']:
        # Only explicit user-confirmed other mask. Does not create Hair Mask / Human Parsing.
        for section in ['materials','shaders']:
            shutil.copytree(engine/'assets/effects/foliagesway'/section,out/section,dirs_exist_ok=True)
        (out/'effects/foliagesway').mkdir(parents=True,exist_ok=True)
        shutil.copy2(engine/'assets/effects/foliagesway/effect.json',out/'effects/foliagesway/effect.json')
        with Image.open(root/motion['regions']['other']['asset']) as mask:
            texture('s2l_sway_mask',sway_sampling_mask(mask,plan['sway']['amplitude_px']).convert('RGBA'))
        plan['sway']['sampling_policy']='bounded halo: ceil(amplitude_px)+2 pixels dilation; 1px Gaussian feather; source mask unchanged'
        rng=np.random.default_rng(motion['seed']);texture('s2l_noise',Image.fromarray(rng.integers(0,256,(64,64,4),dtype=np.uint8),'RGBA'))
        # UV mode displacement has four sine terms and squared strength (official shader).
        strength=math.sqrt(plan['sway']['amplitude_px']/(.02*max(w,h)))
        properties['swayenabled']={'type':'bool','text':'手选区域摇摆','value':True,'order':5}
        properties['swaystrength']={'type':'slider','text':'摇摆强度（%）','value':100,'min':0,'max':100,'order':6}
        obj['effects'].append({'id':150,'file':'effects/foliagesway/effect.json','visible':{'user':'swayenabled','value':True},
            'passes':[{'id':151,'combos':{'MODE':0,'MASK':1},'textures':[None,'s2l_sway_mask','s2l_noise'],
                'constantshadervalues':{'strength':{'value':strength,'script':scalar_script('swaystrength',strength)},
                    'speeduv':.8,'power':1,'ratio':h/w,'scale':.05,'phase':.5,'scrolldirection':0}}]})
        for item in objects:
            if item.get('id')==120:item['effects']=deepcopy(obj['effects'])
    for i,item in enumerate(objects):
        for j,effect in enumerate(item.get('effects',[])):
            effect['id']=200+i*20+j*4
            for k,p in enumerate(effect.get('passes',[])):p['id']=effect['id']+1+k
    scene['objects']=objects;write_json(out/'scene.json',scene)
    project.update(title=f'Static2Live {root.name} – '+root.parent.name,type='scene',file='scene.json',visibility='private',preview='preview.jpg')
    project.pop('workshopid',None);project['general']={'properties':properties}
    # The editor detects this from SceneScript and persists the capability flag.
    # Export it up front so direct local playback need not open/save the editor.
    if plan['runtime_effect'] and plan['runtime_effect']['audio']['enabled']:
        project['general']['supportsaudioprocessing']=True
    write_json(out/'project.json',project);image.convert('RGB').resize((320,180)).save(out/'preview.jpg')
    plan.update(engine_version=read_json(engine/'version.json').get('version'),template={'source':str(source),'sha256':template_hashes},
        compiler={'path':str(engine/'bin/resourcecompiler64.exe'),'sha256':sha256(engine/'bin/resourcecompiler64.exe'),'runs':logs},
        external_requirements=['Wallpaper Engine built-in genericimage/particle shaders and common.h'],
        redistribution='Installed official template/effects: local licensed use only; not relicensed as project MIT')
    write_json(root/'native-plan.json',plan)
    return {'requested':'wallpaper-engine','actual':'native-scene','entry':'wallpaper-engine/project.json',
        'plan':'native-plan.json','warnings':plan['unsupported'],'runtime_status':'not_tested'}


def validate_native(root):
    root=Path(root);out=root/'wallpaper-engine';plan=read_json(root/'native-plan.json')
    project=read_json(out/'project.json');scene=read_json(out/'scene.json')
    if project.get('type')!='scene' or project.get('file')!='scene.json' or 'workshopid' in project: raise ValueError('原生 project 类型/入口/发布状态错误')
    props=project['general']['properties'];ids=[]
    for obj in scene['objects']:
        ids.append(obj['id'])
        if 'image' in obj:
            model=read_json(safe_resource(out,obj['image']));mat=read_json(safe_resource(out,model['material']))
            for p in mat['passes']:
                for name in p.get('textures',[]):
                    if name and not safe_resource(out,'materials/'+name+'.tex').is_file(): raise ValueError('纹理缺失: '+name)
        if 'particle' in obj:
            particle=read_json(safe_resource(out,obj['particle']))
            if not 0<=particle['maxcount']<=256: raise ValueError('原生粒子预算超限')
            mat=read_json(safe_resource(out,particle['material']))
            for p in mat['passes']:
                for name in p.get('textures',[]):
                    if name and not safe_resource(out,'materials/'+name+'.tex').is_file():raise ValueError('粒子纹理缺失')
        for e in obj.get('effects',[]):
            ids.append(e['id'])
            definition=read_json(safe_resource(out,e['file']))
            for dep in definition.get('dependencies',[]):
                if not safe_resource(out,dep).is_file(): raise ValueError('原生效果依赖缺失: '+dep)
            for p in e.get('passes',[]):
                ids.append(p['id'])
                for name in p.get('textures',[]):
                    if name and not safe_resource(out,'materials/'+name+'.tex').is_file(): raise ValueError('效果纹理缺失: '+name)
    if len(ids)!=len(set(ids)): raise ValueError('原生对象 ID 重复')
    def bindings(value):
        if isinstance(value,dict):
            if 'user' in value and value['user'] not in props:raise ValueError('用户属性引用无效')
            for v in value.values():bindings(v)
        elif isinstance(value,list):
            for v in value:bindings(v)
    bindings(scene)
    if scene['general']['orthogonalprojection']!=plan['canvas']:raise ValueError('原生画布与计划不一致')
    motion=read_json(root/'motion.json')
    from .config import load_config
    expected=plan_native(motion,load_config(root/'config.yaml'))
    validate_pointer_policy(plan.get('pointer_policy'))
    audio_enabled=bool(expected['runtime_effect'] and expected['runtime_effect']['audio']['enabled'])
    if project['general'].get('supportsaudioprocessing',False) is not audio_enabled:
        raise ValueError('原生音频能力标记未绑定Motion/config: supportsaudioprocessing')
    for field in ['canvas','parallax','parallax_enabled','particles']:
        if plan[field]!=expected[field]:raise ValueError('原生计划未绑定配置/Motion: '+field)
    if plan.get('human_sways',[])!=expected['human_sways']:raise ValueError('原生人物sway未绑定Motion')
    if plan.get('runtime_effect')!=expected['runtime_effect']:raise ValueError('原生V0.6计划未绑定Motion')
    expected_protection=expected['protected_motion']
    if 'pointer_policy' not in plan:
        # Preserve the historical no-subject-guard export contract; never
        # rewrite an old scene merely because the installed validator changed.
        expected_protection=bool(motion.get('regions',{}).get('protected',{}).get('coverage',0)>0 and motion['parallax']['amplitude_px']>0 and not motion.get('sways'))
    if plan.get('protected_motion',False)!=expected_protection:raise ValueError('原生保护区未绑定深度响应')
    for field in ['enabled','region','amplitude_px']:
        if plan['sway'][field]!=expected['sway'][field]:raise ValueError('原生摇摆未绑定配置/Motion: '+field)
    if plan['sway']['enabled'] and 'sampling_policy' in plan['sway']:
        with Image.open(root/motion['regions']['other']['asset']) as original_mask,Image.open(out/'materials/s2l_sway_mask.png') as transported:
            expected_mask=sway_sampling_mask(original_mask,plan['sway']['amplitude_px'])
            if not np.array_equal(np.asarray(expected_mask),np.asarray(transported)[:,:,0]):
                raise ValueError('原生摇摆采样蒙版与区域/幅度不一致')
    if not {'parallaxenabled','parallaxstrength','particlesenabled','particleintensity'}<=set(props):raise ValueError('必需原生用户设置缺失')
    with Image.open(root/'assets/image.png') as original,Image.open(out/'materials/s2l_image.png') as native:
        if not np.array_equal(np.asarray(original.convert('RGBA')),np.asarray(native)):raise ValueError('原生 RGB 资源与规范图不同')
    if plan['parallax_enabled']:
        with Image.open(root/motion['assets']['depth']) as depth,Image.open(out/'materials/s2l_depth.png') as transported:
            values=np.round((.2+.8*np.asarray(depth,dtype=np.float32)/255)*255).astype('uint8')
            if not np.array_equal(values,np.asarray(transported)[:,:,0]):raise ValueError('原生深度传输方向或数值错误')
        if plan.get('depth_policy','').startswith('bounded-uv-v1:'):
            w,h=plan['canvas']['width'],plan['canvas']['height']
            expected_scale=np.array([plan['parallax']['amplitude_px']/w,plan['parallax']['amplitude_px']/h])
            for obj in scene['objects']:
                if 'image' not in obj:continue
                effect=next((e for e in obj.get('effects',[]) if e['file'] in ['effects/s2l_depth/effect.json','effects/s2l_human/effect.json','effects/s2l_runtime/effect.json','effects/s2l_primitives/effect.json','effects/s2l_runtime_subject/effect.json','effects/s2l_primitives_subject/effect.json']),None)
                if effect is None:raise ValueError('原生深度效果未绑定到图像层')
                constants=effect['passes'][0]['constantshadervalues']
                if not np.allclose(list(map(float,constants['scale']['value'].split())),expected_scale):
                    raise ValueError('原生视差像素幅度映射错误')
            shader='s2l_runtime' if plan.get('runtime_effect') else 's2l_human' if plan.get('human_sways') or plan.get('protected_motion') else 's2l_depth'
            # Runtime programs are checked below, including the separate
            # generated primitive variant; do not compare it to a legacy file.
            for suffix in ([] if plan.get('runtime_effect') else ['vert','frag']):
                original=Path(__file__).parent/'native'/f'{shader}.{suffix}'
                expected=human_fragment(original.read_text(encoding='utf8'),plan.get('pointer_policy')) if shader=='s2l_human' and suffix=='frag' else original.read_text(encoding='utf8')
                if (out/'shaders/effects'/f'{shader}.{suffix}').read_text(encoding='utf8')!=expected:
                    raise ValueError('原生 bounded UV Shader 与当前适配器不一致')
    if plan.get('runtime_effect'):
        validate_runtime_resources(root,out,motion,scene,props)
    if (plan.get('human_sways') or plan.get('protected_motion')) and not plan.get('runtime_effect'):
        w,h=plan['canvas']['width'],plan['canvas']['height']
        pointer_guard=plan.get('pointer_policy') in ('subject-anchored-v1',RIGID_POLICY)
        if plan.get('pointer_policy') not in (None,'subject-anchored-v1',RIGID_POLICY):
            raise ValueError('未知人物鼠标保护策略')
        if pointer_guard:
            if motion.get('regions',{}).get('person',{}).get('coverage',0)<=0:
                raise ValueError('人物鼠标保护须有非空来源化person区域')
            with Image.open(out/'materials/s2l_pointer_guard.png') as mask:
                if not np.array_equal(np.asarray(mask)[:,:,0],np.asarray(subject_pointer_guard(root,motion))):
                    raise ValueError('人物鼠标保护蒙版未绑定来源区域和幅度')
        for key,name in [('hair_sway','s2l_hair_weight'),('cloth_sway','s2l_cloth_weight'),('protected','s2l_protected')]:
            region=motion['regions'].get(key)
            with Image.open(out/'materials'/f'{name}.png') as native:
                actual=np.asarray(native)[:,:,0]
                if region:
                    with Image.open(root/region['asset']) as canonical:values=np.asarray(canonical)
                else:values=np.zeros((h,w),dtype='uint8')
                if not np.array_equal(actual,values):raise ValueError('原生人物蒙版传输不一致: '+key)
        for obj in scene['objects']:
            if 'image' not in obj:continue
            effects=obj.get('effects',[])
            if len(effects)!=1 or effects[0]['file']!='effects/s2l_human/effect.json':raise ValueError('原生人物保护效果被遗漏或叠加后置形变')
            actual=effects[0]['passes'][0]
            expected_pass=human_effect(w,h,plan['parallax']['amplitude_px'],plan['human_sways'],pointer_guard)['passes'][0]
            if actual['textures']!=expected_pass['textures'] or actual['constantshadervalues']!=expected_pass['constantshadervalues']:
                raise ValueError('原生人物sway采样或用户绑定错误')
        if plan.get('human_sways') and not {k+s for k in ('hair','cloth') for s in ('motionenabled','motionstrength')}<=set(props):raise ValueError('原生人物用户属性缺失')
        for suffix in ('vert','frag'):
            original=Path(__file__).parent/'native'/f's2l_human.{suffix}'
            expected=human_fragment(original.read_text(encoding='utf8'),plan.get('pointer_policy')) if suffix=='frag' else original.read_text(encoding='utf8')
            if (out/'shaders/effects'/f's2l_human.{suffix}').read_text(encoding='utf8')!=expected:
                raise ValueError('原生人物Shader与当前适配器不一致')
    if read_json(root/'manifest.json').get('planner') and any(e['exclude_person'] for e in plan['particles']) and 'person' in motion['regions']:
        with Image.open(root/motion['regions']['person']['asset']) as p:alpha=p.copy()
        if 'protected' in motion['regions']:
            with Image.open(root/motion['regions']['protected']['asset']) as p:alpha=ImageChops.lighter(alpha,p)
        with Image.open(out/'materials/s2l_person_cover.png') as cover:
            if not np.array_equal(np.asarray(cover.getchannel('A')),np.asarray(alpha)):
                raise ValueError('原生粒子遮挡未合并人物与保护区')
            with Image.open(root/'assets/image.png') as original:
                if not np.array_equal(np.asarray(cover.convert('RGB')),np.asarray(original)):
                    raise ValueError('原生人物覆盖层RGB与规范原图不同')
    for run in plan['compiler']['runs']:
        if run['returncode']!=0:raise ValueError('原生资源编译失败')
    for tex in out.rglob('*.tex'):
        if not tex.read_bytes().startswith(b'TEXV'):raise ValueError('编译纹理损坏')
    return '原生模型、材质、编译纹理、效果依赖及用户绑定有效；运行须独立验收'


def command_path(path):
    """Read-only 8.3 alias when available; never rename or change OS settings."""
    original=str(path)
    if original.isascii() or os.name!='nt':return original,'original'
    try:
        import ctypes
        from ctypes import wintypes
        fn=ctypes.WinDLL('kernel32',use_last_error=True).GetShortPathNameW
        fn.argtypes=[wintypes.LPCWSTR,wintypes.LPWSTR,wintypes.DWORD];fn.restype=wintypes.DWORD
        needed=fn(original,None,0)
        if needed:
            buf=ctypes.create_unicode_buffer(needed);length=fn(original,buf,needed)
            if length and length<needed and buf.value.isascii() and Path(buf.value).samefile(path):
                return buf.value,'existing-ascii-short-path'
    except OSError:pass
    return original,'unicode-host-dependent'


def stage_preview(root,cache,manifest):
    """Explicit, bounded ASCII QA copy. No overwrite, deletion, or engine install."""
    original_manifest_hash=sha256(root/'manifest.json')
    if read_json(root/'manifest.json')!=manifest:raise ValueError('QA复制前Manifest已改变')
    cache=Path(cache).resolve()
    if not str(cache).isascii():raise ValueError('--qa-cache 必须是ASCII路径，以避免引擎控制通道乱码')
    if cache.is_relative_to(root) or root.is_relative_to(cache):raise ValueError('QA缓存与原工程目录须独立')
    cache.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='s2l-'+sha256(root/'manifest.json')[:8]+'-',dir=cache))
    native=staging/'wallpaper-engine';native.mkdir()
    resources={}
    for relative,digest in manifest['resources'].items():
        if not relative.startswith('wallpaper-engine/'):continue
        source=safe_resource(root,relative);target=safe_resource(native,relative[len('wallpaper-engine/'):])
        if source.is_symlink() or sha256(source)!=digest:raise ValueError('QA复制前资源已改变')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if sha256(target)!=digest:raise ValueError('QA副本哈希不符')
        resources[relative]=digest
    if 'wallpaper-engine/project.json' not in resources:raise ValueError('QA入口未被Manifest跟踪')
    if sha256(root/'manifest.json')!=original_manifest_hash:raise ValueError('QA复制期间Manifest已改变')
    write_json(staging/'qa-source.json',{'source':str(root),'manifest_sha256':original_manifest_hash,'resources':resources,
        'note':'Explicit local QA copy; contains wallpaper image assets. No automatic cleanup or publication.'})
    return native/'project.json'


def preview_native(root,engine_path=None,qa_cache=None):
    """Launch in a named QA window only, never change user's desktop wallpaper."""
    from .validator import validate_output
    root=Path(root).resolve();report=validate_output(root,write=False)
    manifest=read_json(root/'manifest.json')
    if report['structural_status']=='failed' or manifest.get('adapter',{}).get('actual')!='native-scene':
        raise ValueError('仅允许预览结构校验有效的原生工程')
    engine=find_engine(engine_path);entry=safe_resource(root,manifest['adapter']['entry'])
    staged=stage_preview(root,qa_cache,manifest) if qa_cache else None
    if staged:entry=staged
    selected,strategy=command_path(entry)
    title='Static2Live QA '+(root.name if root.name.isascii() else 'project')+' '+sha256(root/'manifest.json')[:8]
    canvas=read_json(root/'motion.json')['canvas']
    preview_scale=min(960/canvas['width'],640/canvas['height'])
    preview_size=[max(1,round(canvas[axis]*preview_scale)) for axis in ('width','height')]
    command=[str(engine/'wallpaper64.exe'),'-control','openWallpaper','-file',selected,
        '-playInWindow',title,'-width',str(preview_size[0]),'-height',str(preview_size[1])]
    process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    code=process.poll()
    if code not in [None,0]:raise ValueError('原生预览命令失败')
    return {'command_sent':True,'launcher_pid':process.pid,'runtime_status':'not_tested','window_title':title,
        'requested_preview_size':preview_size,
        'path_strategy':strategy,'command_entry':selected,
        'qa_copy':str(staged.parent.parent) if staged else None,
        'warnings':(['引擎控制通道可能不支持此Unicode路径；加载失败时显式指定ASCII --qa-cache或用编辑器打开，不改系统编码设置'] if strategy=='unicode-host-dependent' else [])+
            (['QA副本含壁纸图像素材，已保留且不会自动清理'] if staged else []),
        'message':'命令已发送；必须检查真实预览、属性和鼠标，不能凭返回码报告通过'}


def record_native(root,note,observed):
    """Record explicit runtime observation; cannot be replaced by browser validation."""
    from .validator import validate_output,summary
    import time
    root=Path(root);previous=read_json(root/'validation.json');fresh=validate_output(root,write=False)
    if not note.strip() or fresh['structural_status']=='failed':raise ValueError('必须提供真实观察说明且结构校验有效')
    if read_json(root/'manifest.json').get('adapter',{}).get('actual')!='native-scene':raise ValueError('Web fallback 不能记录原生通过')
    plan=read_json(root/'native-plan.json');required={'load','properties','edges'}
    if plan['parallax_enabled'] and plan['parallax']['amplitude_px']>0:required.add('mouse')
    if plan['particles']:required.add('particles')
    if plan['sway']['enabled'] or plan.get('human_sways'):required.add('sway')
    if plan.get('runtime_effect'):
        if plan['runtime_effect']['audio']['enabled']:required.add('audio')
        if plan['runtime_effect']['shader']['preset']!='none':required.add('shader')
    if not required<=set(observed):raise ValueError('原生验收缺少实际观察: '+str(sorted(required-set(observed))))
    current_hash=sha256(root/'manifest.json')
    # Use current structural checks, not an editable/stale validation report.
    # Preserve only separately observed browser/visual evidence bound to this
    # exact manifest; native audio/shader does not certify the Web target.
    report=fresh
    for check in report['checks']:
        if check['name'] not in ['browser_runtime','visual_acceptance']:continue
        old=next((c for c in previous.get('checks',[]) if c.get('name')==check['name']),None)
        if old and old.get('status')=='passed':
            detail=old.get('detail',{})
            if isinstance(detail,dict) and detail.get('manifest_sha256')==current_hash:check.update(old)
    detail={'note':note,'observed':sorted(set(observed)),'target':'native-scene',
            'manifest_sha256':current_hash,'recorded_unix':time.time(),
            'method':'explicit runtime observation; not command-return-code verification'}
    for check in report['checks']:
        capability={'audio_runtime':'audio','advanced_shader_runtime':'shader'}.get(check['name'])
        if check['name']=='native_runtime' or capability in required:
            check.update(status='passed',detail=dict(detail))
    report['status']=summary(report['checks']);write_json(root/'validation.json',report);return report
