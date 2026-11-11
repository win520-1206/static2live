"""Shared bounded UV primitives, consumed by both render adapters.

Coordinates are normalized, bottom-left. Each returned component is in [-1,1];
the adapter applies canvas-pixel amplitude, strength, region and protection.
Rotate is a small-angle rotational field, not a skeletal/rigid layer rotation.
"""
GEOMETRIC = ('float','pan','zoom','rotate','wave','distortion')
SHADER_MODES = ('none','warm_glow','water_ripple','neon_pulse',*GEOMETRIC)
DISPLACING = ('water_ripple','neon_pulse',*GEOMETRIC)

GLSL = '''
vec2 s2lPrimitive(float mode, vec2 p, float phase) {
    vec2 r=clamp(p,vec2(0.0,0.0),vec2(1.0,1.0))-vec2(0.5,0.5);
    if(mode<4.5)return vec2(0.65*sin(phase),0.35*cos(phase));
    if(mode<5.5)return vec2(sin(phase),0.0);
    if(mode<6.5)return r*(2.0*sin(phase));
    if(mode<7.5)return vec2(-r.y,r.x)*(2.0*sin(phase));
    if(mode<8.5)return vec2(sin(p.y*18.84955592+phase),0.0);
    return vec2(0.65*sin(p.y*18.84955592+phase),0.35*cos(p.x*12.56637061-phase));
}
'''


def native_fragment(base):
    """New resource only: leave legacy s2l_runtime GLSL byte-for-byte intact."""
    result=base.replace('"range":[0,3]', '"range":[0,9]')
    result=result.replace('void main() {','uniform float u_CanvasAspect; // {"material":"canvasAspect","default":1}\n'+GLSL+'\nvoid main() {')
    result=result.replace('    vec2 sampleUV=', '''    if(u_ShaderMode>3.5) {
        vec2 unit=s2lPrimitive(u_ShaderMode,vec2(uv.x,1.0-uv.y),phase);
        offset+=vec2(unit.x,-unit.y*u_CanvasAspect)*u_ShaderAmplitude*u_ShaderStrength*region;
    }
    vec2 sampleUV=''')
    return result.replace('if(u_ShaderMode>2.5){','if(u_ShaderMode>2.5 && u_ShaderMode<3.5){')
