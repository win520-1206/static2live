## 从请求到参数

已实现V1.0自动规划开发接口，包尚未完成V1.0发布验收；先读[自动分析与规划](../docs/V1.0_IMPLEMENTATION.md)。`static2live IMAGE`默认auto_plan；它在当前Lite/Smart模式内分析，不静默换模式或下载模型。`static2live analyze --input IMAGE --no-parallax`可只做无模型分析，不创建壁纸；没有语义证据时只给通用推荐。需要真实自动区域用Smart，细人物用已准备且授权的human-parsing；用户明确选择Lite时不擅自启用模型。

把自然语言意图映射到已有配置，解释实际能做的部分；不承诺通用语言解析器或读心。例如：

| 用户意图 | 参数与判断 |
| --- | --- |
| 自然微动态、人像 | 自动规划或portrait_subtle / warm_portrait；hair/cloth只有来源蒙版和非空protected时启用。只有person时整个人物保守保护，不冒充脸/发丝识别 |
| 发梢再轻一点 | 改hair_sway.amplitude_px，不改整幅视差；相位/周期和衣料分开。用户明确0或关闭必须保留 |
| 粒子少一点、不要粒子 | 改effects中的count/intensity，或用户YAML设effects: []；不要误改鼠标或头发参数。明确“不要”优先于风格默认值 |
| 雨 / 雪 / 水面微波 | rainy_city / snow_soft；water_ripple必须已有water区域。不按颜色猜天气或把天空等同云层 |
| 动漫氛围 / 雪林 / 霓虹 | anime_chill / snow_forest / cyberpunk只是运动与灯光风格，不重画人物。cyberpunk的neon_pulse需非空glow；雪林不冒称自动识别树或自动光线追踪 |
| 鼠标跟随轻一点 | --strength为短边比例，上限.01；用户要求像素时先除以画布短边，不能当作0–100强度 |
| 跟随音乐 | 仅显式请求时audio.enabled；先说明输入来源。默认无音频，不请求麦克风、不自动播放测试声 |
| 局部轻浮动、平移、缩放、旋转或波动 | 读取[运动原语](../docs/MOTION_PRIMITIVES.md)，用shader.preset选择float/pan/zoom/rotate/wave/distortion；须有明确other蒙版，不擅自作用整图或人脸 |
| 无交互视频、眨眼或说话 | 当前不支持，不用静态画面或变脸效果代替，也不另写视频渲染器 |

CLI > 用户YAML > 所选Preset > 自动建议 > 默认值。自动推荐只补未指定项，不改输入、目标、模式、设备、尺寸或明确的开关。用--no-auto-plan禁用自动建议；仍可读取分析报告。优先复用用户已有蒙版；显式清空的保护区不能被自动重新填上来制造通过。

## 明确的宽屏构图

默认不裁切。用户要求铺满且优先保留头顶时，生成独立版本，加 `--crop-aspect 16:9 --crop-anchor top`；3440×1440用 `--crop-aspect 3440:1440 --crop-anchor top`。比例不同应分别导出，不承诺同一输出在任意宽屏都保留相同构图。取景仅裁去多余部分，不生成画外内容，超宽屏会丢失更多下部发梢/衣料。

CLI对应YAML `framing: {aspect: '16:9', anchor: top}`，优先级不变；自动规划不改构图。EXIF转正后、推理前裁切RGB，本地深度模型重新推理裁切图；原尺寸外部深度图和完整原图蒙版按同一源裁切框变换。检查analysis.crop、assets/regions.json的input_frame及Validator的input_framing，不只移动预览或修改底图。已裁切区域仅允许相同裁切框复用，不同框明确拒绝；需改变构图时重新使用完整原图标注，不能补回已丢失区域。当前annotate仍以完整原图为工作画布，不直接载入已裁切的bundle。

原图与旧输出保留；新构图重新做实际目标视觉验收，旧版脸部/发梢认可不能直接转移。

## 模式与区域

默认 Lite，不调用分割模型，不将规则冒充语义识别。完全无模型：`static2live IMAGE --mode lite --no-parallax --effect dust --output OUTPUT`。保留视差需已有真实深度模型或 `--depth-map`，不能伪造深度。

绘制：`static2live annotate --input IMAGE --output ANNOTATIONS`。打开离线 index.html，选择类别、画笔/擦除，保存独立 JSON。V0.5开发编辑器还支持 Protect/Animate、撤销/重做及缩放，先读 [编辑器说明](../docs/V0.5_IMPLEMENTATION.md)。亮度/蓝色规则候选须预览调整并确认。再用 `static2live IMAGE --mode lite --no-parallax --regions SAVED_JSON --effect glow --output OUTPUT` 生成新版本。效果与区域要匹配；cloud_drift 需要 cloud，sky 不等于 cloud。

自动识别人物、天空、水面选 Smart。检查真实类别表，说明预测可能错误，人物蒙版不是精细脸部/发丝保护。缺模型报错，不自动下载或回退 Lite。首次准备须取得明确联网授权，并说明 SegFormer 使用 NVIDIA 单独许可，限非商业研究/评估，不是项目 MIT：

```powershell
static2live models prepare --kind segmentation --model-cache MODEL_DIR --accept-model-license
static2live models prepare --kind depth --model-cache MODEL_DIR
static2live IMAGE --mode smart --preset warm_portrait --model-cache MODEL_DIR --output OUTPUT
```

不需要视差可加 `--no-parallax`。生成只读本地缓存。修正：`annotate --input IMAGE --regions VERSION/assets/regions.json`，保存新 JSON，重新生成时用 `--regions`，人工同类区域覆盖预测并记录来源，不直接修改旧壁纸。

## 下载慢时换国内镜像

先使用官方源。持续缓慢或失败时停止当前下载，说明切换第三方国内镜像，沿用同一缓存和官方固定 revision，重试一次：

```powershell
static2live models prepare --kind segmentation --model-cache MODEL_DIR --accept-model-license --download-endpoint https://hf-mirror.com
```

深度准备同样支持 `--download-endpoint`。CLI 从官方元数据决定提交和预期哈希，镜像仅提供文件。不得关闭 TLS、跳过哈希或使用来源不明的权重。官方元数据不可达、哈希不符时停止报告，不用假模型/假深度替代；不得上传照片。镜像不改变许可，下载授权不等于发布授权。

## 生成与验收

1. 保留原图和旧输出，确认 CLI > YAML > Preset > 默认值。显式 `--effect` 列表替换配置效果。目标支持 web / wallpaper-engine。
2. 人像可用 warm_portrait；通用视差用 portrait_subtle / general_balanced / landscape_soft；雨雪用 rainy_city / snow_soft。人物排除须有蒙版，缺失检查 warning。单位见 README，不硬编码照片坐标。
3. 读取 analysis、motion、manifest、validation；默认分配新版本。仅用户明确要求时覆盖受管理的具体版本，说明会备份。
4. `static2live validate VERSION --browser`；浏览器不可用保留 not_tested。打开实际画面检查鼠标四角、缩放、边缘、局部效果和粒子多处分布。静态降级不是动态通过。
5. 观察通过后才 `static2live record-visual VERSION --note "实际观察"`。重新 validate 或改资源须重验；warning / failed / not_tested 如实报告，返回码不等于完整视觉验收。

视觉录入只证明已实际观察的Web画面，不证明宿主音频、性能或多屏。`record-visual`会重新生成当前结构/能力检查清单，要求同一Manifest的浏览器通过证据；旧报告缺项、未知检查或过期证据不能沿用。已有原生验收仅在Manifest相同、native-scene目标和对应观察分项一致时保留。录入后仍须读取整体状态，不因visual_acceptance单项passed就报告完整验收成功；不要手改validation.json凑齐通过。
