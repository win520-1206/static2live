# README 演示素材

这组 CC0 素材由 `examples/generate_readme_demos.py` 程序生成。三个 GIF 的每一帧均来自 Static2Live Web 运行时在 Chromium / SwiftShader 中的实际截图，Pillow 负责 GIF 编码。分辨率768×512，60帧、约12 FPS、5秒。

| 文件 | 实际输入与运行配置 |
| --- | --- |
| depth-parallax.gif | 程序风景、显式已知深度，Lite，视差短边比例0.01，左右指针输入 |
| portrait-motion.gif | 程序绘制人物、显式hair/protected/cloth区域，Lite，发梢3.5画布像素、5秒周期 |
| particle-effects.gif | 程序风景，Lite，snow 96粒、强度0.7、速度22画布像素/秒 |

这组区域示意用于展示渲染行为。真实照片与模型预测质量的验收范围见项目1.0说明。`landscape-source.png` 和 `portrait-source.png` 为原始静态输入，`provenance.json` 保存录制方式、帧差与GIF哈希。

在安装项目dev依赖和Playwright Chromium后，从仓库根目录复现。

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD/.browsers"
.\.venv\Scripts\python.exe examples/generate_readme_demos.py --work local-acceptance/readme-demos --output assets/demo
```

脚本按显式目标路径更新演示文件，工程、蒙版、深度和配置保存在work目录。使用新的output目录可保留当前演示不变。

These CC0 procedural fixtures are rendered by the actual Static2Live Web runtime. Depth and masks are supplied test data. GIFs show renderer behavior, while real-photo and model-quality acceptance is documented separately. Run the same command from the repository root to reproduce the assets.
