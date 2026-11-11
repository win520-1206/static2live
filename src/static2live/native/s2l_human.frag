// Static2Live Motion 0.4 formula. All amplitudes are canonical canvas pixels / width.
varying vec4 v_TexCoord;
uniform sampler2D g_Texture0; // {"hidden":true}
uniform sampler2D g_Texture1; // {"label":"Depth","default":"util/black"}
uniform sampler2D g_Texture2; // {"label":"Hair sampling weight","default":"util/black"}
uniform sampler2D g_Texture3; // {"label":"Cloth sampling weight","default":"util/black"}
uniform sampler2D g_Texture4; // {"label":"Protected region","default":"util/black"}
uniform float g_Time;
uniform vec2 g_ParallaxPosition;
uniform vec2 u_Scale; // {"material":"scale","default":"0.001 0.001","linked":true,"range":[0,0.01]}
uniform float u_HairAmplitude; // {"material":"hairAmplitude","default":0,"range":[0,0.01]}
uniform float u_HairRate; // {"material":"hairRate","default":1,"range":[0,4]}
uniform float u_HairPhase; // {"material":"hairPhase","default":0,"range":[0,6.283186]}
uniform float u_ClothAmplitude; // {"material":"clothAmplitude","default":0,"range":[0,0.01]}
uniform float u_ClothRate; // {"material":"clothRate","default":1,"range":[0,4]}
uniform float u_ClothPhase; // {"material":"clothPhase","default":0,"range":[0,6.283186]}
void main() {
    vec2 uv = v_TexCoord.zw;
    float protectedWeight = texSample2D(g_Texture4, uv).r;
    float depthWeight = clamp(texSample2D(g_Texture1, uv).r, 0.2, 1.0) * (1.0 - protectedWeight);
    vec2 pointer = clamp(g_ParallaxPosition * 2.0 - 1.0, vec2(-1.0, -1.0), vec2(1.0, 1.0));
    vec2 offset = pointer * vec2(-1.0, 1.0) * u_Scale * depthWeight;
    float localPhase = 0.6 * uv.x + 0.35 * uv.y;
    float hair = u_HairAmplitude * texSample2D(g_Texture2, uv).r * sin(g_Time * u_HairRate + u_HairPhase + localPhase);
    float cloth = u_ClothAmplitude * texSample2D(g_Texture3, uv).r * sin(g_Time * u_ClothRate + u_ClothPhase + localPhase);
    offset.x -= hair + cloth;
    gl_FragColor = texSample2D(g_Texture0, clamp(v_TexCoord.xy + offset, vec2(0.0, 0.0), vec2(1.0, 1.0)));
}
