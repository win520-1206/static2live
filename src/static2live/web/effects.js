/* Canvas overlays consume Manifest only, never perform image analysis. */
window.Static2LiveEffects=class {
  constructor(boot,state,base){
    this.boot=boot;this.state=state;this.base=base;this.canvas=document.querySelector('#effects');
    this.ctx=this.canvas.getContext('2d');this.layer=document.createElement('canvas');this.lc=this.layer.getContext('2d');
    this.combined=document.createElement('canvas');this.cc=this.combined.getContext('2d',{willReadFrequently:true});
    this.effects=(boot.motion.effects||[]).filter(e=>e.enabled && e.intensity>0 && e.type!=='cloud_drift');
    this.active=this.effects.length>0;this.images={};this.masks={};this.clipCache={};
    let seed=boot.motion.seed??1;
    const random=()=>{seed=(Math.imul(1664525,seed)+1013904223)>>>0;return seed/4294967296;};
    const fraction=boot.motion.runtime?.performance.particle_fraction??1;
    this.particles=this.effects.map(e=>Array.from({length:Math.ceil(e.count*fraction)},()=>({x:random(),y:random(),phase:random()*Math.PI*2,s:.5+random(),v:.6+random()*.8})));
    this.state.effectParticleCounts=this.effects.map((e,i)=>({type:e.type,count:this.particles[i].length}));
    this.ready=Promise.all(Object.entries(boot.regions||{}).map(([key,url])=>new Promise((resolve,reject)=>{
      const image=new Image();image.onerror=()=>reject(Error('区域纹理加载失败'));
      image.onload=()=>{this.images[key]=image;const mask=document.createElement('canvas');mask.width=image.width;mask.height=image.height;
        const c=mask.getContext('2d',{willReadFrequently:true});c.drawImage(image,0,0);const data=c.getImageData(0,0,mask.width,mask.height);
        for(let i=0;i<data.data.length;i+=4){data.data[i+3]=data.data[i];data.data[i]=255;data.data[i+1]=255;data.data[i+2]=255;}
        c.putImageData(data,0,0);this.masks[key]=mask;resolve();};image.src=url;
    })));
  }
  layout(){
    const m=this.boot.motion,w=this.base.width,h=this.base.height,iw=m.canvas.width,ih=m.canvas.height;
    const rect=m.runtime?.display.viewport||[0,0,1,1];
    const ia=iw/ih,va=w/h*rect[3]/rect[2],cx=Math.min(1,va/ia),cy=Math.min(1,ia/va),ox=m.parallax.overscan_px/iw,oy=m.parallax.overscan_px/ih;
    const ux=cx*(1-2*ox)*rect[2],uy=cy*(1-2*oy)*rect[3];
    // Canvas Y points down, Manifest mouse Y points up. Same base UV as shader.
    return {w,h,iw,ih,ux,uy,left:ox+((1-cx)/2+rect[0]*cx)*(1-2*ox),top:oy+((1-cy)/2+rect[1]*cy)*(1-2*oy)};
  }
  drawMask(ctx,key,operation){
    const mask=this.masks[key];if(!mask)return;
    const cacheKey=key+operation;
    if(this.clipCache[cacheKey]){ctx.globalAlpha=1;ctx.globalCompositeOperation=operation;ctx.drawImage(this.clipCache[cacheKey],0,0);ctx.globalCompositeOperation='source-over';return;}
    const l=this.layout(),scaleX=l.w/(l.ux*l.iw),scaleY=l.h/(l.uy*l.ih);
    const cached=document.createElement('canvas');cached.width=l.w;cached.height=l.h;const cc=cached.getContext('2d');
    const pad=operation==='destination-out'?this.boot.motion.parallax.amplitude_px*Math.max(scaleX,scaleY)+2:0;
    const offsets=pad?[-pad,0,pad]:[0];
    for(const dx of offsets)for(const dy of offsets)cc.drawImage(mask,-l.left*l.iw*scaleX+dx,-l.top*l.ih*scaleY+dy,l.iw*scaleX,l.ih*scaleY);
    this.clipCache[cacheKey]=cached;ctx.globalAlpha=1;ctx.globalCompositeOperation=operation;ctx.drawImage(cached,0,0);
    ctx.globalCompositeOperation='source-over';
  }
  render(){
    const w=this.base.width,h=this.base.height;
    if(this.canvas.width!==w || this.canvas.height!==h){for(const c of [this.canvas,this.layer,this.combined]){c.width=w;c.height=h;}this.clipCache={};}
    this.ctx.clearRect(0,0,w,h);
    if(!this.active || this.state.reducedMotion || !this.state.effectsEnabled)return;
    const rect=this.boot.motion.runtime?.display.viewport||[0,0,1,1];
    const vw=w/rect[2],vh=h/rect[3],offsetX=rect[0]*vw,offsetY=rect[1]*vh;
    const time=this.state.time,l=this.layout(),scale=Math.max(vw/l.iw,vh/l.ih),c=this.lc;
    this.effects.forEach((e,j)=>{
      c.clearRect(0,0,w,h);c.globalAlpha=1;c.globalCompositeOperation='source-over';c.fillStyle=e.color;c.strokeStyle=e.color;
      if(e.type==='glow'){
        c.globalAlpha=e.intensity*(.45+.25*Math.sin(time*2*Math.PI/e.period_seconds));c.fillRect(0,0,w,h);
      }else{
        this.particles[j].forEach(p=>{
          let x=p.x*vw,y=p.y*vh,s=e.size_px*scale*p.s,speed=e.speed_px_s*scale*p.v;
          if(e.type==='rain' || e.type==='snow'){
            y=((p.y*(vh+2*s)+time*speed)%(vh+2*s))-s;
            x+=(e.type==='rain'?-time*speed*.13:Math.sin(time*.6+p.phase)*s*4);
          }else{x=(x+time*speed*.45)%(vw+2*s)-s;y+=Math.sin(time*.35+p.phase)*s*3;}
          x=((x+s)%(vw+2*s)+vw+2*s)%(vw+2*s)-s-offsetX;y-=offsetY;
          c.globalAlpha=e.intensity*(e.type==='fog'?.16:.7);
          if(e.type==='rain'){c.lineWidth=Math.max(.6,scale*.5);c.beginPath();c.moveTo(x,y);c.lineTo(x-s*.15,y+s);c.stroke();}
          else if(e.type==='fog'){
            const r=Math.max(vw,vh)*(.12+.1*p.s);const gradient=c.createRadialGradient(x,y,0,x,y,r);
            gradient.addColorStop(0,e.color);gradient.addColorStop(1,e.color+'00');c.fillStyle=gradient;c.fillRect(x-r,y-r,2*r,2*r);
          }else{c.beginPath();c.arc(x,y,s,0,2*Math.PI);c.fill();}
        });
      }
      if(e.region!=='full')this.drawMask(c,e.region,'destination-in');
      if(e.exclude_person){this.drawMask(c,'person','destination-out');this.drawMask(c,'protected','destination-out');}
      this.ctx.drawImage(this.layer,0,0);
    });
  }
  pixels(){this.cc.clearRect(0,0,this.combined.width,this.combined.height);this.cc.drawImage(this.base,0,0);this.cc.drawImage(this.canvas,0,0);
    return this.cc.getImageData(0,0,this.combined.width,this.combined.height).data;}
};
