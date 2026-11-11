# 本机验收记录（2026-10-04）

> 历史验收摘要来自维护者本地记录。文中 `local-acceptance/`、`output/` 和标注产物保留在本地，公开仓库提供源码与合成示例。测试结果按记录日期和所列范围解释，完整 V1 验收仍在进行。


本次只验收 V0.1。原设计规格、原照片、以前的动态壁纸和视频保留未改。没有 GitHub 仓库、发布操作、全局 skill 安装或后续版本模块。

## 环境和安装

Windows；主虚拟环境 Python 3.10.20，继承 本地基础环境 的 PyTorch 2.12.0+cpu。新依赖仅装在项目 `.venv`；Transformers 4.57.6、huggingface-hub 0.36.2。模型和测试浏览器显式联网准备后，生成和 Web 播放离线。

已运行安装、CLI help、模型准备、真实 CPU 推理、单元测试、浏览器测试、skill quick_validate、sdist/wheel 打包，以及另一个虚拟环境从 wheel 安装后的生成。wheel 含三个 Preset 和 Web 运行时，不依赖源目录。曾遇到 editable .pth 的中文路径与 Python UTF-8 模式冲突，交付改为普通 wheel 安装，未改原 conda 环境。

## 模型和真实流程

官方 `depth-anything/Depth-Anything-V2-Small-hf`，Apache-2.0，revision `5426e4f0f36572d16453bbda7a8389317b1bef99`。权重 SHA-256 `[本地记录哈希]`，所有必要文件哈希位于本地模型记录。

用户照片真实推理两次，生成 v001 / v002，2048×1365，不裁保存素材，portrait_subtle 单轴最大 2.73 画布像素。两份输入哈希与原照片当前哈希一致；两份深度 PNG 哈希一致，说明本次重复 CPU 流程一致。这不是跨设备绝对确定性承诺。私人样例仅存在被忽略的 output 中。

## 自动验证

最终测试 23 项通过，包括配置优先级、有限数值与幅度单位、非法目标、损坏图片、深度尺寸和近白方向、缺模型报错、原图/规范 RGB 保真、Manifest 资源引用与哈希、内嵌数据一致性、并发版本分配、覆盖备份/输入/用户文件保护、任意工作目录 CLI。

合成图是程序生成的 CC0 图，不冒充真实深度推理。测试证实左右位移符号相反，白色近区域位移大于黑色远区域，零幅度输出逐像素一致，最高合法幅度可运行。

实际 Chromium 153.0.8010.12 用 SwiftShader WebGL 直接打开 file:// HTML，着色器编译、纹理、鼠标帧变化、四角不透明、窗口缩放、减少动态、静态降级提示均通过。无 HTTP 外部请求和脚本/控制台 error。照片左右极值画面平均 RGB 差异约 4.7685（0–255 单通道单位，不是位移单位）。浏览器检查证据记录在各版本 validation.json，截图也受 Manifest 哈希跟踪。

## 视觉检查与限制

Codex 已检查真实浏览器截图的左右极值和中间画面：相对位移可见但很轻，未观察到明显撕裂、重影或透明边缘。自动像素测试不能替代对所有图像/设备的观察，也不能证明五官完全固定。v002 的视觉记录显式写明观察者和局限，不声称用户本人已批准。

16:9 窗口以 cover 显示 3:2 源图，头顶/下部会有窗口裁切；保存的 3:2 图片没有裁切。安全 UV 边缘有轻微放大，没有隐藏背景补全。未进行真实 GPU 或 CUDA 性能验收；默认 CPU 模型和浏览器软件 WebGL 已验收。

分割、人物保护、发梢、表情、粒子、背景修复、原生 Wallpaper Engine、视频导出及标注编辑器均不适用，没有伪造通过。报告层级为结构 / 浏览器 / 实际视觉；纯结构生成的 status=not_tested 是预期行为，不能据此声称完整验收。

## 重现命令（在项目目录）

```powershell
.\.venv\Scripts\static2live.exe --help
.\.venv\Scripts\static2live.exe models prepare --model-cache .\models
.\.venv\Scripts\static2live.exe generate --input "原照片路径" --model-cache .\models --preset portrait_subtle --output .\output
# 同样生成命令再次执行会分配下一版本
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.browsers"
$env:STATIC2LIVE_BROWSER_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\static2live.exe validate "实际版本目录" --browser
# 打开 index.html 实际观察，再用 record-visual 记录；不提前声明视觉通过
```

模型准备不是每次生成的必要步骤；已有缓存时不需再次联网。修改源代码后需重新安装再测试。
