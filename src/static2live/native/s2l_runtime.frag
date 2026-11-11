// Motion 0.6 adapter. Same bounded primitives, original source RGB/alpha.
varying vec4 v_TexCoord;
uniform sampler2D g_Texture0; // {"hidden":true}
uniform sampler2D g_Texture1; // {"label":"Depth","default":"util/black"}
uniform sampler2D g_Texture2; // {"label":"Hair weight","default":"util/black"}
uniform sampler2D g_Texture3; // {"label":"Cloth weight","default":"util/black"}
uniform sampler2D g_Texture4; // {"label":"Protected","default":"util/black"}
uniform sampler2D g_Texture5; // {"label":"Shader region","default":"util/black"}
uniform sampler2D g_Texture6; // {"label":"Audio region","default":"util/black"}
uniform float g_Time;
uniform vec2 g_ParallaxPosition;
uniform vec2 u_Scale; // {"material":"scale","default":"0 0","linked":true,"range":[0,0.01]}
uniform float u_HairAmplitude; // {"material":"hairAmplitude","default":0,"range":[0,0.01]}
uniform float u_HairRate; // {"material":"hairRate","default":1,"range":[0,4]}
uniform float u_HairPhase; // {"material":"hairPhase","default":0,"range":[0,6.283186]}
uniform float u_ClothAmplitude; // {"material":"clothAmplitude","default":0,"range":[0,0.01]}
uniform float u_ClothRate; // {"material":"clothRate","default":1,"range":[0,4]}
uniform float u_ClothPhase; // {"material":"clothPhase","default":0,"range":[0,6.283186]}
uniform float u_ShaderMode; // {"material":"shaderMode","default":0,"range":[0,3]}
uniform float u_ShaderStrength; // {"material":"shaderStrength","default":0,"range":[0,1]}
uniform float u_ShaderAmplitude; // {"material":"shaderAmplitude","default":0,"range":[0,0.01]}
uniform float u_ShaderRate; // {"material":"shaderRate","default":1,"range":[0,4]}
uniform float u_AudioLevel; // {"material":"audioLevel","default":0,"range":[0,0.2]}
void main() {
    vec2 uv = v_TexCoord.zw;
    float protectedWeight = texSample2D(g_Texture4, uv).r;
    float safeWeight = 1.0-step(0.001,protectedWeight);
    float depthWeight = clamp(texSample2D(g_Texture1, uv).r,0.2,1.0)*(1.0-protectedWeight);
    vec2 pointer = clamp(g_ParallaxPosition*2.0-1.0,vec2(-1.0,-1.0),vec2(1.0,1.0));
    vec2 offset = pointer*vec2(-1.0,1.0)*u_Scale*depthWeight;
    float localPhase = 0.6*uv.x+0.35*uv.y;
    float hair = u_HairAmplitude*texSample2D(g_Texture2,uv).r*sin(g_Time*u_HairRate+u_HairPhase+localPhase);
    float cloth = u_ClothAmplitude*texSample2D(g_Texture3,uv).r*sin(g_Time*u_ClothRate+u_ClothPhase+localPhase);
    offset.x-=hair+cloth;
    float region = texSample2D(g_Texture5,uv).r*safeWeight;
    float phase = g_Time*u_ShaderRate;
    if(u_ShaderMode>1.5 && u_ShaderMode<2.5)offset.x+=sin((1.0-uv.y)*80.0+phase)*u_ShaderAmplitude*u_ShaderStrength*region;
    vec2 sampleUV=clamp(v_TexCoord.xy+offset,vec2(0.0,0.0),vec2(1.0,1.0));
    vec4 color=texSample2D(g_Texture0,sampleUV);
    if(u_ShaderMode>0.5 && u_ShaderMode<1.5)color.rgb+=vec3(0.12,0.065,0.018)*u_ShaderStrength*region*(0.65+0.35*sin(phase));
    if(u_ShaderMode>2.5){
        float shift=u_ShaderAmplitude*u_ShaderStrength*region;
        color.r=texSample2D(g_Texture0,clamp(sampleUV+vec2(shift,0.0),vec2(0.0,0.0),vec2(1.0,1.0))).r;
        color.b=texSample2D(g_Texture0,clamp(sampleUV-vec2(shift,0.0),vec2(0.0,0.0),vec2(1.0,1.0))).b;
        color.rgb+=vec3(0.08,0.015,0.09)*u_ShaderStrength*region*(0.5+0.5*sin(phase));
    }
    float audioMask=texSample2D(g_Texture6,uv).r*safeWeight;
    color.rgb+=vec3(1.0,0.65,0.25)*u_AudioLevel*audioMask;
    gl_FragColor=vec4(clamp(color.rgb,vec3(0.0,0.0,0.0),vec3(1.0,1.0,1.0)),color.a);
}
