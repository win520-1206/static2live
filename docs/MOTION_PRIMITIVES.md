# 有界局部运动原语（开发验收）

> 历史验收摘要来自维护者本地记录。文中 `local-acceptance/`、`output/` 和标注产物保留在本地，公开仓库提供源码与合成示例。测试结果按记录日期和所列范围解释，完整 V1 验收仍在进行。


原规格第11节的float、pan、zoom、rotate、wave、distortion已接入现有shader配置，并复用同一GLSL函数生成Web及原生资源。不是新增视频渲染器，也不会自动给人脸或全图开启这些运动。已有parallax、hair/cloth sway、water_ripple、cloud_drift、warm_glow/neon_pulse及粒子继续使用各自接口。

```yaml
shader:
  preset: float
  amplitude_px: 1
  strength: 0.5
  period_seconds: 8
```

六种新原语都要求已确认非空other区域，缺失即拒绝。可以用annotate手画或导入明确蒙版，不凭照片颜色猜运动区域。protected区域扣除后完全不参与采样位移；若未提供保护区，不宣称自动保护人物。

| 名称 | 实际行为 |
| --- | --- |
| float | 椭圆式轻浮动，x/y不同幅度，根随区域权重过渡 |
| pan | 周期性水平局部平移，不是整幅镜头持续滑走 |
| zoom | 以规范画布中心为基准的局部小幅缩放场 |
| rotate | 小角度旋转形变场，不是骨骼或完整刚体图层旋转 |
| wave | 随纵坐标错相的水平正弦波 |
| distortion | x/y不同空间频率的低强度二维UV形变 |

坐标统一为画布归一化、底部原点；每轴单位位移有界[-1,1]，再乘amplitude_px、strength、区域权重，并按画布宽高归一化。原生坐标翻转和宽高比在Adapter处理，不通过改变源蒙版修正。幅度上限仍4画布像素且不超过短边1%；overscan累加最坏位移；period_seconds为完整循环周期。

Web与原生共享primitives.py中的GLSL函数。旧原生s2l_runtime.vert/.frag不改，新原语独立输出s2l_primitives资源；Validator复核函数生成文本、参数、aspect、纹理和保护。已有旧工程不因新增原语而修改文件。当前shader字段一次选择一种高级原语；可与现有深度、人物微摆、粒子和显式音频组合，不宣称任意多层关键帧系统。

开发测试：tests/test_primitives.py的12项专项通过，包括六种真实WebGL时序帧差、保护/外区不变、首尾循环、零幅度、关闭与减少动态、透明边缘，以及六种原生结构/宽高比绑定。它们不等于原生实际GPU验收。

原生证据截至2026-10-27：六种原语各有独立局部时变、保护区/外围稳定、关闭与开启但0%对照，以及恢复默认强度和边缘观察。pan和distortion增量见local-acceptance/native-distortion-pan-20261027.md；每源46项原生资源精确匹配。此前zoom遮罩阻挡已在新编辑器复验解除。这里的通过仅覆盖各合成源的原生Shader，不代表照片、音频或整体V1验收通过。继续验收应先核对[原规格审计](V1_REQUIREMENT_AUDIT.md)的最新增量及对应Manifest，不重复把已验证的局部项当缺失，也不将其它模式的通过挪给未测源。
