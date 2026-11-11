# V1完成审计：原规格对照

> 历史验收摘要来自维护者本地记录。文中 `local-acceptance/`、`output/` 和标注产物保留在本地，公开仓库提供源码与合成示例。测试结果按记录日期和所列范围解释，完整 V1 验收仍在进行。


## 当前补充（2026-10-27）

water_ripple新增独立真实生成源43ac1775…的原生局部时变、中央/外围保护、关闭/开启0%/恢复100%及边缘观察，46资源前后匹配；仅此源native_runtime及advanced_shader_runtime通过，总体not_tested。此前临时诊断记录不倒填。详情local-acceptance/native-water-observation-20261027.md。已恢复认可照片29cf3aec…运行预览，54资源匹配，无新音频或照片参数修改。

认可人像29cf3aec…新增默认设置638.583秒间歇观察：05:36:03–05:46:42 UTC，同一编辑器525516持续运行，期间无编辑器输入或参数切换；所见无黑屏/崩溃/明显面部拉伸，暖尘持续变化。54项资源匹配、原图及Manifest哈希未变。此项补齐该版本该预览尺寸的十分钟抽查，不代表精确性能或整体完成。文档源码包已重建并核对无私人素材，skill配方2 passed，详见local-acceptance/default-stability-20261027.md。

pan a590d9f4…与distortion cb08d01e…已补完实际局部时间运动、中央/外围保护、关闭、开启0%、恢复100%及四边检查，各46项原生资源前后精确一致，record-native的native_runtime及advanced_shader_runtime为passed，总体仍not_tested。六种几何原语已有各自原生对照证据，不能继续列作全部未测。详见local-acceptance/native-distortion-pan-20261027.md。结束已恢复29cf3aec…人像QA_V1运行预览，54项资源匹配，未改认可参数、未播放新音频或应用桌面。宿主音频视觉、实体多屏及其余完整V1门槛继续保留未测。

以下为本日较早记录，后续状态以上述增量为准：

旧卡住窗口已不在；从已安装主入口启动一次、刷新发现实际管理器后打开新编辑器。zoom fd9ce51d…和rotate c71f119b…各完成局部时变、中央/外围保护、关闭、开启0%、恢复100%及边缘观察；每源46项原生资源前后精确一致，分别record-native load/edges/properties/shader，native与advanced_shader分项passed，总体not_tested。详见local-acceptance/native-zoom-rotate-20261027.md。遮罩不再是当前阻碍；distortion、pan属性对照、音频视觉及原有其余V1门槛仍待验收。没有播放新声音、修改照片参数或全量重跑。

## 当前补充（2026-10-26；下表及后文保留历史快照）

pan/zoom/rotate/distortion各完成独立真实原生生成。pan a590d9f4…已实际运行并观察水平局部时变、中央/外围固定、四边填满，46资源前后一致；未做该源属性对照，不录完整通过。切换zoom fd9ce51d…时编辑器暗色遮罩无法正常退出，已停止输入并请求用户重新打开；当前未恢复照片，不谎称恢复。rotate/distortion仅结构通过。详见local-acceptance/native-geometric-observation-20261026.md，运动原语文档已同步区分证据范围。

新增float原生实测：源f8d2855c…实际局部时间位移、中央保护区/外围固定，关闭及开启0%静止，恢复100%重现，46项资源前后精确一致。仅该源record-native load/edges/properties/shader，详见local-acceptance/native-float-observation-20261026.md。其它原语不由此通过；wave已有历史独立证据。用户确认本日测试音听到，音频视觉响应仍not_tested。

本日另一次经明确授权的单次音频测试已执行，实际播放14:28:09.530–14:28:12.713 UTC，但上下文整理后采样已至14:30:58，未覆盖播放窗口。音频响应保持not_tested，不以命令成功替代真实宿主证据、不自动重播。完整时间和恢复人像记录见local-acceptance/audio-attempt-20261026.md。

最终安装包全量202 passed、无跳过。用户已明确认可29cf3aec…照片的鼠标视差、人物/头发衔接及停鼠标后的发梢轻摆，不能继续把等待这一反馈列作障碍，也不将认可挪给其它版本。原生粒子开关及开启零强度/100%对照有实际证据；subject-rigid-v2组合runtime合成网格另有真实GPU非零一致位移观察。证据分别在subject-rigid-repair-20261026.md、rigid-policy-repair-20261026.md、rigid-runtime-native-observation-20261026.md。

最终已安装包又完成一次主Agent按薄skill的真实Smart三模型CPU离线自动规划→双输出→Validator演练，新源859699ef…自动选warm_portrait且explicit_preset=false、结构passed，详情local-acceptance/v1-final-smart-flow-20261026.md。原图及用户认可源不变，新样例不替换旧壁纸、不转移视觉通过；不是独立Agent评估。原生属性/长期稳定、照片Web受限通道、宿主音频和实体多屏仍各有未验证部分，未宣布整体V1完成。

2026-10-16。原始设计规格保持不改；本表不缩减目标，不是正式V1发布声明。passed仅表示所列窄范围有证据，整体验收仍not_tested。

| 原规格 | 当前实现/证据 | 完成判断及下一动作 |
| --- | --- | --- |
| 1、5、10、39 自动分析到输出 | analyzer.py、planning.py、pipeline.py；真实CPU三模型生成v1-wallpapers照片v001，自动warm_portrait | 实现并真实生成；完整实际运行尚未通过 |
| 2、3、21、48 非视频、本地优先、可选WE | 无视频生成依赖；模型显式准备、生成离线；Lite可关闭视差无模型；原生不可用退Web测试 | 已有测试证据，不要求补MP4或云服务 |
| 4.1、8 RGB保真、统一坐标 | 规范RGB、所有区域共画布；覆盖板RGB/Alpha重算验证，test_v04/test_planning | 结构与合成证据通过；实际边缘审美需观察 |
| 4.2、4.3、16 保护与局部发梢 | FASHN/导入区域、保守保护、sway权重、编辑器；test_sway/test_v04 | 开发实现；旧v005用户认可，不能泛化新V1通过 |
| 4.4、25、26 Validator/Manifest | validator.py、browser_check.py、native记录；资源/配置/版本绑定 | 测试通过；新V1完整状态保持not_tested |
| 6 解耦Motion | 0.2/0.4/0.6契约，Renderer消费资源不重新分析 | 已实现；示例JSON版本1.0不强制旧输出改版 |
| 7、30、31 可替换模型 | DepthBackend/SegmentationBackend、真实本地模型、官方revision/license/hash | 已实现；类别覆盖有限，不能宣称text等全自动识别 |
| 9 背景补全 | 当前No Inpaint、小视差 | 规格明示可选，不凭此删减其它必需项；不宣称重建隐藏背景 |
| 11 可复用Motion Primitive | 深度、sway、ripple、drift、pulse/glow、粒子及新增float/pan/zoom/rotate/wave/distortion；primitives.py共享GLSL | 已有六种新原语Web像素与原生结构专项；原生逐个GPU运行未测，一次选择一种高级Shader，不宣称无限图层叠加 |
| 12–15 Sway/Parallax/Ripple/Pulse | sway.py、runtime.js、native_runtime.py/Shader | 合成像素/保护检查通过；宿主高级效果仍需实际控制检查 |
| 17、34 粒子与基础效果 | rain/snow/fog/dust/glow/cloud_drift；原生dust/snow/rain映射等 | 基础六类有测试；firefly/spark/stars为推荐未实现，不伪装别名支持 |
| 18 Web标准Runtime | 离线嵌入配置/纹理、WebGL、静态降级、鼠标、音频 | 合成浏览器回归；实际照片视觉受访问限制仍未测，不换工具绕过 |
| 19、20、35 原生可选Adapter | 合法模板、编译纹理、引用、保护pass、粒子和属性 | 新V1实际显示；属性开关/完整运动验收待完成 |
| 22、40 Preset | 已打包9个名称，包括anime_chill/snow_forest/cyberpunk | 真配置生成有测试；树木摇摆、Light Ray等参考效果未等价实现，需明确能力或补齐 |
| 23、42 薄skill | SKILL.md自然语言映射、CLI、分级验收、失败处理、无静默下载/覆盖 | 语法和部分调用通过；最终完整行为演练待完成 |
| 24 CLI | 快捷输入、generate、analyze、models、annotate、validate等 | 安装后任意CWD测试；旧示例合法命令保留 |
| 27、32、41 非破坏、优先级、可复现 | 原子版本分配、受控覆盖；CLI>YAML>Preset>建议>默认；哈希和依赖版本 | 128项回归包含并发/输入/覆盖/优先级；本机原图哈希未变 |
| 28、37 可视化编辑器 | Brush/Erase/Protect/Animate、撤销/缩放、原子导入、显式空蒙版 | 合成真实浏览器保存再导入通过；照片编辑体验未测 |
| 29、43、49 结构与阶段顺序 | Python包、模块、测试、README/LICENSE、薄skill和阶段文档 | 功能按阶段推进；推荐目录不逐项创建空模块，不创建远端GitHub |
| 33、44、45 V0.1及测试 | tests/test_core/test_browser，旧真实模型和浏览器记录 | 维护回归；旧成功不自动升级为新V1视觉通过 |
| 36 Human Parsing | 真实FASHN、许可、face/hair/cloth/hands，源RGB保留 | CPU真实生成完成；当前V1的时间运动仍需观察 |
| 38 Audio/Performance/Multi-monitor/Shaders | Web性能像素/帧/粒子预算、标准化viewport、真FFT、三Shader；原生音频/Shader接入 | 合成Web通过；真实宿主音频/属性和真实多屏未通过；原生性能/跨屏映射仍有unsupported |
| 46 README、47竞争力 | 已写实现/限制与路线；自动规划依据可解释 | 最终说明需与最终实际能力再核对，不用README代替验收 |

## 下一个完整门槛

1. 对当前V1源Manifest绑定实际原生属性、鼠标和发梢证据，不复制旧版本验收。
2. 处理宽比例预览裁头的适配/说明并验证；不为了“无黑边”默认为主体裁切通过。
3. 实际照片Web/编辑体验、宿主音频及真实多屏按允许渠道验证，受限就保持未测。
4. 原规格Primitive、参考Preset高级效果及原生V0.6差距逐项处理，不能靠绿色回归跳过。
5. 最终安装、skill实际端到端调用与逐项审计后，再决定是否满足完整V1。

## 新增证据与剩余区别

person-only修正版59dd68ad…最终安装包全量197 passed（227.68秒、无跳过）；源码包实际解包、六项关键文件哈希一致，skill基础有效，链接/已安装CLI配方2 passed（4.94秒）。这些证据不证明独立Agent行为或真实宿主验收。当前照片与额外音频许可问题已提交，尚未得到答复，不播放新测试音，不把整体V1标完成。详见person-only-repair-20261021.md。

person-only分支审计新增真实回归失败：无protected/sway/runtime时原生绕过人物pointer guard，已修正启用视差的person-only走保护pass。旧无policy输出保留历史契约，并只读复核一个修正前产物；实际CLI/真实资源编译生成独立合成源结构passed，未载入或播放。相关专项32 passed/1浏览器未启用skip；新wheel59dd68ad…完整回归另记，不用旧195项代替。照片当前预览不变，详见local-acceptance/person-only-repair-20261021.md。

独立primitives_subject变体已实际加载合成源6235c8fa…并运行，46资源一致，完整纹理显示，无错误色块；仅加载分项，不推定全部原语/鼠标/音频通过。结束恢复bf675498…照片运行，没有播放声音、应用桌面或发布。详见local-acceptance/subject-native-primitive-20261021.md。

2026-10-21原生高级鼠标专项新增：合成源71d59bfd…实际载入s2l_runtime_subject，左/右鼠标稳定终点观察到完整person框保持、框外近远背景响应不同，46资源精确一致。不同于只验证加载的2dd7dacf…源；不代表primitives_subject或真人边缘/属性/长期/音频通过。已恢复bf675498…照片运行，未发声/应用/发布。例程新增--subject-anchor，两个例程专项通过，完整195项历史不改写。详见subject-native-pointer-20261021.md。

新s2l_runtime_subject已在实际编辑器331734载入合成源2dd7dacf…并运行，46原生资源相同，彩色纹理/保护区域可见，无错误色块；该源视差关闭且未播声音，仅支持实际加载分项，不能证明鼠标guard或音频响应。结束恢复当前bf675498…照片Y=576运行预览，未发布。详见subject-cross-target-20261021.md新增段。

跨输出人物鼠标保护最终安装包全量195 passed、205.82秒，无跳过（subject-cross-installed-full-20261021.xml）。真实合成WebGL证明固定时间下人物内部不随鼠标分裂、背景仍响应，停鼠标后时间动画仍变化；原生新增subject变体仅有映射/实际资源编译，GPU/属性仍未验收。源码分发已包含共同模块、测试及skill路由更新，不将此记为完整V1通过。

2026-10-21后续跨输出补齐：共同pointer.py生成来源化subject guard，新Web boot与原生runtime_subject/primitives_subject以深度G通道传输，只抑制鼠标，不挪用面部效果保护或增加纹理槽。实际合成Web像素对照和原生映射专项已跑，最终G通道安装包全量回归另记；真实编译生成独立合成runtime工程结构passed，未实际加载/播放，不记宿主通过。当前照片bf675498…预览与输出保持不变，仍待反馈。详细记录local-acceptance/subject-cross-target-20261021.md，原生GPU/音频等门槛保留。

2026-10-21用户明确旧16:9发梢可见、脸不变形，但鼠标时脸发割裂，旧源连续性失败。已新增非高级runtime原生人物subject-anchored-v1分支，锁定来源化完整人物的鼠标形变、保留背景视差/发梢时变/暖尘。独立新照片源bf675498…实际生成、54原生资源精确复制并载入QA_V1运行，左右端目视无明显割裂，待用户确认；没有提升为完整通过。安装包191 passed、1环境skip；Web/高级runtime分支尚未包含此修复。用户确认听到测试音，但宿主音频响应仍未验收。详见local-acceptance/subject-pointer-repair-20261021.md。

音频标记修正版最终安装包回归189 passed、1 skipped（ASCII缓存环境）、190.75秒，audio-capability-installed-full-20261021.xml；包含合成浏览器，不是宿主音频成功。源码包已含skill排查补充、新校验与测试，版本仍0.3.0开发版。没有重播测试音或把当前照片/整体V1标通过。

该跳过项随后在显式独立 ASCII 临时缓存下补测1 passed（1.32秒），不是改写为单次190项全通过。源码包实际解包后skill有效、链接/已安装CLI工作流2 passed（4.77秒），四个关键文件与工作树哈希一致。未运行额外测试音、未变动照片；实际视觉与宿主音频的未通过状态保持。

2026-10-21重新打开当前16:9 QA_V1运行，51个原生资源与db434962…源一致。用户新授权的一次测试音已实际调用，播放期间取样未辨认明确响应，不能判通过；结束恢复照片预览。宿主给音频样例补写supportsaudioprocessing=true，现修正生成器直接按音频配置导出并增加Validator绑定检查及开/关测试。已安装修正版wheel，实际生成独立合成工程结构passed，但未运行新源的宿主音频验收。新版照片反馈、真实音频及其余门槛保留。详细证据见local-acceptance/v1-reopen-audio-20261021.md和audio-capability-repair-20261021.md；测试失败/中断如实保留，完整回归另记。

超宽屏新增实际宿主证据：同一已授权QA_V1临时载入9e308722…源，实际Y=429，51资源一致；近3440:1440面板运行中头顶轮廓/左侧留白、暖尘多处变化、鼠标四角无露空可见。不是实体超宽屏或独立preview-native窗口通过，不替代全部属性/发梢主观/性能等门槛。测试后从16:9源恢复51项一致，实际Y=576、大预览/运行/暖尘均恢复。详见local-acceptance/v1-top-framed-ultrawide-native-20261018.md；未发布，V1未完整完成。

当前16:9新版粒子属性专项另完成：实际运行中关闭→暖尘消失，恢复→出现；开启但0%提交后多帧无暖尘，恢复100%后多处暖尘再次出现。结束恢复大预览和默认值，51原生资源仍与源精确一致。详见local-acceptance/v1-top-framed-particle-properties-20261018.md。该分项通过不替代发梢/衣料/鼠标的完整属性观察或整个native_runtime；没有调用录入器伪造全通过。

2026-10-18当前16:9新版另完成默认设置长时目视检查：14:36:13–14:46:45 UTC，632秒，编辑器333668，同一Manifest db434962…；9次完整取样未见黑屏、裂缝或明显面部拉伸，暖尘持续变化，期间未切项目、重启或更改效果设置，起止51资源均与源精确相同。该窄稳定分项有证据；不将其升为精确性能、逐帧保证或完整原生验收。详细记录local-acceptance/v1-top-framed-default-soak-20261018.md。新版主观反馈、属性/精确位移、超宽屏及既有其它门槛仍保留。

2026-10-18预览尺寸修复后，新安装wheel [本地记录哈希] 完整回归188 passed / 198.78秒（v1-preview-aspect-installed-full.xml）。preview-native按画布比例请求有界窗口，不再固定3:2；宿主是否真实创建窗口仍需观察，不能由命令单测推定。超宽屏Unicode和ASCII副本命令均返回not_tested，尚无明确目标窗口证据。用户误关16:9后要求重开，已恢复新编辑器333668同一QA_V1运行、Y=576及粒子，未把误关答复当视觉认可。skill已补比例与编码排除边界，实际源码包解包校验/工作流通过；原图哈希不变，未发布。V1余下照片观感、实际超宽屏、宿主音频及既有审计门槛不被测试数量冲销。

宽屏后续恢复：新编辑器136848已打开QA_V1，实际Y=576，51原生资源与16:9源全相同。面板从约1188×558调整至992×558后头顶轮廓可见；菜单原本已选16:9，不可用菜单代替实际比例。运行中鼠标四角稳定终点未见露空、暖尘多处分布。新版构图/发梢/脸部观感尚待反馈，完整属性/固定默认长时和超宽屏实际观察未完成，不record-native完整通过。下段载入未确认是历史，不再作为当前阻塞。项目skill有效，最终工作流2 passed / 5.75秒，非独立Agent行为评估。

2026-10-18显式取景增量：用户已选择铺满、优先头顶、裁下部，不再等待构图选择。已实现推理前一致裁切并实际离线生成16:9与3440:1440两个独立版本，完整安装包测试184 passed（196.22秒）。原生QA复制一致，但编辑器同路径重新打开仍停在旧尺寸/暗色遮罩，未取得新版加载终态；构图视觉门槛仍未通过，不能以结构测试或磁盘资源相同替代。详见[输入取景](INPUT_FRAMING.md)。其它V1门槛不被冲销。

2026-10-16后续：安装包完整回归129 passed（v1-native-record-cached-regression.xml），修复record-native仅更新总项而遗漏实际启用audio/shader分项的问题；这些记录限定native-scene，不证明Web端。获用户授权复制新V1工程到Static2Live_QA_V1并完成粒子开关和零/100对照，默认已恢复，尚不完整验收。只读副本检查器新增2项专项通过，检查到编辑器对JSON的自动改写；原始资源/模型/Shader与副本内容对应须按当前差异解释，不能仅沿用初次复制哈希。发梢可辨程度已请求当前版本人工反馈，未伪造通过。原规格欠项仍不因新增这些证据而取消。

最新复核：原V1的1.5和2.5像素版均获发梢不可辨反馈；新tip-edge-v2独立版本仍待视觉确认。完整回归147 passed（153.46秒，v1-thin-skill-regression.xml）；包含新增两项skill引用完整性和真实已安装CLI配方检查，但不是独立Agent自然语言行为测试。SKILL入口已拆薄，三份参考文档及YAML示例实际列入源码包；原生/Web照片、宿主音频、多屏等未完成项不因此通过。

2026-10-17增量：已获授权使用单一Static2Live_QA_Runtime，并已使用一次低音量测试音授权。warm_glow原生开关/零强度有目视证据；高对比网格wave有局部时间变化、中央保护区、开关及零强度证据。其余原语不能由此推定通过。音频同期未观察到明确响应、是否实际听见待反馈；没有再次播放。每次QA后已恢复照片预览，记录详见local-acceptance/v1-runtime-observation.md。

同日修复record-visual沿用旧检查清单的漏洞：当前Validator清单重建，浏览器证据需同Manifest；原生能力证据还需实际native-scene输出与对应观察列表。源码8项专项通过，未以mock记录证明视觉成功。最终wheel SHA256=[本地记录哈希]，包版本仍0.3.0。完整安装包回归另记实际结果，V1整体仍未完成。

上述最终wheel完整回归：164 passed、217.63秒（v1-visual-recorder-final-installed.xml）。首次受限全量测试停在第一个浏览器用例后中断，不计成功；重试仅使用合成素材。源码包清单和原图不变已核对。通过范围限测试覆盖，不将照片、宿主音频、实体多屏或其余原生模式改为passed。

后续使用同一已安装wheel另生成float高对比网格样例，原生编辑器实际看到局部时变、外围/中央保护区保持、关闭与零强度恢复基线，详见v1-runtime-observation.md的float分项。warm_glow、wave、float目前有这些窄范围原生观察；water_ripple、neon_pulse、pan、zoom、rotate、distortion仍未完成同等宿主验证。照片已恢复运行，不以诊断幅度替换照片风格或将所有Shader改为通过。

2026-10-18整理新增共享Shader诊断：在同一float网格QA副本中切换模式，实际运行观察到pan/zoom/rotate/distortion/water_ripple局部时变及中央保护块/外围保持。neon_pulse只可靠观察色偏、保护及关闭恢复基线，呼吸时间差异仍未确认。不是独立CLI源版本的完整验收、未给源报告录入通过。已备份诊断副本并恢复测试前QA文件。恢复照片预览时发现Windows锁屏并停止操作，需解锁后继续，不能宣称本次恢复完成。用户对单次测试音回答“没注意到”，音频证据仍不足、不自动重播。详见v1-runtime-observation.md最新段落。

用户随后明确“已解锁”，照片QA_V1已在新编辑器5050648恢复运行，50项原生资源与tip-edge-v2源完全相同，仅scene.json有宿主改写。用户对该明确修正版回复“能，但幅度稍小”：发梢可辨已获得支持，幅度偏轻保留为观感，不推断未单独回答的脸部稳定。连续运行观察随后被用户物理Esc停止，未取得结束画面，10分钟门槛仍未通过。当前等待明确恢复界面操作，不再把已解除的锁屏误写成当前障碍，不自动重播音频或修改幅度。整体V1仍未完成。

后续用户明确“允许继续验收”，已恢复同一照片编辑器。本轮另获当前版本“脸部稳定”的明确反馈，解除上一段该项反馈缺失；粒子关闭/恢复实际可辨，四角无露空，发梢0/100设置后恢复默认。但默认视差响应、零强度精确静止、完整属性、宽比例适配与长期稳定不因这些窄观察自动通过，详见v1-runtime-observation.md新段。音频授权仍已用尽，不重播；V1整体尚未完成。

本轮运行观察区间07:47:15–07:57:26 UTC共611秒，期间多次实际检查同一运行预览，没有发现黑屏/报错/撕裂/明显面部拉伸，结束默认已恢复。其间包含开关和0/100操作，证据为间歇目视，不等于连续逐帧或十分钟不操作默认设置测试；精确性能、全部周期及整体V1不据此通过。

新增独立合成鼠标网格源[本地记录哈希]：实际原生编辑器检查到左右相反响应、近区域大于远区域、中央保护保持、四角不露空及关闭/开启零强度恢复基线。40个原生资源与QA副本精确一致，已仅为该源record-native load/mouse/edges/properties，native_runtime passed、整体not_tested。夹具组合9项通过，非渲染全量重跑。照片已恢复运行，照片小幅响应/宽屏适配、音频及其它既有门槛不因合成通过被冲销；详见runtime-observation。

进一步核对宽比例裁切：编辑器实际原选16:9，换4:3并复位镜头仍未取得完整头顶画面，已恢复16:9及运行预览；不能宣称切菜单即修复。Web居中cover与3:2画布在宽屏有真实构图风险，已给用户完整留边/顶端锚定裁切/暂不改的选择，待确认后才改变构图。源码分发另构建[本地记录哈希]，已含最新鼠标诊断与skill参考；未冒充V1发布。

随后新增纯色零位移霓虹合成源[本地记录哈希]，实际原生观察到局部时间亮度变化、保护保持、关闭与0%恢复基线、100%恢复效果。46资源精确一致，仅该源record-native shader/load/edges/properties通过；整体not_tested。夹具11项通过，非渲染全量回归，照片预览已恢复。此前网格只能证明色偏的记录仍按原范围保留，不倒填其全部通过。新纯色观察不证明精确周期或非零色散，也不补足宿主音频/多屏/照片门槛。
