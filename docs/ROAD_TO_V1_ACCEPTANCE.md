# 到V1.0的完成审计清单（目标不缩减）

> 历史验收摘要来自维护者本地记录。文中 `local-acceptance/`、`output/` 和标注产物保留在本地，公开仓库提供源码与合成示例。测试结果按记录日期和所列范围解释，完整 V1 验收仍在进行。


2026-10-27增量：六种几何原语的各自原生局部运动、保护区、关闭/开启零强度/恢复默认与边缘观察已完成，当前源和范围见MOTION_PRIMITIVES.md。实际照片29cf3aec…的用户认可继续有效，恢复预览后54项资源精确一致。音频响应仍待单次新测试授权，不复用已消耗授权；实体多屏和受限照片Web等门槛未解除。下文保留历史过程，不把已完成项重复列作当前障碍。

2026-10-26用户随后针对当前照片29cf3aec…的鼠标可见性、人物/头发衔接及停鼠标后的发梢轻摆明确回复“一切正常，完美”。该版本这三项主观视觉已获认可，解除等待此反馈的阻碍，不再盲调参数。音频、实体多屏、照片Web通道及其余完整验收仍需各自证据，不能据此宣布整个V1完成。版本绑定记录见local-acceptance/subject-rigid-repair-20261026.md。

2026-10-26后续：原生策略名按真值选择导致未知值静默冻结/禁用，以及Shader替换未命中无报错，新增5项回归已先复现后修复。最终安装包全量202 passed、0 skipped（rigid-policy-installed-20261026.xml）。原生当前照片补做粒子开启且强度0→100实际对照，恢复默认后资源仍精确一致。详见local-acceptance/rigid-policy-repair-20261026.md；不将此记为音频、主观鼠标、多屏或完整V1通过。

2026-10-26最新核对：subject-anchored-v1被用户判为鼠标效果不可辨，当前subject-rigid-v2改为人物统一非零位移。安装后全量197 passed、无跳过（rigid-v2-full-final-20261021.xml）；旧的16:9、冻结版及当前版只读结构复核均passed，不修改旧文件。当前照片Manifest为29cf3aec…，QA_V1的54资源与源完全一致并重新进入原生编辑器运行。左上/右下稳定帧未见露空，粒子可辨；新版本主观视差/衔接仍须反馈，完整属性与长期稳定未录入通过。一次额外音已播放，但截图早于实际播放、未覆盖同期，宿主音频不通过记录。详见local-acceptance/subject-rigid-repair-20261026.md。以下历史证据不冲销这些未测项，V1整体未完成。

依据原始Static2Live_Skill_最终设计规格_Codex版.md，目标保持V0.3验证、V0.4及后续直到完整V1.0 skill。此为待办与证据索引，不是完成声明。原文的可选/推荐项不擅自改为硬性，必需项也不因已有测试容易通过而删减。

| 范围 | 当前权威来源 | 已知未完成 / 下一证据 |
| --- | --- | --- |
| V0.1包、CLI、真实深度、Schema、版本化输出、Preset、Manifest、Validator | src/static2live，tests/test_core.py，V0.1_IMPLEMENTATION.md | 维护跨版本回归；旧记录不充当新版本视觉证据 |
| V0.2 Lite/Smart、区域与六种效果、明确模型准备 | tests/test_v02.py，V0.2_IMPLEMENTATION.md，模型缓存记录 | 每次实际样例复核区域与来源；不能用规则假扮语义模型 |
| V0.3原生Adapter与优先映射 | wallpaper_engine.py，V0.3_ACCEPTANCE.md，V0.3_IMPLEMENTATION.md | 保留旧失败/修复与属性警告；最终版本需实际加载、鼠标、边缘、粒子和开关验收 |
| V0.4人物解析、发梢/衣料、保护 | human_parser.py，sway.py，test_v04.py，V0.4_IMPLEMENTATION.md | v005用户确认脸稳定、发梢轻摆；实际Web视觉未测，不能泛化为所有版本通过 |
| V0.5可视化编辑 | editor.py，web/editor.*，test_v05.py，V0.5_IMPLEMENTATION.md | 合成功能和保存再导入通过；实际照片编辑体验仍未测 |
| V0.6音频、性能、多屏、Shader | runtime_options.py，web/audio.js，web/runtime.js，native_runtime.py，test_v06.py，test_native_v06.py，V0.6_IMPLEMENTATION.md | Web合成功能实测；原生音频/Shader已接入且合成工程实际加载，属性与宿主音频仍未完整验收；原生性能/跨屏映射及真实多屏未完成 |
| V1.0自动分析→推荐→规划→双目标→验证→Manifest | analyzer.py，planning.py，test_planning.py，V1.0_IMPLEMENTATION.md | 开发接口和真实CPU三模型自动生成已实现；128项安装包回归通过。当前照片自动选择warm_portrait，不是手选Preset。实际原生加载/粒子已有新观察；属性、发梢及完整跨目标验收仍未完成 |
| 最终skill | SKILL.md，skill-creator校验 | 需要完成版本能力路由、自然语言映射、错误反馈和最终真实调用；基础语法通过不是完整行为验收 |
| 可复现与非破坏 | manifest资源/模型哈希，tests各版本，输出目录 | 最终安装、任意工作目录、输入哈希、新版本与覆盖安全都要复核，不发布/不上传/不清理既有文件 |

最终完成前需逐项核对原规格所有明确要求及交付物，检查代码、安装包、真实生成与实际渲染，不以本表或绿色测试代替。未测项保持not_tested；参考Preset的高级效果需逐个检查是否实现或是否仅建议，不用静默删减达成“V1.0”。

当前不满足完整完成条件，goal应保持active。Web实际照片页面工具访问限制继续遵守，不能换协议/换工具绕过；可继续实现和合成回归，实际视觉需获得允许的直接观察或用户对明确版本的反馈。

最新增量：安装包145项回归通过（v1-tip-edge-regression.xml），新增有界局部原语见MOTION_PRIMITIVES.md。原V1的1.5和2.5像素样例均获发梢不可辨反馈，不能算通过。独立tip-edge-v2权重修正版已生成并实际进入编辑器运行，仍待新版本反馈，不把旧v005或测试通过挪来充当可辨通过。

Skill入口已由9166字符缩为1714字符，详细生成/原生QA/开发能力分别放在references下；保留失败、镜像、授权及证据规则，源码分发补齐参考文档与YAML样例。新增两项链接/CLI配方专项通过，不等于独立Agent行为测试或最终完整V1验收。

最新完整回归147 passed（153.46秒，v1-thin-skill-regression.xml）。源码包清单已确认三份references及v06_runtime.yaml存在，Skill基础校验通过。旧v005、旧2.5修正版及新tip-edge-v2的只读结构复核均passed，未改写旧产物，也未将结构结果转成视觉通过。

后续完整150项回归通过（159.25秒），新增原生QA夹具的3项验证已纳入。按OS报告的横屏+偏移竖屏/负原点/空隙布局追加1项Chromium裁切专项通过（16.04秒）；不混写成151项全量测试，也不当成实体多屏验收。原生新增运行时测试目录及短音频授权待答复，当前照片tip-edge-v2仍待实际可辨性反馈。

2026-10-16更新：完整需求核对见V1_REQUIREMENT_AUDIT.md；新V1样例的原生观察单独记录在local-acceptance/v1-native-observation.md。旧v005人工反馈不挪用于新样例。preview命令成功、编译成功、合成测试和截图观察分别记账。
