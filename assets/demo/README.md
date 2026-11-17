# README 演示素材

三组演示使用真实照片或AI生成的写实底图。每一帧均来自Static2Live Web运行时在Chromium / SwiftShader中的实际截图，Pillow负责动画编码。首页使用960×540高画质动态WebP，同目录保留768×432兼容GIF副本。各采样60帧、约12 FPS、5秒；编码可合并相邻重复帧并保留完整时长。

| 文件 | 输入、来源与效果 |
| --- | --- |
| [depth-parallax.webp](depth-parallax.webp) / [GIF](depth-parallax.gif) | AI生成的湖畔山景，本地Depth Anything V2 Small估计深度，Lite导入深度图，视差短边比例0.006 |
| [portrait-motion.webp](portrait-motion.webp) / [GIF](portrait-motion.gif) | 用户提供并授权展示的人像照片，人物模型结果经用户修正后导入，发梢/衣料微动态及暖尘，指针保持中央 |
| [particle-effects.webp](particle-effects.webp) / [GIF](particle-effects.gif) | AI生成的冬日街景，Lite绘制110个动态雪粒子，强度0.7、速度55画布像素/秒 |

## 来源与权限

- `portrait-source.png`为1280×720展示副本，沿用此前确认的顶部优先16:9构图，原始高分辨率照片保留在本机。用户授权此照片和衍生动图用于本项目README展示，后续再利用须确认图片与肖像权利人的许可。MIT代码许可不自动授予照片再利用权。
- `landscape-source.png`与`particle-source.png`通过内置image_gen生成，再制作适合网页展示的副本。完整生成提示词见[prompts.md](prompts.md)。底图为AI生成图像，动画为实际程序运行结果。
- `depth-map.png`来自本地真实Depth Anything V2 Small模型推理，模型revision和哈希保存在`depth-provenance.json`。
- `portrait-regions.json`是与公开展示副本对齐的区域，源自已认可工程的人物解析及人工修正；导入后由核心重新生成运动权重。区域和深度资源用于复现这几组演示。
- `provenance.json`保存来源类型、输入哈希、截图参数和动图哈希。源照片、AI图像与衍生动图的权利独立于代码许可，测试目录中原有的程序生成CC0素材保持其原许可。

## 复现

在仓库根目录安装dev依赖及Playwright Chromium后执行。

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD/.browsers"
.\.venv\Scripts\python.exe examples/generate_readme_demos.py --assets assets/demo --work local-acceptance/readme-demos --output assets/demo
```

随附深度图和区域可直接复现，模型推理及人物编辑在准备素材时已完成。脚本按显式output路径更新WebP、GIF与provenance；使用新的output目录可保留当前演示。原始素材的制作与许可记录按上述来源解释。

## English

These animations capture the actual Static2Live Web runtime with 60 samples at 12 FPS over 5 seconds. Encoding may merge adjacent identical frames while retaining the full duration. The README displays high-quality 960×540 animated WebP, with 768×432 compatibility GIF copies included. The landscape and winter street are AI-generated photographic-style sources made with the built-in image_gen tool. Their prompts are included. The portrait is the user's photograph, authorized for this project's README display. The public portrait source is a reduced 1280×720 top-priority crop. Further use of the photo or derived animations requires confirming permission from the rights holder.

Depth comes from real local Depth Anything V2 Small inference. Portrait regions originated from human parsing and user corrections, then were aligned with the display source and imported into Lite. Included depth/regions let the same command reproduce the animations. Image and animation rights are separate from the MIT code license. Existing CC0 procedural test fixtures retain their original license.
