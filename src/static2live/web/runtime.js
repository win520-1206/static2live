/* Static2Live 0.2; compatible with 0.1 Motion. No network. */
(() => {
  'use strict';
  const boot = JSON.parse(document.getElementById('static2live-data').textContent);
  const m = boot.motion, canvas = document.querySelector('canvas'), fallback = document.querySelector('#fallback');
  const notice = document.querySelector('#notice');
  fallback.src = boot.image;
  const state = window.static2live = {status:'loading', shaderCompiled:false, frames:0,
    pointer:[0,0], target:[0,0], reducedMotion:false, errors:[], motion:m, networkRequests:0,time:0};
  const cloud=(m.effects||[]).find(e=>e.type==='cloud_drift' && e.enabled);
  const sways=m.sways||[];
  const options=m.runtime;
  const budget=options?.performance||{fps:60,pixel_ratio:2,max_pixels:16777216,particle_fraction:1};
  const display=options?.display.viewport||[0,0,1,1];
  const advanced=options?.shader;
  const audio=new window.Static2LiveAudio(options?.audio||{enabled:false,response_seconds:.15,strength:0},state);
  state.runtimeOptions=options||null;state.shaderEnabled=true;
  state.setShaderEnabled=enabled=>{state.shaderEnabled=!!enabled;};
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const fail = (reason) => {
    state.status='fallback'; state.errors.push(String(reason)); canvas.hidden=true;
    const overlay=document.querySelector('#effects');if(overlay)overlay.hidden=true;
    fallback.hidden=false; notice.hidden=false; notice.textContent='静态模式：'+reason;
  };
  let gl;
  try { gl = canvas.getContext('webgl',{alpha:false,preserveDrawingBuffer:true,antialias:false}); }
  catch (e) { fail(e); return; }
  if (!gl) { fail('WebGL 不可用，交互尚未通过验证'); return; }
  const vs = 'attribute vec2 a; varying vec2 uv; void main(){ uv=(a+1.0)*0.5; gl_Position=vec4(a,0.0,1.0); }';
  const fs = `precision highp float;
    varying vec2 uv; uniform sampler2D imageTex; uniform sampler2D depthTex; uniform sampler2D cloudTex;
    uniform sampler2D hairTex; uniform sampler2D clothTex; uniform sampler2D protectedTex;
    uniform vec3 hairParams; uniform vec3 clothParams; uniform float swayTime;
    uniform vec2 mouse; uniform vec2 imageSize; uniform vec2 viewport;
    uniform float amplitude; uniform float overscan; uniform float cloudAmplitude; uniform float cloudPhase;
    uniform vec4 displayRect; uniform vec4 advancedParams; uniform sampler2D advancedTex; uniform sampler2D audioTex;
    uniform float advancedTime; uniform float audioLevel; uniform float subjectGuardEnabled;
    /*S2L_PRIMITIVE_GLSL*/
    void main(){
      float ia=imageSize.x/imageSize.y, va=(viewport.x/viewport.y)*displayRect.w/displayRect.z;
      vec2 cover=vec2(min(1.0,va/ia),min(1.0,ia/va));
      vec2 virtualUV=vec2(displayRect.x,1.0-displayRect.y-displayRect.w)+uv*displayRect.zw;
      vec2 base=(virtualUV-0.5)*cover+0.5;
      vec2 margin=vec2(overscan)/imageSize;
      base=margin+base*(vec2(1.0)-2.0*margin);
      float d=texture2D(depthTex,base).r;
      float weight=0.2+0.8*d;
      weight*=1.0-texture2D(protectedTex,base).r;
      if(subjectGuardEnabled>1.5)weight=mix(0.2+0.8*d,0.85,texture2D(depthTex,base).g);
      else weight*=1.0-subjectGuardEnabled*texture2D(depthTex,base).g;
      vec2 shifted=base-mouse*amplitude*weight/imageSize;
      shifted.x-=sin(cloudPhase)*cloudAmplitude*texture2D(cloudTex,base).r/imageSize.x;
      float localPhase=.6*base.x+.35*(1.0-base.y);
      float h=hairParams.x*texture2D(hairTex,base).r*sin(swayTime*hairParams.y+hairParams.z+localPhase);
      float c=clothParams.x*texture2D(clothTex,base).r*sin(swayTime*clothParams.y+clothParams.z+localPhase);
      shifted.x-=(h+c)/imageSize.x;
      float safeRegion=texture2D(advancedTex,base).r*(1.0-step(0.001,texture2D(protectedTex,base).r));
      float phase=advancedTime*6.283185/advancedParams.w;
      if(advancedParams.x>1.5 && advancedParams.x<2.5){
        shifted.x+=sin(base.y*80.0+phase)*advancedParams.z*advancedParams.y*safeRegion/imageSize.x;
      }
      if(advancedParams.x>3.5){
        shifted+=s2lPrimitive(advancedParams.x,base,phase)*advancedParams.z*advancedParams.y*safeRegion/imageSize;
      }
      shifted=clamp(shifted,vec2(0.5)/imageSize,vec2(1.0)-vec2(0.5)/imageSize);
      vec3 color=texture2D(imageTex,shifted).rgb;
      if(advancedParams.x>.5 && advancedParams.x<1.5){color+=vec3(.12,.065,.018)*advancedParams.y*safeRegion*(.65+.35*sin(phase));}
      if(advancedParams.x>2.5 && advancedParams.x<3.5){
        float offset=advancedParams.z*advancedParams.y*safeRegion/imageSize.x;
        vec2 lo=vec2(.5)/imageSize,hi=vec2(1.0)-lo;
        color.r=texture2D(imageTex,clamp(shifted+vec2(offset,0.0),lo,hi)).r;
        color.b=texture2D(imageTex,clamp(shifted-vec2(offset,0.0),lo,hi)).b;
        color+=vec3(.08,.015,.09)*advancedParams.y*safeRegion*(.5+.5*sin(phase));
      }
      float audioMask=texture2D(audioTex,base).r*(1.0-step(.001,texture2D(protectedTex,base).r));
      color+=vec3(1.0,.65,.25)*audioLevel*audioMask;
      gl_FragColor=vec4(clamp(color,0.0,1.0),1.0);
    }`;
  function shader(type,source){
    const s=gl.createShader(type); gl.shaderSource(s,source); gl.compileShader(s);
    if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(s)); return s;
  }
  let program;
  try {
    program=gl.createProgram(); gl.attachShader(program,shader(gl.VERTEX_SHADER,vs));
    gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fs)); gl.linkProgram(program);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
    gl.useProgram(program); state.shaderCompiled=true;
  } catch(e) { fail(e); return; }
  const buffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
  const attr=gl.getAttribLocation(program,'a'); gl.enableVertexAttribArray(attr); gl.vertexAttribPointer(attr,2,gl.FLOAT,false,0,0);
  const uniforms={}; ['mouse','imageSize','viewport','amplitude','overscan','cloudAmplitude','cloudPhase','hairParams','clothParams','swayTime','displayRect','advancedParams','advancedTime','audioLevel'].forEach(k=>uniforms[k]=gl.getUniformLocation(program,k));
  gl.uniform4f(uniforms.displayRect,...display);
  gl.uniform2f(uniforms.imageSize,m.canvas.width,m.canvas.height);
  gl.uniform1f(uniforms.amplitude,m.parallax.amplitude_px);
  gl.uniform1f(uniforms.overscan,m.parallax.overscan_px);
  gl.uniform1f(gl.getUniformLocation(program,'subjectGuardEnabled'),boot.pointer_policy==='subject-rigid-v2'?2:boot.pointer_policy==='subject-anchored-v1'?1:0);
  gl.uniform1f(uniforms.cloudAmplitude,cloud?cloud.amplitude_px*cloud.intensity:0);
  function texture(url,unit,name){return new Promise((resolve,reject)=>{
    const image=new Image(); image.onerror=()=>reject(Error('嵌入纹理加载失败'));
    image.onload=()=>{
      gl.activeTexture(gl.TEXTURE0+unit); const t=gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D,t);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);
      gl.uniform1i(gl.getUniformLocation(program,name),unit); resolve();
    }; image.src=url;
  });}
  state.setPointer=(x,y)=>{state.target=[Math.max(-1,Math.min(1,x)),Math.max(-1,Math.min(1,y))];};
  addEventListener('pointermove',e=>state.setPointer((display[0]+e.clientX/innerWidth*display[2])*2-1,1-(display[1]+e.clientY/innerHeight*display[3])*2));
  document.documentElement.addEventListener('pointerleave',()=>state.setPointer(0,0));
  canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();fail('WebGL 上下文丢失');});
  function resize(){
    const ratio=Math.min(devicePixelRatio||1,budget.pixel_ratio,Math.sqrt(budget.max_pixels/(innerWidth*innerHeight)));
    canvas.width=Math.max(1,Math.floor(innerWidth*ratio)); canvas.height=Math.max(1,Math.floor(innerHeight*ratio));
    gl.viewport(0,0,canvas.width,canvas.height); gl.uniform2f(uniforms.viewport,canvas.width,canvas.height);
  }
  addEventListener('resize',resize);
  const effects=window.Static2LiveEffects?new window.Static2LiveEffects(boot,state,canvas):null;
  state.readPixels=()=>{
    if(effects && effects.active){const combined=effects.pixels();const out=new Uint8Array(combined.length),stride=canvas.width*4;
      for(let y=0;y<canvas.height;y++)out.set(combined.subarray(y*stride,(y+1)*stride),(canvas.height-1-y)*stride);return Array.from(out);}
    const data=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,data);return Array.from(data);
  };
  state.setTime=t=>{state.fixedTime=t===null?null:Math.max(0,t);};
  state.setEffectsEnabled=enabled=>{state.effectsEnabled=!!enabled;};
  state.setParallaxEnabled=enabled=>{state.pointerEnabled=!!enabled;if(!enabled)state.pointer=[0,0];};
  state.effectsEnabled=true;state.pointerEnabled=true;
  state.swayEnabled=true;state.swayStrength=1;
  state.setSwayEnabled=enabled=>{state.swayEnabled=!!enabled;};
  state.setSwayStrength=strength=>{state.swayStrength=Math.max(0,Math.min(1,Number(strength)||0));};
  Promise.all([texture(boot.image,0,'imageTex'),texture(boot.pointer_depth||boot.depth,1,'depthTex'),
    texture(boot.cloud_texture||(boot.regions||{}).cloud||boot.black||boot.depth,2,'cloudTex'),
    texture((boot.regions||{}).hair_sway||boot.black||boot.depth,3,'hairTex'),
    texture((boot.regions||{}).cloth_sway||boot.black||boot.depth,4,'clothTex'),
    texture((boot.regions||{}).protected||boot.black||boot.depth,5,'protectedTex'),
    texture((boot.regions||{})[advanced?.region]||boot.black,6,'advancedTex'),
    texture(options?.audio.region==='full'?boot.white:(boot.regions||{})[options?.audio.region]||boot.black,7,'audioTex'),
    effects?effects.ready:Promise.resolve()]).then(()=>{
    resize(); state.status='ready'; const start=performance.now();let last=start,lastDraw=-Infinity;
    function render(now){
      if(document.hidden || now-lastDraw<1000/budget.fps-.5){if(state.status==='ready')requestAnimationFrame(render);return;}
      lastDraw=now;
      state.reducedMotion=media.matches;
      const dt=Math.min((now-last)/1000,0.1);last=now;
      const rate=1-Math.exp(-dt/m.parallax.response_seconds);
      const target=media.matches || !state.pointerEnabled?[0,0]:state.target;
      state.pointer=state.pointer.map((v,i)=>media.matches?0:v+(target[i]-v)*rate);
      state.time=media.matches?0:(state.fixedTime??(now-start)/1000);
      gl.uniform1f(uniforms.cloudPhase,cloud?state.time*2*Math.PI/cloud.period_seconds:0);
      gl.uniform1f(uniforms.cloudAmplitude,cloud && state.effectsEnabled && !media.matches?cloud.amplitude_px*cloud.intensity:0);
      gl.uniform1f(uniforms.swayTime,state.time);
      const advancedEnabled=advanced && state.shaderEnabled && !media.matches;
      gl.uniform4f(uniforms.advancedParams,advancedEnabled?(/*S2L_SHADER_MODES*/).indexOf(advanced.preset):0,
        advancedEnabled?advanced.strength:0,advanced?.amplitude_px||0,advanced?.period_seconds||8);
      gl.uniform1f(uniforms.advancedTime,state.time);
      gl.uniform1f(uniforms.audioLevel,audio.update(dt,media.matches));
      for(const kind of ['hair','cloth']){
        const s=sways.find(item=>item.kind===kind);
        const strength=state.swayEnabled && !media.matches?state.swayStrength:0;
        gl.uniform3f(uniforms[kind+'Params'],s?s.amplitude_px*strength:0,s?2*Math.PI/s.period_seconds:0,s?s.phase:0);
      }
      gl.uniform2f(uniforms.mouse,...state.pointer); gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
      if(effects)effects.render();state.frames++;
      if(state.status==='ready') requestAnimationFrame(render);
    } requestAnimationFrame(render);
  }).catch(fail);
})();
