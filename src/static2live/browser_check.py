"""Optional real browser acceptance. No screenshot-only claims of success."""
import time
import base64
from pathlib import Path

import numpy as np
from PIL import Image

from .storage import read_json, write_json, sha256
from .validator import summary, validate_output


def check_browser(root):
    root = Path(root).resolve()
    previous = read_json(root / "validation.json") if (root / "validation.json").exists() else {}
    report = validate_output(root, write=False)
    result = {"name":"browser_runtime", "status":"not_tested", "detail":"浏览器尚未运行"}
    report["checks"][-2] = result
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["detail"] = "安装 dev 可选依赖和 Chromium 后重试"
        report["status"] = summary(report["checks"])
        write_json(root / "validation.json", report)
        return report
    launch_failed = True
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            launch_failed = False
            page = browser.new_page(viewport={"width":960,"height":540})
            errors, external = [], []
            page.on("pageerror", lambda e:errors.append(str(e)))
            page.on("console", lambda msg:errors.append(msg.text) if msg.type == "error" else None)
            page.on("request", lambda r:external.append(r.url) if r.url.startswith(("http:","https:")) else None)
            page.goto((root / "index.html").as_uri())
            page.wait_for_function("window.static2live && static2live.status !== 'loading'")
            state = page.evaluate("({status:static2live.status,shader:static2live.shaderCompiled,errors:static2live.errors})")
            if state["status"] != "ready" or not state["shader"]:
                raise ValueError(f"WebGL 未成功运行: {state}")
            page.evaluate('static2live.setTime?.(0)')
            # Isolate existing depth/effects/sway checks. V0.6 capability checks
            # remain separate not_tested entries, never inferred from these.
            page.evaluate('static2live.setShaderEnabled?.(false);static2live.setAudioEnabled?.(false)')
            def pixels():
                encoded = page.evaluate("""()=>{const a=static2live.readPixels();let s='';
                  for(let i=0;i<a.length;i+=8192)s+=String.fromCharCode(...a.slice(i,i+8192));return btoa(s)}""")
                return np.frombuffer(base64.b64decode(encoded),np.uint8).reshape(540,960,4)
            def settle(x,y):
                page.evaluate("([x,y])=>static2live.setPointer(x,y)",[x,y])
                page.wait_for_function("([x,y])=>Math.abs(static2live.pointer[0]-x)<0.0001 && Math.abs(static2live.pointer[1]-y)<0.0001",arg=[x,y])
            settle(-1,0); left=pixels()
            page.screenshot(path=str(root / "browser-left.png"))
            settle(1,0); right=pixels()
            page.screenshot(path=str(root / "browser-right.png"))
            amplitude = read_json(root / "motion.json")["parallax"]["amplitude_px"]
            difference = float(np.abs(left[:,:,:3].astype(float)-right[:,:,:3]).mean())
            if amplitude > 0 and difference == 0:
                raise ValueError("鼠标左右移动没有造成可测图像变化")
            if amplitude == 0 and not np.array_equal(left,right):
                raise ValueError("零强度仍产生画面变化")
            corner_checks=[]
            for x,y in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                settle(x,y); shot=pixels()
                if not np.all(shot[:,:,3] == 255):
                    raise ValueError("检测到透明边缘")
                corner_checks.append([x,y])
            page.emulate_media(reduced_motion="reduce")
            page.wait_for_function("static2live.reducedMotion && static2live.pointer.every(v=>v===0)")
            reduced=pixels()
            page.wait_for_timeout(150)
            if not np.array_equal(reduced,pixels()): raise ValueError('减少动态仍存在时间动画')
            page.set_viewport_size({"width":700,"height":700})
            page.wait_for_function("document.querySelector('canvas').width===700")
            page.emulate_media(reduced_motion="no-preference")
            page.set_viewport_size({"width":960,"height":540})
            page.wait_for_function("document.querySelector('canvas').width===960")
            settle(0,0)
            sway_test={'status':'not_applicable'}
            if read_json(root/'motion.json').get('sways'):
                page.evaluate('static2live.setEffectsEnabled(false);static2live.setParallaxEnabled(false);static2live.setTime(0)')
                page.wait_for_timeout(100);sway0=pixels()
                page.evaluate('static2live.setTime(2)');page.wait_for_timeout(100);sway2=pixels()
                change=float(np.abs(sway0.astype(float)-sway2.astype(float)).mean())
                if change==0:raise ValueError('启用人物sway但时间变化无帧差异')
                sm=read_json(root/'motion.json');iw=sm['canvas']['width'];ih=sm['canvas']['height']
                rect=sm.get('runtime',{}).get('display',{}).get('viewport',[0,0,1,1])
                yy,xx=np.mgrid[:540,:960];ia=iw/ih;va=960/540*rect[3]/rect[2]
                cx=min(1,va/ia);cy=min(1,ia/va);margin=sm['parallax']['overscan_px']
                sx=(margin/iw+((rect[0]+(xx+.5)/960*rect[2]-.5)*cx+.5)*(1-2*margin/iw))*iw
                # readPixels is bottom-up; masks on disk are top-down.
                sy=(margin/ih+((rect[1]+(1-(yy+.5)/540)*rect[3]-.5)*cy+.5)*(1-2*margin/ih))*ih
                with Image.open(root/sm['regions']['protected']['asset']) as p:
                    protected=np.asarray(p)[np.clip(sy.astype(int),0,ih-1),np.clip(sx.astype(int),0,iw-1)]==255
                if not protected.any():raise ValueError('浏览器视口没有可检验的保护区')
                if not np.array_equal(sway0[protected],sway2[protected]):raise ValueError('保护区像素在局部摇摆时发生变化')
                page.evaluate('static2live.setSwayStrength(0)');page.wait_for_timeout(100);zero2=pixels()
                page.evaluate('static2live.setTime(0)');page.wait_for_timeout(100);zero0=pixels()
                if not np.array_equal(zero2,zero0):raise ValueError('sway零强度仍随时间变化')
                page.evaluate('static2live.setSwayStrength(1);static2live.setSwayEnabled(false)');page.wait_for_timeout(100);off0=pixels()
                page.evaluate('static2live.setTime(2)');page.wait_for_timeout(100);off2=pixels()
                if not np.array_equal(off0,off2):raise ValueError('sway关闭后仍随时间变化')
                page.evaluate('static2live.setSwayEnabled(true);static2live.setEffectsEnabled(true);static2live.setParallaxEnabled(true);static2live.setTime(0)')
                sway_test={'status':'passed','mean_time_difference':change,'zero_stable':True,'off_stable':True,'protected_pixels_unchanged':int(protected.sum())}
            effect_test={'status':'not_applicable','detail':'没有启用非零效果'}
            effect_motion=read_json(root/'motion.json')
            active=any(e['enabled'] and e['intensity']>0 and (e['count']>0 or e['type'] in ['glow','cloud_drift']) for e in effect_motion.get('effects',[]))
            if active:
                page.evaluate('static2live.setSwayEnabled?.(false)')
                page.evaluate('static2live.setParallaxEnabled(false);static2live.pointer=[0,0]')
                page.evaluate('static2live.setTime(0)');page.wait_for_timeout(100);frame0=pixels()
                page.evaluate('static2live.setTime(2)');page.wait_for_timeout(100);frame2=pixels()
                change=float(np.abs(frame0.astype(float)-frame2.astype(float)).mean())
                if change==0: raise ValueError('启用效果但时间改变没有可见帧变化')
                page.evaluate('static2live.setEffectsEnabled(false)');page.wait_for_timeout(100);off2=pixels()
                page.evaluate('static2live.setTime(0)');page.wait_for_timeout(100);off0=pixels()
                if not np.array_equal(off2,off0): raise ValueError('效果关闭后仍在随时间变化')
                page.evaluate('static2live.setEffectsEnabled(true)');page.wait_for_timeout(100)
                page.evaluate('static2live.setParallaxEnabled(true)')
                page.evaluate('static2live.setSwayEnabled?.(true)')
                effect_test={'status':'passed','mean_time_difference':change,'disable_stable':True}
            page.evaluate('static2live.setShaderEnabled?.(true);static2live.setAudioEnabled?.(true)')
            page.screenshot(path=str(root / "browser-preview.png"))
            manifest = read_json(root / "manifest.json")
            for name in ("browser-preview.png", "browser-left.png", "browser-right.png"):
                manifest["resources"][name] = sha256(root / name)
            write_json(root / "manifest.json", manifest)
            # Explicitly test failure mode without treating fallback as interactive success.
            fallback = browser.new_page()
            fallback.add_init_script("HTMLCanvasElement.prototype.getContext=function(){return null}")
            fallback.goto((root / "index.html").as_uri())
            fallback.wait_for_function("window.static2live && static2live.status==='fallback'")
            if not fallback.locator("#notice").is_visible() or not fallback.locator("#fallback").is_visible():
                raise ValueError("静态降级提示缺失")
            if errors or external:
                raise ValueError(f"控制台或网络错误: {errors}, {external}")
            result.update(status="passed",detail={"shader":state,"mean_left_right_difference":difference,
                                                   "corners":corner_checks,"resize":True,"reduced_motion":True,
                                                   "fallback":True,"external_requests":external,'effects':effect_test,'sway':sway_test,
                                                   "browser":browser.version,"manifest_sha256":sha256(root / "manifest.json")})
            browser.close()
    except Exception as error:
        result.update(status="not_tested" if launch_failed else "failed",detail=str(error))
    report["status"] = summary(report["checks"])
    write_json(root / "validation.json", report)
    return report


def record_visual(root, note):
    if not note.strip():
        raise ValueError("人工验收记录必须说明实际观察结果")
    root = Path(root)
    previous = read_json(root / "validation.json")
    fresh = validate_output(root,write=False)
    current_hash = sha256(root / "manifest.json")
    browser = next((c for c in previous.get("checks",[]) if c.get("name")=="browser_runtime"),{})
    detail = browser.get("detail")
    if (fresh["structural_status"] == "failed" or browser.get("status") != "passed"
            or not isinstance(detail,dict) or detail.get("manifest_sha256") != current_hash):
        raise ValueError("结构/浏览器验证未通过，不能记录完整视觉通过")
    # Rebuild structure and capability inventory. A stale/edited report must
    # not omit new required checks or carry invented passed entries forward.
    report = fresh
    native = next((c for c in previous.get('checks',[]) if c.get('name')=='native_runtime'),{})
    native_detail = native.get('detail')
    native_current = (native.get('status')=='passed' and isinstance(native_detail,dict)
        and native_detail.get('manifest_sha256')==current_hash
        and native_detail.get('target')=='native-scene'
        and read_json(root/'manifest.json').get('adapter',{}).get('actual')=='native-scene')
    for check in report["checks"]:
        if check['name']=='browser_runtime':
            check.update(browser)
        elif native_current and check['name'] in ('native_runtime','audio_runtime','advanced_shader_runtime'):
            old = next((c for c in previous.get('checks',[]) if c.get('name')==check['name']),{})
            capability = {'audio_runtime':'audio','advanced_shader_runtime':'shader'}.get(check['name'])
            if (old.get('status')=='passed' and old.get('detail')==native_detail
                    and (capability is None or capability in native_detail.get('observed',[]))):
                check.update(old)
        if check["name"] == "visual_acceptance":
            check.update(status="passed", detail={"note":note,"recorded_unix":time.time(),"method":"recorded visual observation; not an automated guarantee", "manifest_sha256":current_hash})
    report["status"] = summary(report["checks"])
    write_json(root / "validation.json",report)
    return report
