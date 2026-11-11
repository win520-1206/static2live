# Static2Live

开发进度：V0.4人物摇摆分项验证中，另已实现[V0.5离线蒙版编辑器](docs/V0.5_IMPLEMENTATION.md)开发接口（保护/运动源、撤销、缩放），不代表全部视觉验收通过。发布包版本暂不提升。

[V0.6 Web运行时扩展](docs/V0.6_IMPLEMENTATION.md)正在开发：性能档、虚拟桌面裁切、局部Shader和可选本地音频响应；原生适配与完整运行验收尚未完成。

[V1.0自动分析与推荐](docs/V1.0_IMPLEMENTATION.md)开发接口已加入：`analyze --input IMAGE`只分析，生成默认自动规划，`--no-auto-plan`可关闭。推荐依据写入analysis.json并由Validator复算，缺模型不自动下载或假降级。尚未通过完整V1.0验收。

[有界局部运动原语](docs/MOTION_PRIMITIVES.md)新增float/pan/zoom/rotate/wave/distortion：需要明确other蒙版，保护区保持不动；六种均有Web像素测试和各自合成源的原生GPU局部运动、保护区、开关及零强度观察。它们不代表照片或整个V1通过；当前门槛见[原规格审计](docs/V1_REQUIREMENT_AUDIT.md)。旧规划算法可继续验证，不改写旧输出。

本地图片 → 离线 Web 或原生 Wallpaper Engine Scene。V0.3 新增基于合法编辑器模板与真实纹理编译器的可选 Adapter；保留 Lite / Smart、Web 的六种效果及离线标注。代码 MIT，模型及引擎素材单独许可。不是视频生成器。

## V0.3 原生 Adapter

```powershell
static2live photo.jpg --target wallpaper-engine --mode smart --preset warm_portrait --model-cache models
# 非标准安装目录或合法同结构模板
static2live photo.jpg --target wallpaper-engine --engine-path "D:\SteamLibrary\steamapps\common\wallpaper_engine" --we-template TEMPLATE
static2live preview-native VERSION
```

默认只读使用本机官方 Depth Parallax 编辑器模板，复制到新输出，编译图片/深度/粒子纹理为真正 .tex，包含模型、材质与完整效果依赖。深度位移采用项目自有的有界 UV Shader，不平移整个相机；Shader 随包提供，需另行实际引擎验收。无安装/编译器/模板时保留 Web Export 并记录明确 warning、actual:web；模板损坏或实际编译失败不伪造成功。

原生入口 VERSION/wallpaper-engine/project.json，Web 备用为 VERSION/index.html。不会自动安装进 myprojects、替换桌面或发布。preview-native 使用独立 QA 窗口；发送命令不等于运行通过。可用编辑器“打开项目”选择 project.json。

原生优先映射深度视差、全画布雨/雪/尘/柔雾粒子与用户属性；原生粒子由引擎随机化，不与 Web 固定 seed 像素一致。局部粒子、Glow、Cloud Drift 仍完整保留在 Web，但原生明确列入 unsupported / warning，不宣称已映射。人物排除用同源像素覆盖板与同一视差效果，不是背景重建；混合排除语义会 warning。

可选 Foliage Sway 仅映射用户已确认的 other 蒙版：用 annotate 手画/导入植物等区域，再加 --native-sway --sway-amplitude-px 1 --regions JSON。默认关闭；不自动分析头发、衣料或脸部。幅度0–4画布像素且不超过短边1%。此 native-only 选项不是 V0.4 Human Parsing。缺蒙版拒绝，不强行作用整图。

属性面板：鼠标视差开关、视差强度0–100%、粒子开关、粒子强度0–100%；选用摇摆时另有摇摆开关/强度。原生 runtime 与 Web browser 检查分离；原生只在实际观察加载、四角、属性、鼠标及相关效果后记录：

```powershell
static2live validate VERSION --browser
# 观察 Web 后 record-visual；观察原生后才执行下条，check 项须确实检查过
static2live record-native VERSION --check load --check mouse --check edges --check properties --check particles --note "实际观察结果"
```

没完成原生观察，native_runtime 保持 not_tested，不能宣称 V0.3 完整验收。详见 [V0.3 实施说明](docs/V0.3_IMPLEMENTATION.md) 与 [本机验收](docs/V0.3_ACCEPTANCE.md)。复制的引擎模板/着色器仅按引擎许可本地使用，不以 MIT 重新许可或打包到软件分发。

## 安装（Python 3.10+）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
# 按需要安装可选本地模型依赖
.\.venv\Scripts\python.exe -m pip install ".[depth]"
.\.venv\Scripts\python.exe -m pip install ".[smart]"
```

建议使用独立虚拟环境安装。Windows 中文路径遇到 editable 安装编码问题时可使用普通 wheel 安装。命令入口为 static2live。

## Lite：无需分割模型

完全无模型需显式关闭视差：

```powershell
static2live photo.jpg --mode lite --no-parallax --effect dust
static2live annotate --input photo.jpg --output annotations
```

打开标注 index.html，选择人物/天空/水面/云层/发光区域/其他，画笔、擦除、清除、保存 regions.json。规则仅是亮度/蓝色候选，须预览确认，不是语义识别。再运行：

```powershell
static2live photo.jpg --mode lite --no-parallax --regions saved-regions.json --effect glow
```

Lite 保留视差仍需本地深度模型或 --depth-map，不伪造深度。

## Smart：本地自动识别

SegFormer B0 ADE 预测人物、天空、水面；不自动识别 cloud 或 glow。**NVIDIA 许可限非商业研究/评估，不是 MIT 商用权重授权。** 首次准备显式联网，照片不上传，生成只读本地缓存：

```powershell
static2live models prepare --kind segmentation --model-cache models --accept-model-license
static2live models prepare --kind depth --model-cache models
static2live photo.jpg --mode smart --preset warm_portrait --model-cache models
```

无需深度加 --no-parallax。缺模型报错，不下载或回退。修正预测：`annotate --input photo.jpg --regions VERSION/assets/regions.json`，保存新 JSON 后通过 --regions 生成；同类人工区域覆盖预测并记录来源。

下载慢时停止后沿用同一缓存，显式换国内镜像：

```powershell
static2live models prepare --kind segmentation --model-cache models --accept-model-license --download-endpoint https://hf-mirror.com
```

depth 同样支持该参数。官方元数据确定固定 revision 和预期哈希；镜像仅提供文件。元数据不可达或哈希不符停止，不关闭 TLS。实际下载使用官方源；镜像仅模拟校验测试，未真实下载。见 [许可](docs/MODEL_LICENSE.md)。

## 配置与单位

显式宽屏取景（默认仍保留原比例）：

```powershell
static2live photo.jpg --crop-aspect 16:9 --crop-anchor top --output output/16x9
static2live photo.jpg --crop-aspect 3440:1440 --crop-anchor top --output output/ultrawide
```

顶部锚定会优先保留头顶、裁去下部；不补画画外内容。取景发生在EXIF转正后、推理前，RGB、外部深度和导入蒙版共用源坐标裁切框。YAML为 `framing: {aspect: '16:9', anchor: top}`；anchor还可选center/bottom。不同屏幕比例应单独导出，运行时依旧cover，不能保证单一输出适配任意屏幕。已裁切bundle只允许相同框复用；换比例请用完整原图标注。当前annotate不直接编辑裁切bundle，详见[工作流](references/workflow.md)。每份新输出须重新视觉验收。

优先级 CLI > 用户 YAML > Preset > 自动规划建议 > 默认值。自动规划只补未明确指定项；显式 --effect 列表替换配置效果，不隐式叠加：

```yaml
preset: portrait_subtle
mode: lite
target: web
device: cpu
max_edge: 2048
parallax_enabled: true
seed: 1337
parallax:
  fraction: 0.002
  response_seconds: 0.2
effects:
  - type: dust
    intensity: 0.35
    count: 72
    speed_px_s: 9
    size_px: 2
    exclude_person: true
```

用 --config config.yaml。--strength 是短边比例，最高0.01；0仅停止视差，效果单独关闭。--no-parallax 不产生深度资源。深度图为 EXIF 转正原图同尺寸单通道，白色近，不猜方向。CUDA 需兼容 PyTorch/GPU。

| Preset | 幅度/短边 | 响应常数 | 效果 |
| --- | --- | --- | --- |
| portrait_subtle | 0.2% | 0.20秒 | 无 |
| general_balanced | 0.3% | 0.15秒 | 无 |
| landscape_soft | 0.4% | 0.18秒 | 无 |
| warm_portrait | 0.2% | 0.20秒 | 暖尘、人物排除 |
| rainy_city | 0.3% | 0.15秒 | 雨 |
| snow_soft | 0.4% | 0.18秒 | 雪 |
| anime_chill | 0.2% | 0.25秒 | 稀疏尘、局部Glow及Cloud Drift，须有对应区域 |
| snow_forest | 0.3% | 0.25秒 | 雪与柔雾；尚不含树木摇摆或光线束 |
| cyberpunk | 0.3% | 0.15秒 | 雨与局部neon_pulse，须有glow区域 |

效果 intensity 0–1，每类 count≤256，speed_px_s 为画布像素/秒，size_px 是雨线长度或其他粒子尺寸。region 默认 full，可指定确认区域；exclude_person 需人物蒙版，缺失 warning，不能宣称五官保护。cloud_drift 需 cloud 蒙版，amplitude_px≤短边1%，period_seconds 为周期。Glow 为区域颜色/亮度脉冲，Fog 为柔雾叠加，不是物理光照或体积重建。

## 输出与验证

默认保持比例、长边≤2048，不裁素材；浏览器 cover 可能裁窗口外区域。画布像素不同于屏幕物理像素。

输出 output/图片名/v001 等，含 HTML/CSS/runtime.js/effects.js、YAML、analysis/motion/manifest/validation、图片、masks/regions.json；Smart 另有 labels.png。双击 HTML，纹理与配置内嵌，无 fetch/CDN。WebGL 失败提示静态降级，不算动态通过；减少动态偏好停止运动。

标注页面单独保存，不修改原图或旧壁纸。--overwrite 只接受受管理的明确版本目录，拒绝输入位置、无关文件与符号链接，替换前备份。通常生成新版本。

```powershell
python -m pip install ".[dev]"
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.browsers"
python -m playwright install chromium
$env:STATIC2LIVE_BROWSER_TESTS = '1'
python -m pytest -q
static2live validate VERSION --browser
static2live record-visual VERSION --note "实际观察"
```

四态 passed/warning/failed/not_tested；结构、浏览器、视觉分离。返回码不等于视觉验收；重新 validate 重置视觉，改资源须重验。视觉记录复核浏览器 Manifest 哈希，不是算法保证。

examples/generate_scene.py 生成 CC0 风景与已知区域供六种效果验收，不冒充模型识别。私人素材、模型与本机输出不打包。未发布或全局安装 skill。

## 边界

V0.3基础Adapter本身不含自动发梢或完整编辑器；后续开发接口已有本地人物解析、保护/发梢权重和离线区域编辑，见上方版本说明，尚未完整视觉验收。当前均不含表情、精细发丝Alpha Matting、背景补全或MP4。深度UV不是分层重建；语义预测可能出错，仍须检查人物外观。原生Adapter不保证与Web像素相同。

见 [实施说明](docs/V0.2_IMPLEMENTATION.md)、[本机验收](docs/V0.2_ACCEPTANCE.md)、[设计](docs/V0.2_PLAN.md)、[薄 skill](SKILL.md)。V0.1 文档/输出保留为历史，新 Validator 兼容旧 Manifest。
