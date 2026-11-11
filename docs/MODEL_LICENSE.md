# 模型与素材许可

> 历史验收摘要来自维护者本地记录。文中 `local-acceptance/`、`output/` 和标注产物保留在本地，公开仓库提供源码与合成示例。测试结果按记录日期和所列范围解释，完整 V1 验收仍在进行。


项目代码：MIT，见根目录 LICENSE。

V0.3 原生生成会在本地输出中复制已安装 Wallpaper Engine 的官方模板、材质与着色器。这些资产不是本项目 MIT，不随软件包分发，不自动下载，也不自动发布到创意工坊；使用/分享前须独立确认引擎资产许可。机器上编译器只执行本地纹理编译，不上传照片。

V0.2 Smart：[SegFormer B0 ADE](https://huggingface.co/nvidia/segformer-b0-finetuned-ade-512-512)，使用 [NVIDIA Source Code License for SegFormer](https://raw.githubusercontent.com/NVlabs/SegFormer/master/LICENSE)，限非商业研究/评估，不是 Apache-2.0 或项目 MIT。准备需 --accept-model-license，保留官方 LICENSE.txt、固定 revision 和文件哈希。模型预测不保证精细人像准确。

下载缓慢时显式切换 --download-endpoint https://hf-mirror.com，仍以官方元数据确定固定版本和预期哈希。元数据不可达或校验失败停止，不关闭 TLS。镜像不改变许可，不发送照片。本次真实下载使用官方源；镜像路径仅模拟验证。

默认模型：[depth-anything/Depth-Anything-V2-Small-hf](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf)。官方模型卡标注 Apache-2.0。这里只选择 Small，不能将此许可推及其他尺寸或第三方模型。

`models prepare` 记录实际下载的提交 revision、模型许可标识和 config / preprocessor / weights / README 文件 SHA-256。保留模型卡与其要求；模型权重并非本项目代码，不以 MIT 重新许可，不提交到项目仓库。使用和再分发时应自行确认官方最新条款及 Apache-2.0 的通知义务。

安装软件依赖首次需要网络，显式模型准备需要网络；生成与 Web 播放不需要网络，不发送照片。示例图由程序生成，CC0。用户照片仅本机验收，公开发布需另有图片与肖像授权，本项目未公开发布。
