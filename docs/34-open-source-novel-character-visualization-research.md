# 小说内容到角色形象：开源项目与 Skill 调研

> 调研日期：2026-08-30  
> 调研对象：从小说、故事或剧本中识别人物，形成角色视觉设定，并进一步生成一致角色图像的开源项目、Agent Skill 与相关技术。  
> 与当前项目的关系：本文是技术选型参考，不改变当前 V3 的实现顺序；当前仍优先完成 M1、N2、M2、N3 的人物外貌证据流水线。

## 1. 结论摘要

市场上较完整的方案普遍不是“把整本小说直接交给生图模型”，而是把问题拆成五层：

1. 从长文本中发现人物、称谓和相关场景；
2. 合并别名并建立角色档案；
3. 将原著事实整理成稳定、可复用的视觉描述；
4. 先生成并确认角色母版或多视角设定图；
5. 后续场景通过参考图、身份适配器、姿态控制和结果复核保持一致。

本次调研中，与当前项目最直接相关的参考是：

- `novel-characters` Skill：最适合借鉴其长文本分块、别名归并、逐字证据校验、结构化角色卡和设定图工作流；
- UpDream：最适合借鉴其“Skill + 画布 + 项目资产 + 多视角角色母版”的产品形态，但它不是开源项目，无法验证底层实现；
- CharacterGeneration：提供最小可运行的“小说 RAG + LLM + ComfyUI”端到端范例；
- Wind Comic：提供 Character DNA、Style Bible、参考图复用和视觉评分重试等工程思路；
- AutoStory、StoryDiffusion、Artikon：分别提供重型多角色生成、跨图一致性注意力、参考图与姿态控制闭环。

当前项目的主要优势是：在人物合并和图像生成之前，先建立 `exact/describe/null`、逐字证据和“每个 exact 批量判断全部 describe”的归属机制。多数同类项目缺少这一层，因此更容易把描述归错人，或者把模型补全内容误当成原著事实。

## 2. 调研范围与判断标准

本次主要比较：长文本支持、人物别名和泛称处理、原文证据、结构化角色档案、角色母版或多视角图、跨场景一致性、代码/视觉校验、人工审批、失败重试、开源程度和依赖重量。

本文只把项目官方页面、仓库 README、Skill 指令和可见源码作为实现依据。UpDream 的底层模型、特征提取方法和资产存储结构没有公开，第三方教程中的“特征数量”“像素级一致”“3D 白模”等说法不作为已验证事实。

## 3. 项目与 Skill 总览

| 项目 | 类型 | 核心路线 | 可借鉴部分 | 主要限制 |
| --- | --- | --- | --- | --- |
| [UpDream](https://www.updream.cn/) | 闭源创作平台 | 小说/剧本经 Skill 拆成美术资产，在画布上生成和复用角色、多视角与分镜节点 | Skill 工作流、可回溯画布、角色资产化、多视角母版 | 无法核对底层算法和数据结构，不可直接复用代码 |
| [novel-characters](https://github.com/eternityspring/shuohao-skills/tree/main/skills/novel-characters) | 开源 Agent Skill，Apache-2.0 | 两遍扫描长文本，归并别名，生成证据化角色卡、提示词和设定图 | 分块、证据校验、断点续跑、JSON 契约、设定图版式 | 人物归属主要依赖名称、别名与模型复核，缺少细粒度 describe 归属 |
| [CharacterGeneration](https://github.com/snorcack/CharacterGeneration) | 开源应用，MIT | 小说向量化，RAG 检索场景，LLM 生成描述，ComfyUI 出图 | 简单完整、本地模型、Provider 与工作流接口 | 外部百科可能污染原著；证据验证和身份合并较弱 |
| [Wind Comic](https://github.com/ChrisChen667788/wind-comic) | 开源短剧/漫画系统，MIT | 小说拆集、多视角图、Character DNA、Style Bible、视觉评分 | 文字锚点与参考图双保险、风格锚定、自动重试 | 系统庞大，部分模块成熟度不均，不宜整体引入 |
| [Artikon](https://github.com/HarisUmer/artikon-comic-genai) | 开源漫画原型 | 角色库、IP-Adapter、ControlNet、遮罩合成、相似度验证 | “生成—验证—重试”闭环，多人物区域化处理 | 社区和工程成熟度较低 |
| [AutoStory](https://github.com/aim-uofa/AutoStory) | 开源学术系统 | 单角色 ED-LoRA、LoRA 融合、检测分割、姿态估计、LLM 布局、区域生成 | 多角色同框、布局和姿态强控制 | Linux/CUDA 和训练依赖重，不适合早期验证 |
| [StoryDiffusion](https://github.com/HVision-NKU/StoryDiffusion) | 开源研究实现 | 扩散模型 Consistent Self-Attention | 连续漫画和长图像序列中的角色一致性 | 不负责从小说识别人和建立证据档案 |
| [Novel-to-Comic Studio](https://github.com/lhfer/codex-novel-to-comic-studio) | 开源 Codex Skill，MIT | 小说解析、Visual Bible、角色卡审批、脚本、分镜、QC | 来源追溯、资产审批、服装/阶段版本、断点续跑 | 面向完整漫画制作，超出近期范围 |
| [Novel Comic Adapter](https://github.com/cbthuodot/novel-comic-adapter) | 开源 Skill，CC BY 4.0 | 小说章节转为角色/场景 Bible、资产计划、分镜与 mock 页面 | 生产资产目录和低成本 mock 验证 | 项目较新，更偏流程模板 |

## 4. UpDream：产品层做法

UpDream 官方页面公开展示了“剧本直出美术资产”“人物多视角生成”“剧本转视频提示词”等 Skill，公开产品介绍还强调长记忆 Agent、技能库和无界画布。

从可观察能力看，其角色工作流可概括为：

```text
小说或剧本
  → Skill 拆解角色、场景、道具和固定美学
  → 在画布上形成可查看、可修改的中间节点
  → 生成角色概念图或多视角图
  → 将确认结果作为项目资产
  → 后续分镜和视频节点继续引用同一资产
```

值得学习的是三个产品设计：

1. **中间结果可见**：人物档案、角色图、分镜和视频是独立节点，可确认、修改、重跑和分支；
2. **角色从文本变成资产**：视觉形象确认后，后续任务引用稳定资产 ID 和版本，而不是只传姓名或自由文本；
3. **Skill 沉淀专业流程**：小说拆资产、角色多视角、分镜光影分别封装，既可组合也可单独执行。

UpDream 是闭源产品，因此本文不推断其是否使用 LoRA、IP-Adapter、3D 人体模型或专有身份编码。

## 5. novel-characters：最直接的开源参考

`novel-characters` 输入小说或短篇故事，输出 `cast.json`、Markdown、离线 HTML，并可选生成每个角色的设定图。

项目内已固定保存一份对照副本，来源与版本见 [references/upstream/shuohao-skills/UPSTREAM.md](../references/upstream/shuohao-skills/UPSTREAM.md)。

### 5.1 两遍处理长文本

第一遍 roster scan：

- 按段落切成带重叠的约 4 万字符 Chunk；
- 每个 Chunk 可并行识别角色名称、别名、外貌观察和逐字引文；
- 重叠区降低人物首次出现在分块边缘时被漏掉的风险；
- 单次最多 24 块，超出时显式报告 `truncated`，不静默丢弃尾部。

第二遍 profile：

- 合并同一人物在各 Chunk 中的观察；
- 默认只为重要度靠前的角色生成完整人物卡；
- 生成某个角色时同时提供同批其他角色的名字，减少人物外观和声音趋同；
- 分别输出人物画像、图像提示词、负面提示词、风格标签和音色提示词。

### 5.2 别名归并

姓名和别名建立在同一个索引中。完全匹配可确定性归并；“陆”与“陆行远”之类包含关系只生成 `mergeCandidates`，需要模型或人工复核，避免同姓父子、兄弟被误合并。

该方法适合明确名称和称谓，但对“红衣女子”“月袍老人”仍然较粗。当前项目的 `exact/describe/null` 和逐 exact 批量 describe 解析能提供更强的局部证据归属。

### 5.3 原文证据和确定性校验

Skill 要求证据必须是小说原文中的连续逐字片段，并由脚本检查。其他硬校验包括：

- 引文必须逐字存在于源文件；
- 生图提示词不能包含人物名、作者名或作品名，避免图像模型调用固有训练记忆；
- 人类字段使用报告语言，图像/TTS 机器提示词保持英文；
- 画风与负面提示词不能互相矛盾；
- 枚举和 JSON 结构满足 Schema。

项目提供 355 项不调用模型的自测，覆盖分块、归并、合成、多语言、校验和渲染。

### 5.4 角色设定图

每个人物生成一张 16:9 横向设定图：

```text
┌────────────┬────────────────────────────┐
│            │   正视    侧视    背视       │
│  面部半身像 ├────────────────────────────┤
│  约 34%    │   关键细节特写条             │
└────────────┴────────────────────────────┘
```

左侧半身像是面部设计基准；右上三视图用于身材、服装和比例；右下保留饰品、伤疤、纹理等细节。每个角色单独调用生图，断点续跑时跳过已有文件。

### 5.5 对当前项目的价值

建议把它作为对照实现和评测基线，而不是替代当前流水线。最值得复用的是重叠分块、显式截断、逐字校验、自动归并与人工复核分离、机器/人类字段分离、单角色可恢复出图、确定性自测和失败定位。

## 6. CharacterGeneration：最小端到端应用

CharacterGeneration 使用 FastAPI、LangChain、ChromaDB、HuggingFace Embedding、Ollama 和本地 ComfyUI：读取小说并建向量索引，识别主要人物，检索相关外貌和场景片段，让 LLM 生成角色描述，再将提示词注入 ComfyUI API workflow。

它证明了“小说 RAG → LLM → ComfyUI”可以用较少模块跑通，但也暴露了常见问题：

- 向量相似度适合召回相关场景，不等于能解决称谓与人物归属；
- Wikipedia 等外部增强可能把影视改编或百科设定混入原著事实；
- 没有展示与当前 N2/N3 类似的逐字证据和归属校验；
- 真实演员作为视觉基底会引入肖像、版权和固有形象偏差。

因此，RAG 可以作为长文本召回层，但不能取代当前的证据校验和局部人物解析。

## 7. Wind Comic：Character DNA 与视觉闭环

与本项目相关的设计主要有四项：

1. **Character DNA**：用视觉模型从设定图中抽取眼型、下颌、发型、标志性服装等结构化特征，再把同一文字锚点注入每个镜头；
2. **多视角设定图**：正面、四分之三侧面、正侧面和背面使用同一 DNA、服装、比例和一致性约束；
3. **Style Bible**：先生成标准风格帧，再作为后续分镜的风格参考，降低画风、光照和材质漂移；
4. **视觉审核与重试**：视觉模型评分不合格时提高参考权重重新生成。

参考图与结构化文字锚点双重存在，比单独依赖其中一种更稳定。其“生成结果也是待校验提案”的思想与当前项目的模型提案—代码验证结构一致。

Wind Comic 功能面很大，部分代码仍保留阶段性“后续接线”描述。适合借鉴数据结构和闭环，不适合整体作为依赖引入。

## 8. 图像一致性技术层

### 8.1 IP-Adapter

[IP-Adapter](https://github.com/tencent-ailab/IP-Adapter) 将参考图编码为图像提示，通过轻量适配器注入扩散模型，同时保留文字控制。官方实现提供 Face、FaceID、Plus 和 ControlNet 组合方式，并支持 ComfyUI。

它适合在已有角色母版后生成不同姿势和场景。参考权重过高会让构图过度接近原图，过低则身份漂移；虚构角色的服装和全身特征仍需文字锚点或额外参考。

### 8.2 InstantID 与 PhotoMaker

[InstantID](https://github.com/instantX-research/InstantID) 和 [PhotoMaker](https://github.com/TencentARC/PhotoMaker) 主要解决真人或类真人面部身份保持，均支持无需为每个人训练 LoRA 的快速定制。

它们适合半写实真人角色和面部近景，但身份一致不等于服装、体型、配饰和全身轮廓一致；纯动漫、非人类或高度风格化角色可能需要其他适配器或 LoRA。

### 8.3 ControlNet

ControlNet 用姿态、深度、边缘或分割图约束构图和动作。它解决“人站在哪里、做什么姿势”，不直接解决“这个人是谁”。生产流程通常将身份参考和姿态控制组合使用。

### 8.4 LoRA

LoRA 适合角色设计已经确认、需要大量镜头和变化的阶段。AutoStory 为每个角色训练 ED-LoRA，再融合多角色 LoRA，用区域控制生成多人画面。

LoRA 需要准备数据、训练和版本管理。如果母版仍在变化，过早训练会固化错误设计，因此不建议作为第一种出图方式。

### 8.5 StoryDiffusion

StoryDiffusion 通过 Consistent Self-Attention 在连续生成图之间共享人物信息，适合漫画或长分镜序列。它可以作为序列增强层，但仍需要上游提供可靠角色设定和场景提示词。

## 9. 建议的目标架构

```text
M1：识别 exact / describe / null，并归拢原文证据
  ↓
N2：逐字存在性、位置、哈希和结构校验
  ↓
M2 / N3：拆解外貌事实，确定 describe 片段归属
  ↓
Character Memory：local_character_ref → character_id
  ↓
Appearance Profile：原文事实、推断设计、服装阶段和冲突版本
  ↓
Prompt Compiler：身份锚点 + 阶段服装 + 场景变化 + 风格 + 负面约束
  ↓
Character Master：面部基准、全身多视角、关键细节，人工确认
  ↓
Reference Generation：身份参考 + 姿态控制 + 场景提示词
  ↓
Visual Validator：身份、服装、风格和构图验收，不合格重试
```

### 9.1 Appearance Profile 建议分层

- `grounded_facts`：来自 N3 的原文外貌事实，每项保留证据和位置；
- `inferred_design`：根据时代、地域、职业补全的视觉信息，明确标记为推断；
- `adaptation_design`：为视觉辨识度增加的创作设计，不冒充原著事实；
- `appearance_stages`：少年/成年、受伤前后、伪装等阶段；
- `outfit_versions`：服装和装备版本；
- `conflicts`：原文矛盾描述，不静默覆盖；
- `visual_identity`：稳定身份锚点、负面约束和已批准参考资产。

### 9.2 角色资产元数据

每个确认母版建议记录：

- `character_id`、`appearance_profile_version`、`reference_asset_id`；
- 正面、侧面、背面、半身和细节图；
- Prompt、Negative Prompt 和风格预设版本；
- Provider、模型版本、seed 和生成参数；
- 输入证据包哈希和输出图像哈希；
- `draft/approved/rejected/superseded` 状态；
- 人工修改说明和批准时间。

### 9.3 Prompt Compiler

提示词不要由每个任务自由重写，建议按稳定模块编译：

```text
固定身份块
+ 当前外貌阶段
+ 当前服装版本
+ 本镜头动作、表情和环境变化
+ 全局画风与光照
+ 负面约束
```

人物姓名只作为系统内部 ID；真正交给图像模型的是视觉描述和参考资产，避免知名人物名字触发模型的固有训练记忆。

## 10. 分期落地建议

### 阶段 A：当前 M1/N2

- 继续按现有 Schema 实现，不引入向量库和图像生成；
- 加入重叠分块策略和显式 `truncated` 状态；
- 保持逐字引文、位置和哈希的确定性校验；
- 为分块边界、同名不同人、名字加泛称、纯 describe 等情况建立测试。

落地状态：前三项已进入 V3 `3.4.0-draft1` 技术契约；其中 `DocumentChunkManifest` 负责证明处理范围，N2/M2/N3 的多层 span 负责证明证据来源。当前仍只完成契约与 Schema，Manifest 校验器和自动化测试属于下一步实现工作。

### 阶段 B：M2/N3 与人物记忆

- 完成每个 exact 携带全部 describe 的归属和片段消费；未被 exact 消费的 describe 单独进入 M2，可建立一个或多个新的本地正式人物；
- 再设计跨 Chunk `local_character_ref → character_id`；
- 自动归并和人工/模型复核分开，不把包含关系直接当作同一人物；
- 不使用 Wikipedia 等外部信息作为原著人物事实来源。

### 阶段 C：视觉档案和母版

- 增加 `AppearanceProfile` 与版本管理；
- 建立 Prompt Compiler 和少量风格预设；
- 每个角色一次生成标准设定图；
- 人工确认后才建立可复用角色资产。

### 阶段 D：跨场景生成

- 第一版优先接 ComfyUI 或抽象 Image Provider；
- 使用角色母版配合 IP-Adapter 或同类参考图能力；
- 姿态/构图另用 ControlNet，不把身份和姿态混成一个参数；
- 保存全部生成参数，支持单角色、单镜头重跑。

### 阶段 E：视觉验收

- 先实现人工接受/拒绝；
- 再增加视觉模型对人物、服装和风格的分项评分；
- 阈值不通过时只重跑失败镜头；
- 保留自动评分和人工最终判断的差异。

### 阶段 F：规模化生成

- 角色和画风稳定后再评估 LoRA；
- 多人物同框需要区域身份控制、遮罩或区域合成；
- 连续漫画/视频再评估 StoryDiffusion 类跨帧一致性；
- 最后才考虑类似 UpDream 的画布和完整短剧生产链。

## 11. 推荐 Skill

### 11.1 优先研究：novel-characters

```bash
npx skills add https://github.com/eternityspring/shuohao-skills --skill novel-characters
```

建议用其样例和输出作为对照基线，复用或改写确定性校验和自测思想，并比较两种方案在人物召回、别名合并、证据准确率和外貌提示词质量上的差异。

不建议直接用它替换当前 M1–N3，因为当前项目对 describe 归属和证据片段消费的定义更严格。

### 11.2 完整漫画阶段：Novel-to-Comic Studio

```bash
npx skills add https://github.com/lhfer/codex-novel-to-comic-studio
```

适合以后研究 Visual Bible、角色服装阶段、审批 Gate、`source_span` 和成品 QC；当前阶段不需要引入整套漫画流水线。

### 11.3 暂不优先：character-design-sheet

[character-design-sheet](https://www.skills.sh/inference-sh/skills/character-design-sheet) 可以通过 inference.sh CLI 生成一致角色设定图，但公开安装量较低，依赖外部服务，skills.sh 页面还显示部分安全扫描警告。现阶段使用内置图像能力或自建 ComfyUI Provider 更容易控制数据和版本。

## 12. 建议的评测指标

为了避免只比较“哪张图更好看”，建议分层评测。

### 文本与证据层

- 人物提及召回率；
- exact/describe/null 分类准确率；
- 引文逐字存在率；
- describe 归属准确率；
- 跨 Chunk 人物合并准确率；
- 原著事实、推断和改编设计的混淆率。

### 角色档案层

- 外貌事实覆盖率；
- 同一字段冲突是否被保留；
- 提示词是否包含无证据事实；
- 不同人物的视觉区分度；
- 时代、地域和服装设定是否自洽。

### 图像层

- 正面、侧面和背面的身份一致性；
- 脸型、发型、体型、服装、配饰分别的一致性；
- 角色与原文事实的一致性；
- 跨场景画风一致性；
- 姿态和构图服从度；
- 人工接受率、平均重试次数和单张成本。

## 13. 最终建议

当前不应把项目直接扩成“小说一键出图”或完整 UpDream 替代品。更稳妥的路线是：

1. 先把现有 V3 做成可靠的小说人物外貌事实层；
2. 用 `novel-characters` 验证分块、人物清单和角色卡产出方式；
3. 在人物记忆完成后设计版本化 Appearance Profile；
4. 先生成并人工确认角色母版；
5. 再使用参考图适配器和姿态控制生成场景；
6. 最后补视觉验收、重试和资产工作台。

这样既保留当前项目在证据追溯和人物归属上的优势，又能逐步吸收 UpDream、开源 Skill 和一致性图像项目中已经被验证的做法。

## 14. 主要资料

- UpDream 官方网站：[https://www.updream.cn/](https://www.updream.cn/)
- shuohao-skills / novel-characters：[GitHub](https://github.com/eternityspring/shuohao-skills/tree/main/skills/novel-characters)
- novel-characters 项目内固定副本：[来源与版本](../references/upstream/shuohao-skills/UPSTREAM.md)
- CharacterGeneration：[GitHub](https://github.com/snorcack/CharacterGeneration)
- Wind Comic：[GitHub](https://github.com/ChrisChen667788/wind-comic)
- Artikon：[GitHub](https://github.com/HarisUmer/artikon-comic-genai)
- AutoStory：[GitHub](https://github.com/aim-uofa/AutoStory)
- StoryDiffusion：[GitHub](https://github.com/HVision-NKU/StoryDiffusion)、[项目主页](https://storydiffusion.github.io/)
- Codex Novel-to-Comic Studio：[GitHub](https://github.com/lhfer/codex-novel-to-comic-studio)
- Novel Comic Adapter：[GitHub](https://github.com/cbthuodot/novel-comic-adapter)
- IP-Adapter：[GitHub](https://github.com/tencent-ailab/IP-Adapter)
- InstantID：[GitHub](https://github.com/instantX-research/InstantID)
- PhotoMaker：[GitHub](https://github.com/TencentARC/PhotoMaker)
