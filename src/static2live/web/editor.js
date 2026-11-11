/* Offline source masks only. No network, model calls, or RGB rewriting. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const boot = JSON.parse($('editor-data').textContent), canvas = $('paint');
  const ctx = canvas.getContext('2d');
  const keys = boot.editable_regions, derived = ['hair_sway', 'cloth_sway'];
  const state = window.static2liveEditor = {ready: false, busy: false, masks: {}, metadata: {}, candidate: null};
  canvas.width = boot.canvas.width; canvas.height = boot.canvas.height;
  const create = () => {const c = document.createElement('canvas'); c.width = canvas.width; c.height = canvas.height; return c;};
  const defaults = key => ({id: key, source: 'manual', confirmed: true});
  const active = new Set(), undo = [], redo = [];
  const historyLimit = 64 * 1024 * 1024;
  keys.forEach(k => {state.masks[k] = create(); state.metadata[k] = defaults(k);});
  const image = new Image(); image.src = boot.image;
  function status(message, error = false) {$('status').textContent = message; $('status').dataset.error = String(error);}
  function historyButtons() {$('undo').disabled = !undo.length || !!state.candidate; $('redo').disabled = !redo.length || !!state.candidate;}
  function alpha(mask) {
    const data = mask.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    const a = new Uint8Array(canvas.width * canvas.height);
    for (let p = 0; p < a.length; p++) a[p] = data[p * 4 + 3];
    return a;
  }
  function fromAlpha(a) {
    const c = create(), cc = c.getContext('2d'), data = cc.createImageData(canvas.width, canvas.height);
    for (let p = 0; p < a.length; p++) {data.data[p*4] = data.data[p*4+1] = data.data[p*4+2] = 255; data.data[p*4+3] = a[p];}
    cc.putImageData(data, 0, 0); return c;
  }
  function snapshot(key) {return {key, pixels: alpha(state.masks[key]), metadata: structuredClone(state.metadata[key]), active: active.has(key)};}
  function trimHistory() {
    while (undo.length + redo.length > 20 || (undo.length + redo.length) * canvas.width * canvas.height > historyLimit) {
      if (undo.length) undo.shift(); else redo.shift();
    }
    historyButtons();
  }
  function remember(key) {undo.push(snapshot(key)); redo.length = 0; trimHistory();}
  function restore(from, to) {
    if (!from.length || state.candidate || painting || state.busy) return;
    const previous = from.pop(); to.push(snapshot(previous.key));
    state.masks[previous.key] = fromAlpha(previous.pixels); state.metadata[previous.key] = previous.metadata;
    if (previous.active) active.add(previous.key); else active.delete(previous.key);
    $('category').value = previous.key; trimHistory(); draw(); status('已恢复区域：' + previous.key);
  }
  function manual(key) {
    const previous = state.metadata[key];
    state.metadata[key] = {...previous, id: key, source: 'manual', confirmed: true};
    if (previous.source !== 'manual') state.metadata[key].previous_source = previous;
    active.add(key);
  }
  function grayMask(mask) {
    const a = alpha(mask), c = create(), cc = c.getContext('2d'), data = cc.createImageData(canvas.width, canvas.height);
    for (let p = 0; p < a.length; p++) {data.data[p*4] = data.data[p*4+1] = data.data[p*4+2] = a[p]; data.data[p*4+3] = 255;}
    cc.putImageData(data, 0, 0); return c.toDataURL('image/png');
  }
  const tint = create(), tc = tint.getContext('2d');
  function overlay(mask, color, opacity) {
    tc.clearRect(0, 0, canvas.width, canvas.height); tc.globalCompositeOperation = 'source-over'; tc.fillStyle = color;
    tc.fillRect(0, 0, canvas.width, canvas.height); tc.globalCompositeOperation = 'destination-in'; tc.drawImage(mask, 0, 0);
    ctx.globalAlpha = opacity; ctx.drawImage(tint, 0, 0); ctx.globalAlpha = 1;
  }
  function draw() {
    ctx.drawImage(image, 0, 0);
    if (!$('preview').checked) return;
    const key = $('category').value;
    if (key !== 'protected') overlay(state.masks[key], '#41e0ad', .45);
    overlay(state.masks.protected, '#ff5268', .55);
    if (state.candidate) overlay(state.candidate.mask, '#ffc354', .55);
  }
  function clearCandidate() {state.candidate = null; $('confirm').disabled = $('discard').disabled = true; historyButtons();}
  async function loadBundle(bundle) {
    if (painting) throw Error('请结束当前笔画后导入');
    if (!['0.2', '0.4'].includes(bundle?.version) || bundle.coordinates !== boot.coordinates || bundle.input_sha256 !== boot.input_sha256 || bundle.canvas?.width !== canvas.width || bundle.canvas?.height !== canvas.height)
      throw Error('图片绑定或画布尺寸不一致；请先使用 CLI 统一尺寸');
    if (!Array.isArray(bundle.regions) || bundle.regions.length > keys.length + derived.length) throw Error('区域列表无效');
    const prepared = {}, seen = new Set(); let skipped = 0;
    for (const r of bundle.regions) {
      if (!r || ![...keys, ...derived].includes(r.id) || seen.has(r.id) || !['manual','imported','rule','model'].includes(r.source) || r.confirmed !== true || typeof r.asset !== 'string' || !r.asset.startsWith('data:image/png;base64,') || r.asset.length > 64*1024*1024)
        throw Error('导入需独立嵌入 PNG 蒙版、合法来源和确认状态');
      seen.add(r.id);
      if (derived.includes(r.id)) {skipped++; continue;}
      const im = new Image(); im.src = r.asset; await im.decode();
      if (im.width !== canvas.width || im.height !== canvas.height) throw Error('蒙版尺寸错误');
      const c = create(), cc = c.getContext('2d', {willReadFrequently: true}); cc.drawImage(im, 0, 0);
      const data = cc.getImageData(0, 0, c.width, c.height);
      for (let i = 0; i < data.data.length; i += 4) {
        if (data.data[i] !== data.data[i+1] || data.data[i] !== data.data[i+2] || data.data[i+3] !== 255) throw Error('蒙版需不透明灰度 PNG');
        data.data[i+3] = data.data[i]; data.data[i] = data.data[i+1] = data.data[i+2] = 255;
      }
      cc.putImageData(data, 0, 0); const {asset, ...metadata} = r; prepared[r.id] = {mask: c, metadata};
    }
    active.clear();
    keys.forEach(k => {state.masks[k] = prepared[k]?.mask || create(); state.metadata[k] = prepared[k]?.metadata || defaults(k); if (prepared[k]) active.add(k);});
    undo.length = redo.length = 0; clearCandidate(); draw();
    status('已导入；撤销记录已重置。' + (skipped ? '派生摇摆权重已忽略，重新生成时由源蒙版计算。' : ''));
  }
  async function importBundle(bundle) {
    if (state.busy) throw Error('已有导入正在进行，请稍候');
    state.busy = true;
    try {await loadBundle(bundle);} finally {state.busy = false;}
  }
  state.exportBundle = () => {
    if (!state.ready || state.busy) throw Error('请等待图片加载或导入完成');
    if (state.candidate || painting) throw Error('请结束笔画并确认或取消规则候选后再保存');
    return {version: '0.4', coordinates: boot.coordinates, input_sha256: boot.input_sha256, canvas: boot.canvas,
      regions: keys.filter(k => active.has(k)).map(k => ({...state.metadata[k], asset: grayMask(state.masks[k])}))};
  };
  state.normalizedPoint = (x,y) => {const r = canvas.getBoundingClientRect(); return [Math.max(0,Math.min(1,(x-r.left)/r.width)),Math.max(0,Math.min(1,(y-r.top)/r.height))];};
  let painting = false, last = null, strokeKey = null;
  function stroke(event) {
    if (!painting || state.candidate) return;
    const [u,v] = state.normalizedPoint(event.clientX,event.clientY), p = [u*canvas.width,v*canvas.height];
    const c = state.masks[strokeKey].getContext('2d'), radius = Number($('radius').value);
    c.globalCompositeOperation = $('tool').value === 'erase' ? 'destination-out' : 'source-over';
    c.strokeStyle = c.fillStyle = '#fff'; c.lineWidth = radius*2; c.lineCap = 'round'; c.beginPath(); c.moveTo(...(last || p)); c.lineTo(...p); c.stroke();
    c.beginPath(); c.arc(...p,radius,0,Math.PI*2); c.fill(); last = p; manual(strokeKey); draw();
  }
  canvas.onpointerdown = e => {
    if (!state.ready || state.busy || state.candidate || painting || (e.pointerType === 'mouse' && e.button !== 0)) return;
    strokeKey = $('tool').value === 'protect' ? 'protected' : $('category').value;
    if ($('tool').value === 'animate' && strokeKey === 'protected') {status('请先选择头发、衣料或其他运动源区域', true); return;}
    remember(strokeKey); painting = true; last = null; canvas.setPointerCapture(e.pointerId); stroke(e);
  };
  canvas.onpointermove = stroke;
  canvas.onpointerup = canvas.onpointercancel = canvas.onlostpointercapture = () => {painting = false; last = null;};
  $('category').onchange = () => {clearCandidate(); draw();}; $('preview').onchange = draw;
  $('radius').oninput = () => {$('radius-value').textContent = $('radius').value;};
  $('tool').onchange = () => {clearCandidate(); status($('tool').value === 'protect' ? '保护工具：笔画写入红色 protected 区域' : '就绪：当前工具只编辑蒙版，不播放动画'); draw();};
  $('undo').onclick = () => restore(undo, redo); $('redo').onclick = () => restore(redo, undo);
  document.addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey) || ['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)) return;
    if (e.key.toLowerCase() === 'z') {e.preventDefault(); restore(e.shiftKey ? redo : undo, e.shiftKey ? undo : redo);}
    if (e.key.toLowerCase() === 'y') {e.preventDefault(); restore(redo, undo);}
  });
  $('zoom').onchange = () => {canvas.style.width = $('zoom').value === 'fit' ? '100%' : `${canvas.width * Number($('zoom').value)}px`;};
  $('clear').onclick = () => {if (!state.ready || state.busy || painting) return; clearCandidate(); const k = $('category').value; remember(k); state.masks[k] = create(); manual(k); draw(); status('已清空 ' + k + '；导出保留空蒙版，避免重新使用旧预测。可撤销。');};
  function rule(type) {
    if (!state.ready || state.busy || painting) return;
    const ymin = Number($('ymin').value), ymax = Number($('ymax').value), threshold = Number($('threshold').value);
    if (![ymin,ymax,threshold].every(Number.isFinite) || ymin < 0 || ymax > 1 || ymin >= ymax || threshold < 0 || threshold > 255) {status('范围须 0 ≤ y_min < y_max ≤ 1，阈值 0–255', true); return;}
    const raw = create(), rc = raw.getContext('2d', {willReadFrequently: true}); rc.drawImage(image,0,0); const data = rc.getImageData(0,0,raw.width,raw.height);
    for (let i=0; i<data.data.length; i+=4) {
      const y = Math.floor(i/4/raw.width)/raw.height, r = data.data[i], g = data.data[i+1], b = data.data[i+2];
      const selected = y>=ymin && y<=ymax && (type==='brightness' ? .2126*r+.7152*g+.0722*b>=threshold : b>=threshold && b>r*1.1 && b>g*1.05);
      data.data[i] = data.data[i+1] = data.data[i+2] = 255; data.data[i+3] = selected ? 255 : 0;
    }
    rc.putImageData(data,0,0); state.candidate = {mask:raw,rule:{type,threshold,ymin,ymax}}; $('confirm').disabled = $('discard').disabled = false; historyButtons(); status('黄色候选尚未确认，不会导出'); draw();
  }
  $('bright').onclick = () => rule('brightness'); $('blue').onclick = () => rule('blue');
  $('confirm').onclick = () => {if (!state.candidate || state.busy) return; const k = $('category').value; remember(k); state.masks[k] = state.candidate.mask; state.metadata[k] = {id:k,source:'rule',confirmed:true,rule:state.candidate.rule}; active.add(k); clearCandidate(); status('已确认规则区域；可撤销'); draw();};
  $('discard').onclick = () => {clearCandidate(); draw(); status('已取消候选');};
  $('save').onclick = () => {try {
    const blob = new Blob([JSON.stringify(state.exportBundle(),null,2)],{type:'application/json'}), url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = 'regions.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); status('已请求保存独立标注文件；原图和壁纸未修改');
  } catch(e) {status(e.message,true);}};
  $('import').onchange = async e => {const file = e.target.files[0]; if (!file) return; try {
    if (file.size > 64*1024*1024) throw Error('标注文件超过 64 MiB');
    await importBundle(JSON.parse(await file.text()));
  } catch(e) {status(e.message,true);} finally {e.target.value = '';}};
  state.importBundle = importBundle;
  image.decode().then(async () => {if (boot.regions.length) await importBundle(boot); state.ready = true; if (!boot.regions.length) status('就绪：选择区域后绘制，关闭前请导出'); draw();}).catch(e => status('加载失败：'+e.message,true));
})();
