"""Motion 0.6 native shader adapter, not an independent image analyzer."""
from pathlib import Path
import shutil
import numpy as np
from PIL import Image
from .storage import read_json, write_json, sha256
from .primitives import GEOMETRIC, SHADER_MODES, native_fragment
from .pointer import has_subject, subject_pointer_guard, RIGID_POLICY, validate_pointer_policy


def active(runtime):
    return bool(runtime and (runtime['audio']['enabled'] or runtime['shader']['preset']!='none'))


def program_name(runtime,subject=False):
    validate_pointer_policy(subject,legacy_bool=True)
    return ('s2l_primitives' if runtime['shader']['preset'] in GEOMETRIC else 's2l_runtime')+('_subject' if subject else '')


def fragment_source(base,runtime,subject=False):
    validate_pointer_policy(subject,legacy_bool=True)
    result=native_fragment(base) if runtime['shader']['preset'] in GEOMETRIC else base
    if subject and result.count('vec2 offset = pointer*')!=1:
        raise ValueError('组合Shader鼠标公式 / formula 不符合版本化适配契约')
    if subject == RIGID_POLICY:
        result=result.replace('vec2 offset = pointer*',
            'depthWeight=mix(clamp(texSample2D(g_Texture1,uv).r,0.2,1.0),0.85,texSample2D(g_Texture1,uv).g);\n    vec2 offset = pointer*')
    elif subject:
        result=result.replace('vec2 offset = pointer*',
            'depthWeight*=1.0-texSample2D(g_Texture1,uv).g;\n    vec2 offset = pointer*')
    return result


def strength_script(key,toggle,base):
    return ("'use strict'; let factor=1; let enabled=true; export function applyUserProperties(p){"
        f"if(p.hasOwnProperty('{key}'))factor=Math.max(0,Math.min(1,p.{key}/100));"
        f"if(p.hasOwnProperty('{toggle}'))enabled=p.{toggle};}}"
        f" export function update(value){{return enabled?{base:.12g}*factor:0;}}")


def audio_script(options):
    # Official SceneScript API; 64 bands aligns with the Web host's 64/channel.
    return ("'use strict'; const spectrum=engine.registerAudioBuffers(engine.AUDIO_RESOLUTION_64);"
        "let level=0; let factor=1; let enabled=true; export function applyUserProperties(p){"
        "if(p.hasOwnProperty('audioenabled'))enabled=p.audioenabled;"
        "if(p.hasOwnProperty('audiostrength'))factor=Math.max(0,Math.min(1,p.audiostrength/100));}"
        "export function update(value){if(!enabled){level=0;return 0;}let sum=0;"
        "for(let i=0;i<8;i++){let x=spectrum.average[i];sum+=Number.isFinite(x)?Math.max(0,Math.min(1,x)):0;}"
        f"let dt=Math.max(0,Math.min(.1,engine.frametime));level+=(sum/8-level)*(1-Math.exp(-dt/{options['response_seconds']:.12g}));"
        f"return Math.max(0,Math.min(1,level))*{options['strength']:.12g}*factor;}}")


def runtime_effect(width,height,amplitude,sways,runtime,subject=False):
    from .wallpaper_engine import human_effect
    effect=human_effect(width,height,amplitude,sways)
    effect.update(file=f'effects/{program_name(runtime,subject)}/effect.json',name='Static2Live protected runtime')
    p=effect['passes'][0];shader=runtime['shader'];audio=runtime['audio']
    p['textures']+=['s2l_shader_region','s2l_audio_region']
    p['constantshadervalues'].update({
        'shaderMode':SHADER_MODES.index(shader['preset']),
        'shaderStrength':{'value':shader['strength'],'script':strength_script('shaderstrength','shaderenabled',shader['strength'])},
        'shaderAmplitude':shader['amplitude_px']/width,
        'shaderRate':2*np.pi/shader['period_seconds'],
        'audioLevel':{'value':0,'script':audio_script(audio)} if audio['enabled'] else 0,
    })
    if shader['preset'] in GEOMETRIC:p['constantshadervalues']['canvasAspect']=width/height
    return effect


def export_resources(root,out,motion,texture):
    runtime=motion['runtime'];size=tuple(motion['canvas'].values())
    def mask(name,key,full=False):
        if key in motion['regions']:
            with Image.open(root/motion['regions'][key]['asset']) as image:texture(name,image.convert('RGBA'))
        else:texture(name,Image.new('RGBA',size,(255,255,255,255) if full else (0,0,0,255)))
    for key,name in [('hair_sway','s2l_hair_weight'),('cloth_sway','s2l_cloth_weight'),('protected','s2l_protected')]:mask(name,key)
    mask('s2l_shader_region',runtime['shader']['region'])
    mask('s2l_audio_region',runtime['audio']['region'],runtime['audio']['region']=='full')
    name=program_name(runtime,has_subject(motion))
    (out/f'effects/{name}').mkdir(parents=True,exist_ok=True)
    for suffix in ('vert','frag'):
        original=Path(__file__).parent/'native'/f's2l_runtime.{suffix}'
        target=out/'shaders/effects'/f'{name}.{suffix}'
        if suffix=='frag':target.write_text(fragment_source(original.read_text(encoding='utf8'),runtime,RIGID_POLICY if has_subject(motion) else False),encoding='utf8')
        else:shutil.copy2(original,target)
    write_json(out/f'materials/effects/{name}.json',{'passes':[{'shader':f'effects/{name}','blending':'normal',
        'depthtest':'disabled','depthwrite':'disabled','cullmode':'nocull'}]})
    write_json(out/f'effects/{name}/effect.json',{'version':1,'name':'Static2Live protected runtime','group':'distort',
        'passes':[{'material':f'materials/effects/{name}.json'}],
        'dependencies':[f'materials/effects/{name}.json',f'shaders/effects/{name}.vert',f'shaders/effects/{name}.frag']})


def properties(runtime):
    result={}
    for prefix,title,enabled in [('audio','音频响应',runtime['audio']['enabled']),('shader','局部Shader',runtime['shader']['preset']!='none')]:
        result[prefix+'enabled']={'type':'bool','text':title,'value':enabled,'order':20 if prefix=='audio' else 22}
        result[prefix+'strength']={'type':'slider','text':title+'强度（%）','value':100,'min':0,'max':100,'order':21 if prefix=='audio' else 23}
    return result


def validate_resources(root,out,motion,scene,props):
    runtime=motion['runtime'];w,h=motion['canvas'].values()
    # Old exports without this policy retain their legacy resource contract.
    policy=read_json(root/'native-plan.json').get('pointer_policy')
    validate_pointer_policy(policy)
    subject=policy or False
    program=program_name(runtime,subject)
    expected=runtime_effect(w,h,motion['parallax']['amplitude_px'],motion['sways'],runtime,subject)['passes'][0]
    if subject:
        if not has_subject(motion):raise ValueError('人物鼠标保护缺少person来源')
        with Image.open(out/'materials/s2l_depth.png') as texture:
            if not np.array_equal(np.asarray(texture.getchannel('G')),np.asarray(subject_pointer_guard(root,motion))):
                raise ValueError('原生runtime人物鼠标保护传输错误')
    for obj in scene['objects']:
        if 'image' not in obj:continue
        effects=obj.get('effects',[])
        if len(effects)!=1 or effects[0]['file']!=f'effects/{program}/effect.json':raise ValueError('原生V0.6必须使用单一保护采样流程')
        p=effects[0]['passes'][0]
        if p['textures']!=expected['textures'] or p['constantshadervalues']!=expected['constantshadervalues']:
            raise ValueError('原生V0.6参数、脚本或纹理绑定错误')
    pairs=[('hair_sway','s2l_hair_weight'),('cloth_sway','s2l_cloth_weight'),('protected','s2l_protected'),
           (runtime['shader']['region'],'s2l_shader_region'),(runtime['audio']['region'],'s2l_audio_region')]
    for key,name in pairs:
        region=motion['regions'].get(key)
        if region:
            with Image.open(root/region['asset']) as image:values=np.asarray(image)
        else:values=np.full((h,w),255 if key=='full' else 0,dtype='uint8')
        with Image.open(out/'materials'/f'{name}.png') as image:
            if not np.array_equal(np.asarray(image)[:,:,0],values):raise ValueError('原生V0.6蒙版传输不一致: '+name)
    for suffix in ('vert','frag'):
        original=Path(__file__).parent/'native'/f's2l_runtime.{suffix}'
        target=out/'shaders/effects'/f'{program}.{suffix}'
        matches=(target.read_text(encoding='utf8')==fragment_source(original.read_text(encoding='utf8'),runtime,subject)) if suffix=='frag' else sha256(target)==sha256(original)
        if not matches:
            raise ValueError('原生V0.6 Shader与适配器不一致')
    for key,value in properties(runtime).items():
        if props.get(key)!=value:raise ValueError('V0.6用户属性缺失或默认边界错误')
    if motion['sways'] and not {k+s for k in ('hair','cloth') for s in ('motionenabled','motionstrength')}<=set(props):
        raise ValueError('原生人物用户属性缺失')
