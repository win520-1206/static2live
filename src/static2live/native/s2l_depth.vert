// Static2Live bounded depth UV adapter (MIT).
uniform mat4 g_ModelViewProjectionMatrix;
uniform vec4 g_Texture1Resolution;
attribute vec3 a_Position;
attribute vec2 a_TexCoord;
varying vec4 v_TexCoord;
void main() {
    gl_Position = mul(vec4(a_Position, 1.0), g_ModelViewProjectionMatrix);
    v_TexCoord.xy = a_TexCoord;
    v_TexCoord.zw = a_TexCoord * g_Texture1Resolution.zw / g_Texture1Resolution.xy;
}
