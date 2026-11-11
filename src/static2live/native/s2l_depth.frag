// Static2Live bounded depth UV adapter (MIT). No camera-wide offset.
varying vec4 v_TexCoord;
uniform sampler2D g_Texture0; // {"hidden":true}
uniform sampler2D g_Texture1; // {"label":"Depth","mode":"depth","format":"r8","default":"util/black"}
uniform vec2 g_Scale; // {"material":"scale","label":"Maximum UV displacement","default":"0.001 0.001","linked":true,"range":[0,0.01]}
uniform vec2 g_ParallaxPosition;
void main() {
    float weight = clamp(texSample2D(g_Texture1, v_TexCoord.zw).r, 0.2, 1.0);
    vec2 pointer = clamp(g_ParallaxPosition * 2.0 - 1.0, vec2(-1.0, -1.0), vec2(1.0, 1.0));
    vec2 offset = pointer * vec2(-1.0, 1.0) * g_Scale * weight;
    gl_FragColor = texSample2D(g_Texture0, clamp(v_TexCoord.xy + offset, vec2(0.0, 0.0), vec2(1.0, 1.0)));
}
