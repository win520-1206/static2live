/* User-selected local audio, or the documented Wallpaper Engine Web callback.
   No microphone, system capture request, external URL, or automatic playback. */
window.Static2LiveAudio = class {
  constructor(options,state) {
    this.options=options;this.state=state;this.target=0;this.level=0;this.lastInput=-Infinity;
    this.enabled=!!options.enabled;this.context=null;this.source=null;this.url=null;
    state.audio={status:this.enabled?'waiting':'disabled',level:0,source:null};
    state.setAudioEnabled=value=>{this.enabled=!!value && !!options.enabled;if(!this.enabled){this.target=0;this.level=0;}state.audio.status=this.enabled?'waiting':'disabled';};
    if(!this.enabled)return;
    if(typeof window.wallpaperRegisterAudioListener==='function') {
      state.audio.source='wallpaper-engine';
      window.wallpaperRegisterAudioListener(values=>{
        if(!this.enabled || !values || values.length!==128)return;
        let sum=0;for(let i=0;i<8;i++)sum+=this.safe(values[i])+this.safe(values[i+64]);
        this.receive(sum/16);state.audio.status='engine';
      });
    } else {
      const controls=document.getElementById('audio-controls');controls.hidden=false;
      this.player=document.getElementById('audio-player');
      document.getElementById('audio-file').onchange=async event=>{
        const file=event.target.files[0];if(!file)return;
        try {
          await this.stop();
          const player=document.createElement('audio');player.id='audio-player';player.controls=true;
          this.player.replaceWith(player);this.player=player;
          const AudioContext=window.AudioContext||window.webkitAudioContext;
          if(!AudioContext)throw Error('浏览器不支持 Web Audio');
          this.context=new AudioContext();this.analyser=this.context.createAnalyser();this.analyser.fftSize=256;
          this.analyser.smoothingTimeConstant=0;this.samples=new Uint8Array(this.analyser.frequencyBinCount);
          this.source=this.context.createMediaElementSource(this.player);this.source.connect(this.analyser);this.analyser.connect(this.context.destination);
          this.url=URL.createObjectURL(file);this.player.src=this.url;this.player.loop=true;
          this.player.onerror=()=>{state.audio.status='error';document.getElementById('audio-status').textContent='音频解码失败，请换浏览器支持的文件';};
          await this.context.resume();await this.player.play();state.audio.source='local-file';state.audio.status='playing';
          document.getElementById('audio-status').textContent='本地播放中，可暂停或停止；不保存音频到壁纸。';
        }catch(error){state.audio.status='error';document.getElementById('audio-status').textContent=error.message;await this.stop();}
        finally{event.target.value='';}
      };
      document.getElementById('audio-stop').onclick=()=>this.stop();
      this.player.onerror=()=>{state.audio.status='error';document.getElementById('audio-status').textContent='音频解码失败，请换浏览器支持的文件';};
    }
    addEventListener('pagehide',()=>this.stop());
  }
  safe(v){return Number.isFinite(v)?Math.max(0,Math.min(1,v)):0;}
  receive(level){this.target=this.safe(level);this.lastInput=performance.now();}
  update(dt,reduced) {
    if(this.analyser && this.context?.state==='running' && !this.player.paused) {
      this.analyser.getByteFrequencyData(this.samples);let sum=0;for(let i=0;i<8;i++)sum+=this.samples[i]/255;this.receive(sum/8);
    }
    const target=this.enabled && !reduced && performance.now()-this.lastInput<500?this.target:0;
    this.level=reduced || !this.enabled?0:this.level+(target-this.level)*(1-Math.exp(-dt/this.options.response_seconds));
    this.state.audio.level=this.level;return this.level*this.options.strength;
  }
  async stop() {
    if(this.player){this.player.pause();this.player.removeAttribute('src');this.player.load();}
    this.source?.disconnect();this.analyser?.disconnect();if(this.context && this.context.state!=='closed')await this.context.close();
    this.context=null;this.source=null;this.analyser=null;if(this.url)URL.revokeObjectURL(this.url);this.url=null;
    this.target=this.level=0;this.lastInput=-Infinity;this.state.audio.level=0;
    if(this.state.audio.status!=='error')this.state.audio.status=this.enabled?'waiting':'disabled';
  }
};
