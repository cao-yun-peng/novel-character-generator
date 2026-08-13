# 小说角色插画与3D建模生成器 — 最终技术文档

## 目录

- [1 项目概述](#1-项目概述)
- [2 系统架构设计](#2-系统架构设计)
- [3 技术栈选型](#3-技术栈选型)
- [4 项目目录结构](#4-项目目录结构)
- [5 数据模型设计](#5-数据模型设计)
- [6 核心模块详解](#6-核心模块详解)
  - [6.1 配置层 (config/)](#61-配置层-config)
  - [6.2 API层 (api/)](#62-api层-api)
  - [6.3 文本理解层 (core/text/)](#63-文本理解层-coretext)
  - [6.4 2D生成层 (core/image/)](#64-2d生成层-coreimage)
  - [6.5 3D生成层 (core/model3d/)](#65-3d生成层-coremodel3d)
  - [6.6 流水线编排 (core/pipeline.py)](#66-流水线编排-corepipelinepy)
  - [6.7 模型提供商抽象 (models/)](#67-模型提供商抽象-models)
  - [6.8 数据层 (data/)](#68-数据层-data)
  - [6.9 工具层 (utils/)](#69-工具层-utils)
- [7 核心算法设计](#7-核心算法设计)
- [8 Prompt工程](#8-prompt工程)
- [9 3D生成层接口预留](#9-3d生成层接口预留)
- [10 配置管理](#10-配置管理)
- [11 开发计划与里程碑](#11-开发计划与里程碑)
- [12 成本估算](#12-成本估算)

---

## 1 项目概述

### 1.1 项目目标

从百万字级中文小说中自动提取角色核心特征，生成高质量角色插画（PNG/JPEG），并预留3D模型生成接口（OBJ/FBX/STL），同时输出结构化角色特征摘要。

### 1.2 核心价值

市面上不存在端到端的"小说文本→角色插画→3D模型"完整管线产品。文本角色提取工具不输出可驱动视觉生成的结构化特征；2D插画技术虽成熟但缺乏文本到图像的自动化衔接；3D角色生成尚在快速进化中。本项目的核心壁垒在于构建三层之间的胶水层：文本理解→2D生成→3D生成的完整自动化管线。

### 1.3 设计原则

- **80%复用 + 20%自研**：最大化利用云端API和开源组件，自研精力集中在四层记忆体系、特征Schema设计、特征到视觉参数的映射、一致性检查等胶水层
- **四层记忆驱动**：通过四层记忆体系实现百万字小说的增量处理，每个分块仅1.2万字，无需大上下文窗口的LLM，普通云端API即可胜任
- **全云端API**：LLM和图像生成全部使用云端API（DeepSeek API + fal.ai），无需本地部署任何模型，任意联网电脑即可运行
- **增量处理**：支持小说内容的增量输入，不丢失已抽取的人物特征和关系，支持断点续传
- **3D接口预留**：3D生成层本期仅定义接口和数据结构，不实现具体逻辑

### 1.4 硬件适配

任意联网电脑即可运行，无需GPU、无需本地部署任何模型。LLM使用DeepSeek API（OpenAI兼容格式，国内直连），图像生成使用fal.ai云端API。四层记忆体系确保每次只向API发送1.2万字分块，兼顾处理质量和API调用成本。

---

## 2 系统架构设计

### 2.1 四层分层架构

系统采用四层分层架构，各层职责清晰、单向依赖：

```
┌─────────────────────────────────────────────┐
│              API 层 (api/)                    │
│   FastAPI 路由 / 请求响应模型 / WebSocket     │
├─────────────────────────────────────────────┤
│            业务层 (core/)                     │
│   文本理解 / 2D生成 / 3D生成(接口) / 流水线   │
├─────────────────────────────────────────────┤
│            模型层 (models/)                   │
│   LLM Provider / ComfyUI / 数据Schema        │
├─────────────────────────────────────────────┤
│            数据层 (data/)                     │
│   SQLite / 数据访问对象 / 迁移脚本            │
└─────────────────────────────────────────────┘
```

- **API层**：接收HTTP请求，参数校验，调用业务层，返回结果。不包含任何业务逻辑。
- **业务层**：核心处理逻辑。文本理解层负责角色特征提取，2D生成层负责插画生成，3D生成层预留接口，流水线模块负责编排三层协作。
- **模型层**：封装所有外部模型调用。通过Provider抽象层统一LLM接口（OpenAI兼容格式），封装ComfyUI工作流调用，定义数据Schema。
- **数据层**：SQLite数据库管理，提供数据访问对象（Repository模式），处理数据持久化。

### 2.2 三层处理流水线

```
小说文本
    │
    ▼
┌──────────────────┐
│  文本理解层       │  LangGraph 多Agent编排
│  (core/text/)    │  → 角色识别 / 特征提取 / 关系建模
│                  │  → 输出: CharacterFeatureSchema JSON
└────────┬─────────┘
         │ CharacterFeatureSchema
         ▼
┌──────────────────┐
│  2D生成层         │  ComfyUI 工作流
│  (core/image/)   │  → 特征→Prompt映射 / 四视图生成
│                  │  → InstantID一致性 / CLIP-I校验
│                  │  → 输出: PNG/JPEG 角色插画
└────────┬─────────┘
         │ 角色插画 + 特征JSON
         ▼
┌──────────────────┐
│  3D生成层(预留)   │  接口已定义，实现待定
│  (core/model3d/) │  → 输入: 2D插画 + 特征JSON
│                  │  → 输出: OBJ/FBX/STL (下次实现)
└──────────────────┘
```

### 2.3 LangGraph 编排策略

文本理解层使用 LangGraph 而非自研框架，原因如下：

- **循环迭代**：角色特征需跨章节增量累积，天然需要循环结构
- **条件分支**：不同角色重要度（主角/配角/路人）走不同提取深度
- **人工审核节点**：关键角色特征提取后可暂停等待用户确认
- **并行处理**：多角色可并行提取特征
- **状态持久化**：LangGraph 自动保存 checkpoint，支持断点续处理
- **可观测性**：集成 LangSmith 后可追踪每步Agent决策

LangGraph 负责编排层（Agent路由、分支、循环），自写代码负责计算层（文本分块、实体扫描、特征合并等纯函数操作）。当日处理小说量超过100部时，可考虑自研框架替代。

---

## 3 技术栈选型

### 3.1 技术栈总览

| 层级 | 技术 | 用途 | 复用/自研 |
|------|------|------|-----------|
| Web框架 | FastAPI | API服务 | 复用 |
| 编排框架 | LangGraph | 文本理解层Agent编排 | 复用 |
| LLM（云端） | DeepSeek API | 文本理解、角色特征提取（OpenAI兼容，国内直连） | 复用 |
| 四层记忆体系 | 自研 MemoryManager | 增量处理百万字小说，每块1.2万字，控制API成本 | 自研 |
| 图像生成（云端） | fal.ai (云端ComfyUI) | 角色插画生成，FLUX/SD模型 | 复用 |
| 一致性控制 | InstantID / PuLID | 零样本角色一致性 | 复用 |
| 姿态控制 | ControlNet Union Pro 2.0 | 四视图姿态引导 | 复用 |
| 一致性评估 | CLIP-I score | 角色插画一致性量化检查 | 复用 |
| 数据库 | SQLite | 数据持久化 | 复用 |
| ORM | SQLAlchemy | 数据库操作 | 复用 |
| 3D生成 | Tripo / 待定 | 3D模型生成（接口预留） | 待定 |

### 3.2 LLM Provider 抽象

所有LLM调用统一使用 OpenAI 兼容格式编写，通过修改`.env`配置即可切换Provider。本项目选用 DeepSeek API 作为主力LLM，原因如下：

- **国内直连**：DeepSeek API 服务器在国内，无需中转或代理
- **中文理解强**：DeepSeek-V3 在中文NLP任务上表现优秀
- **价格极低**：$0.14/M input tokens, $0.28/M output tokens，远低于同类模型
- **OpenAI兼容**：直接使用 openai SDK 调用，迁移成本为零
- **四层记忆配合**：每块仅1.2万字（约8K tokens），DeepSeek的64K上下文窗口绰绰有余，同时记忆体系注入的已知角色信息约2-4K tokens，总token消耗控制在12K以内

如需切换其他OpenAI兼容的LLM服务（如通义千问API、Moonshot/Kimi API等），只需修改`.env`中的`LLM_BASE_URL`和`LLM_API_KEY`，业务代码零改动。

### 3.3 开源/借鉴/自研分类

**可直接使用的开源组件和云端API（约500行集成代码）：**
- LangGraph：Agent编排框架
- DeepSeek API：云端LLM（OpenAI兼容格式，国内直连）
- fal.ai Python SDK：云端图像生成（云端ComfyUI，支持FLUX/SD模型）
- InstantID / PuLID：零样本角色一致性节点（通过fal.ai云端运行）
- ControlNet Union Pro 2.0：姿态控制节点（通过fal.ai云端运行）
- jieba：中文分词，用于实体预扫描

**借鉴设计但需重写的部分（约500行代码）：**
- 中文别名合并算法（借鉴 AI Reader V2 思路，不复制代码，注意AGPL协议）
- 中文小说特征抽取Prompt（借鉴 largeliterarymodels 的Prompt结构）
- 图像Prompt规范（借鉴 chorus-engine 的image prompt specification）

**必须自研的核心壁垒（约3000行代码）：**
- 四层记忆体系（MemoryManager）— 核心中的核心，使百万字小说可通过1.2万字分块增量处理，控制API成本
- Prompt管理系统（PromptManager）— 数据库+文件双源架构，支持线上热修改和版本回滚，借鉴 llm-rag-server 设计
- 身份原型管理系统（PrototypeManager）— 与 PromptManager 同构，支持 variability 驱动的差异化填充策略和 LLM 自动生成兜底
- 角色视觉特征Schema（CharacterFeatureSchema）
- 特征→fal.ai参数映射器（FeaturePromptMapper）
- CLIP-I一致性检查器（ConsistencyChecker）
- 身份原型优先级覆盖逻辑（IdentityPrototypeResolver）
- LoRA训练编排（v2功能，MVP阶段不实现）
- 3D生成层接口（本期仅定义接口）

---

## 4 项目目录结构

```
novel-character-generator/
├── api/                            # API层
│   ├── __init__.py
│   ├── main.py                     # FastAPI 应用入口
│   ├── deps.py                     # 依赖注入
│   ├── routes/                     # 路由模块
│   │   ├── __init__.py
│   │   ├── novels.py               # 小说管理路由
│   │   ├── characters.py           # 角色管理路由
│   │   ├── images.py               # 图像生成路由
│   │   ├── models3d.py             # 3D模型路由(接口预留)
│   │   ├── pipeline.py             # 完整流水线路由
│   │   ├── prompts.py              # Prompt管理路由(线上修改/回滚/预览)
│   │   └── prototypes.py           # 身份原型管理路由(线上修改/回滚)
│   └── schemas/                    # 请求/响应Pydantic模型
│       ├── __init__.py
│       ├── novel_schemas.py        # 小说相关请求响应
│       ├── character_schemas.py    # 角色相关请求响应
│       ├── image_schemas.py        # 图像相关请求响应
│       ├── model3d_schemas.py      # 3D模型相关请求响应
│       ├── prompt_schemas.py       # Prompt管理请求响应
│       └── prototype_schemas.py    # 身份原型管理请求响应
│
├── core/                           # 业务层
│   ├── __init__.py
│   ├── pipeline.py                 # 三层流水线编排
│   ├── text/                       # 文本理解层
│   │   ├── __init__.py
│   │   ├── graph.py                # LangGraph 工作流定义
│   │   ├── chunker.py              # 智能文本分块
│   │   ├── entity_scanner.py       # 实体预扫描
│   │   ├── feature_extractor.py    # 角色特征提取
│   │   ├── alias_merger.py         # 中文别名合并
│   │   ├── coreference_resolver.py # 共指消解
│   │   ├── memory_manager.py       # 四层记忆体系
│   │   └── identity_resolver.py    # 身份原型优先级覆盖
│   ├── image/                      # 2D生成层
│   │   ├── __init__.py
│   │   ├── feature_mapper.py       # 特征→Prompt映射
│   │   ├── prompt_builder.py       # ComfyUI Prompt构建
│   │   ├── workflow_runner.py      # ComfyUI工作流执行
│   │   ├── grid_generator.py       # Grid Method四视图生成
│   │   ├── consistency_checker.py  # CLIP-I一致性检查
│   │   └── image_postprocessor.py  # 图像后处理
│   └── model3d/                    # 3D生成层(接口预留)
│       ├── __init__.py
│       ├── base.py                 # 3D生成抽象基类
│       ├── interface.py            # 3D生成统一接口定义
│       └── placeholder.py          # 占位实现(返回NotImplemented)
│
├── models/                         # 模型层
│   ├── __init__.py
│   ├── providers/                  # 模型提供商抽象
│   │   ├── __init__.py
│   │   ├── base.py                 # LLM Provider基类
│   │   ├── deepseek_provider.py    # DeepSeek API Provider（主力）
│   │   ├── openai_compat_provider.py # OpenAI兼容格式通用Provider
│   │   └── factory.py              # Provider工厂
│   ├── comfyui/                    # ComfyUI工作流
│   │   ├── __init__.py
│   │   ├── client.py               # fal.ai云端ComfyUI客户端
│   │   ├── workflows.py            # 预定义工作流JSON模板
│   │   └── param_filler.py         # JSON→ComfyUI参数填充器
│   └── schemas/                    # 数据Schema定义
│       ├── __init__.py
│       ├── character_feature.py    # 角色视觉特征Schema
│       ├── novel_metadata.py       # 小说元数据Schema
│       └── generation_config.py    # 生成配置Schema
│
├── data/                           # 数据层
│   ├── __init__.py
│   ├── database.py                 # 数据库连接管理
│   ├── models.py                   # SQLAlchemy ORM模型
│   ├── repositories/               # 数据访问对象
│   │   ├── __init__.py
│   │   ├── novel_repo.py           # 小说数据访问
│   │   ├── character_repo.py       # 角色数据访问
│   │   ├── image_repo.py           # 图像数据访问
│   │   ├── model3d_repo.py         # 3D模型数据访问
│   │   ├── prompt_repo.py          # Prompt模板数据访问(版本管理/回滚)
│   │   └── prototype_repo.py       # 身份原型数据访问(版本管理/LLM生成缓存)
│   └── migrations/                 # 数据库迁移
│       └── init.sql                # 初始化SQL
│
├── config/                         # 配置
│   ├── __init__.py
│   ├── settings.py                 # 全局配置(Pydantic Settings)
│   ├── prompt_manager.py           # Prompt管理器(数据库+文件双源,版本控制,回滚)
│   ├── prompts/                    # Prompt模板(初始种子文件,线上修改后以DB为准)
│   │   ├── extraction_system.txt   # 角色特征提取系统Prompt
│   │   ├── extraction_user.txt     # 角色特征提取用户Prompt
│   │   ├── alias_merge.txt         # 别名合并Prompt
│   │   ├── coreference.txt         # 共指消解Prompt
│   │   └── identity_override.txt   # 身份覆盖Prompt
│   └── prototypes/                 # 身份原型模板
│       └── identity_templates.json # 身份→视觉特征基线映射
│
├── utils/                          # 工具函数
│   ├── __init__.py
│   ├── text_utils.py               # 文本处理工具
│   ├── image_utils.py              # 图像处理工具
│   ├── chinese_nlp.py              # 中文NLP工具
│   └── logger.py                   # 日志配置
│
├── tests/                          # 测试
│   ├── __init__.py
│   ├── test_chunker.py
│   ├── test_entity_scanner.py
│   ├── test_alias_merger.py
│   ├── test_feature_extractor.py
│   ├── test_feature_mapper.py
│   ├── test_consistency_checker.py
│   ├── test_identity_resolver.py
│   └── test_pipeline.py
│
├── .env.example                    # 环境变量示例
├── requirements.txt                # Python依赖
└── README.md                       # 项目说明
```

---

## 5 数据模型设计

### 5.1 数据库表结构

系统使用 SQLite 作为数据存储，通过 SQLAlchemy ORM 管理。共定义7个核心数据表：

#### Novel（小说表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(PK) | UUID主键 |
| title | String | 小说标题 |
| raw_text | Text | 原始文本（或文件路径） |
| total_chars | Integer | 总字数 |
| total_chapters | Integer | 总章节数 |
| processing_status | String | 处理状态：pending/processing/completed/failed |
| chunk_count | Integer | 已处理分块数 |
| memory_snapshot | JSON | 四层记忆体系快照 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### Character（角色表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(PK) | UUID主键 |
| novel_id | String(FK) | 关联小说ID |
| name | String | 角色主名 |
| aliases | JSON | 别名列表 |
| role_type | String | 角色类型：protagonist/supporting/minor |
| importance_score | Float | 重要度评分(0-1) |
| feature_schema | JSON | CharacterFeatureSchema完整JSON |
| identity_prototype | String | 身份原型标识 |
| feature_locked | Boolean | 特征是否已锁定 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### UserPreference（用户偏好表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(PK) | UUID主键 |
| novel_id | String(FK) | 关联小说ID |
| art_style | String | 画风偏好：realistic/anime/ink/oil |
| consistency_threshold | Float | 一致性阈值(默认0.85) |
| auto_lock | Boolean | 是否自动锁定高一致性角色 |
| custom_prompts | JSON | 用户自定义Prompt片段 |
| created_at | DateTime | 创建时间 |

#### GeneratedImage（生成图像表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(PK) | UUID主键 |
| character_id | String(FK) | 关联角色ID |
| image_type | String | 图像类型：portrait/grid_sheet/multi_pose |
| file_path | String | 文件存储路径 |
| file_format | String | 文件格式：png/jpeg |
| clip_i_score | Float | CLIP-I一致性评分 |
| generation_params | JSON | 生成参数快照 |
| is_locked | Boolean | 是否为锁定图像 |
| created_at | DateTime | 创建时间 |

#### GeneratedModel3D（3D模型表，预留）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(PK) | UUID主键 |
| character_id | String(FK) | 关联角色ID |
| source_image_id | String(FK) | 源图像ID |
| file_path | String | 文件存储路径 |
| file_format | String | 文件格式：obj/fbx/stl |
| provider | String | 3D生成提供商 |
| generation_params | JSON | 生成参数 |
| status | String | 状态：pending/completed/failed |
| created_at | DateTime | 创建时间 |

#### PromptTemplate（Prompt模板版本表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer(PK) | 自增主键 |
| template_name | String(100) | 模板名称（如 extraction_system），索引 |
| version | Integer | 版本号，从1递增 |
| content | Text | Prompt模板内容 |
| is_active | Boolean | 是否为当前活跃版本 |
| notes | String(500) | 修改备注（审计用） |
| created_at | DateTime | 创建时间 |

唯一约束：`(template_name, version)`。同一模板仅一行 `is_active=True`。

#### IdentityPrototype（身份原型版本表）

身份原型模板的版本管理表，与 PromptTemplate 同构设计。支持线上修改原型和版本回滚。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer(PK) | 自增主键 |
| identity_label | String(100) | 身份标签（如 beggar/emperor），索引 |
| version | Integer | 版本号，从1递增 |
| content | JSON | 原型特征JSON（含 _meta 元字段） |
| is_active | Boolean | 是否为当前活跃版本 |
| source | String(50) | 来源：seed_file/llm_generated/manual_edit |
| notes | String(500) | 修改备注 |
| created_at | DateTime | 创建时间 |

唯一约束：`(identity_label, version)`。`source` 字段记录原型来源，便于追溯是文件种子、LLM自动生成还是人工编辑。

### 5.2 CharacterFeatureSchema 详细定义

角色视觉特征Schema是连接文本理解层和2D生成层的核心数据结构。所有特征字段均面向视觉生成设计，而非通用NLP特征。

```python
# models/schemas/character_feature.py

class CharacterFeatureSchema(BaseModel):
    """角色视觉特征Schema - 连接文本层和图像层的核心数据结构"""

    # === 基础信息 ===
    name: str                          # 角色主名
    aliases: list[str]                 # 别名列表
    role_type: str                     # protagonist/supporting/minor
    importance_score: float            # 0.0-1.0

    # === 身份锚定特征（跨视图必须一致） ===
    identity: IdentityBlock            # 身份信息

    # === 面部特征 ===
    face: FaceBlock                    # 面部详细特征

    # === 体型特征 ===
    body: BodyBlock                    # 身高/体型/姿态

    # === 发型特征 ===
    hair: HairBlock                    # 发型/发色/发长

    # === 服装特征 ===
    clothing: ClothingBlock            # 服装/配饰/风格

    # === 色彩特征 ===
    color_palette: ColorPaletteBlock   # 主色调/配色方案

    # === 特殊标记 ===
    distinctive_marks: list[MarkItem]  # 疤痕/纹身/胎记等

    # === 文本来源溯源 ===
    text_evidence: dict[str, str]      # 字段→原文引用映射
    confidence_scores: dict[str, float] # 字段→置信度映射

    # === 矛盾标记 ===
    contradictions: list[ContradictionItem] # 检测到的特征矛盾

    # === 元信息 ===
    extraction_source: list[str]       # 来源章节列表
    last_updated_chunk: int            # 最后更新分块索引
```

各子Block定义：

```python
class IdentityBlock(BaseModel):
    """身份锚定 - 决定角色'是谁'的不可变特征"""
    gender: str | None                 # male/female/unknown
    age_range: str | None              # child/teen/young_adult/middle_aged/elderly
    ethnicity: str | None              # 民族/种族视觉特征
    identity_label: str | None         # 身份标签：beggar/monk/warrior/scholar 等
    identity_overridden: bool = False  # 原型特征是否被原文覆盖

class FaceBlock(BaseModel):
    """面部特征"""
    face_shape: str | None             # 圆脸/方脸/瓜子脸/鹅蛋脸
    eye_shape: str | None              # 杏眼/凤眼/桃花眼
    eye_color: str | None
    eyebrow: str | None                # 柳叶眉/剑眉/浓眉
    nose: str | None
    mouth: str | None
    skin_tone: str | None              # 肤色
    facial_hair: str | None            # 胡须（男性）
    expression_default: str | None     # 默认表情

class BodyBlock(BaseModel):
    """体型特征"""
    height_relative: str | None        # tall/average/short（相对描述）
    build: str | None                  # slender/athletic/muscular/heavy
    posture: str | None                # 挺拔/微驼/优雅
    handedness: str | None             # 惯用手

class HairBlock(BaseModel):
    """发型特征"""
    length: str | None                 # 短/中/长/超长
    style: str | None                  # 发型描述
    color: str | None                  # 发色
    texture: str | None                # 直发/卷发/波浪
    accessory: str | None              # 发饰

class ClothingBlock(BaseModel):
    """服装特征"""
    style: str | None                  # 汉服/铠甲/布衣/锦袍
    primary_color: str | None
    secondary_color: str | None
    material: str | None               # 丝绸/棉布/皮革
    accessories: list[str] | None      # 配饰列表
    footwear: str | None               # 鞋履

class ColorPaletteBlock(BaseModel):
    """色彩方案 - 用于统一色调"""
    primary: str | None                # 主色
    secondary: str | None              # 辅色
    accent: str | None                 # 点缀色
    overall_tone: str | None           # warm/cool/neutral

class MarkItem(BaseModel):
    """特殊标记"""
    mark_type: str                     # scar/tattoo/birthmark/accessory
    location: str                      # 位置描述
    description: str                   # 详细描述
    visual_prominence: str             # subtle/medium/prominent

class ContradictionItem(BaseModel):
    """特征矛盾记录"""
    field: str                         # 矛盾字段
    value_a: str                       # 值A
    value_b: str                       # 值B
    source_a: str                      # 来源A（章节引用）
    source_b: str                      # 来源B
    resolution: str                    # 解决方式：prefer_a/prefer_b/merge
```

---

## 6 核心模块详解

### 6.1 配置层 (config/)

#### config/settings.py

全局配置管理，使用 Pydantic Settings 从环境变量加载配置。

```python
class Settings(BaseSettings):
    """全局配置 - 从.env文件加载"""

    # === LLM 配置 ===
    llm_provider: str = "deepseek"         # deepseek / openai_compat
    llm_api_key: str | None = None         # DeepSeek API Key
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"       # DeepSeek-V3

    # === 图像生成配置 ===
    image_provider: str = "fal"            # fal / replicate
    fal_api_key: str | None = None
    replicate_api_token: str | None = None
    comfyui_host: str | None = None        # 本地ComfyUI（可选，默认不用）

    # === 3D 生成配置（预留） ===
    model3d_provider: str | None = None    # trio/meshy/stability
    model3d_api_key: str | None = None

    # === 数据库 ===
    database_url: str = "sqlite:///./data/novel_char.db"

    # === 一致性 ===
    consistency_threshold: float = 0.85
    auto_lock_enabled: bool = True

    # === 文本处理 ===
    max_chunk_size: int = 12000            # 每块最大字符数
    chunk_overlap: int = 500               # 块间重叠
    max_characters_per_novel: int = 100    # 最大角色数

    # === 图像生成 ===
    default_art_style: str = "realistic"
    image_output_dir: str = "output/images"
    default_resolution: tuple[int, int] = (1024, 1024)

    class Config:
        env_file = ".env"
```

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `get_settings() -> Settings` | 获取全局配置单例，使用lru_cache缓存 |

#### config/prompt_manager.py

Prompt 管理器，借鉴 `llm-rag-server` 的 PromptManager 设计思路，实现 **数据库 + 文件双源架构**，支持线上修改和版本回滚。

**核心设计理念：**

- **文件为种子，数据库为准**：`config/prompts/*.txt` 作为初始模板，首次启动时自动导入数据库；此后所有线上修改保存在数据库中，文件不再变化
- **版本控制**：每次修改创建新版本，历史版本永久保留，支持随时回滚到任意版本
- **内存缓存**：活跃版本缓存在内存中，避免每次调用都查数据库；支持手动刷新和TTL自动刷新
- **条件拼接**：支持按场景和条件动态组装Prompt分段（role/ability/format等），借鉴 llm-rag-server 的 `build_complete_prompt()` 设计
- **预览功能**：修改前可用样例数据预览渲染效果，避免线上试错

**PromptVersion 数据类：**

```python
@dataclass
class PromptVersion:
    """Prompt模板版本（内存缓存和API响应的统一数据结构）"""
    template_name: str        # 模板名称
    version: int              # 版本号
    content: str              # 模板内容
    is_active: bool           # 是否为活跃版本
    notes: str                # 修改备注
    created_at: datetime      # 创建时间
```

```python
class PromptManager:
    """Prompt管理器 — 数据库+文件双源,支持版本控制和回滚"""

    def __init__(self, db_session_factory=None):
        self._db_factory = db_session_factory
        self._cache: dict[str, PromptVersion] = {}     # template_name → 活跃版本
        self._lock = threading.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """初始化：将文件模板种子导入数据库(仅首次),加载活跃版本到缓存"""
        await self._seed_from_files()     # 文件→DB(仅不存在的模板)
        await self._reload_cache()        # DB活跃版本→内存缓存
        self._initialized = True

    async def _seed_from_files(self) -> None:
        """扫描 config/prompts/*.txt,将不存在的模板导入数据库"""
        prompts_dir = Path(__file__).parent / "prompts"
        for txt_file in prompts_dir.glob("*.txt"):
            template_name = txt_file.stem
            existing = await self._repo.get_active_version(template_name)
            if not existing:
                content = txt_file.read_text(encoding="utf-8")
                await self._repo.create_version(
                    template_name=template_name,
                    content=content,
                    notes=f"从文件 {txt_file.name} 导入"
                )

    async def _reload_cache(self) -> None:
        """从数据库重新加载所有活跃版本到内存缓存"""
        active_versions = await self._repo.list_active_versions()
        with self._lock:
            self._cache = {v.template_name: v for v in active_versions}

    async def get_prompt(self, template_name: str) -> str:
        """获取指定模板的活跃版本内容(优先从缓存读取)"""
        if not self._initialized:
            await self.initialize()
        with self._lock:
            cached = self._cache.get(template_name)
        if cached:
            return cached.content
        # 缓存未命中,查数据库
        version = await self._repo.get_active_version(template_name)
        if version:
            with self._lock:
                self._cache[template_name] = version
            return version.content
        # 数据库也没有,回退到文件
        return self._load_from_file(template_name)

    def _load_from_file(self, template_name: str) -> str:
        """回退:直接从文件读取(数据库不可用时的降级策略)"""
        file_path = Path(__file__).parent / "prompts" / f"{template_name}.txt"
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Prompt模板 '{template_name}' 不存在于数据库和文件中")

    async def update_prompt(
        self, template_name: str, content: str, notes: str = ""
    ) -> PromptVersion:
        """更新Prompt(创建新版本,旧版本保留)→自动刷新缓存"""
        new_version = await self._repo.create_version(
            template_name=template_name,
            content=content,
            notes=notes
        )
        await self._reload_cache()
        return new_version

    async def rollback(self, template_name: str, target_version: int) -> PromptVersion:
        """回滚到指定版本:将目标版本设为活跃,当前活跃版本变为历史"""
        await self._repo.set_active_version(template_name, target_version)
        await self._reload_cache()
        return await self._repo.get_version(template_name, target_version)

    async def list_versions(self, template_name: str) -> list[PromptVersion]:
        """查看模板的所有历史版本"""
        return await self._repo.list_versions(template_name)

    async def preview_prompt(
        self, template_name: str, content: str, sample_data: dict
    ) -> str:
        """预览:用样例数据渲染Prompt内容(不保存到数据库)"""
        try:
            return content.format(**sample_data)
        except KeyError as e:
            raise ValueError(f"样例数据缺少占位符: {e}")

    async def refresh(self) -> None:
        """手动刷新缓存(线上修改后调用)"""
        await self._reload_cache()

    async def list_templates(self) -> list[str]:
        """列出所有模板名称"""
        return await self._repo.list_template_names()
```

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def initialize() -> None` | 初始化：文件种子导入DB + 加载活跃版本到缓存 |
| `async def get_prompt(template_name: str) -> str` | 获取模板内容（缓存→DB→文件三级回退） |
| `async def update_prompt(template_name, content, notes) -> PromptVersion` | 更新Prompt（创建新版本，旧版本保留） |
| `async def rollback(template_name, target_version) -> PromptVersion` | 回滚到指定历史版本 |
| `async def list_versions(template_name) -> list[PromptVersion]` | 查看模板所有历史版本 |
| `async def preview_prompt(template_name, content, sample_data) -> str` | 预览Prompt渲染效果（不保存） |
| `async def refresh() -> None` | 手动刷新内存缓存 |

#### config/prompts/ 目录

纯文本Prompt模板文件，作为数据库的**初始种子**。首次启动时由 `PromptManager._seed_from_files()` 自动导入数据库。此后线上修改保存在数据库中，文件作为回滚兜底和版本控制初始点。

| 文件 | 用途 |
|------|------|
| `extraction_system.txt` | 角色特征提取的系统Prompt，定义Schema约束和输出格式 |
| `extraction_user.txt` | 角色特征提取的用户Prompt模板，含占位符 `{text_chunk}` `{known_characters}` |
| `alias_merge.txt` | 中文别名合并Prompt，判断多个称呼是否指向同一角色 |
| `coreference.txt` | 共指消解Prompt，处理"他/她/那人"等指代 |
| `identity_override.txt` | 身份原型覆盖Prompt，处理原文与原型的矛盾 |

**数据流转示意：**

```
config/prompts/*.txt (文件种子)
        │
        ▼ 首次启动 _seed_from_files()
┌───────────────────┐
│   SQLite 数据库    │  prompt_templates 表
│   (版本控制存储)   │  ┌────────────────────────────┐
│                   │  │ template_name | version    │
│                   │  │ content       | is_active  │
│                   │  │ notes         | created_at │
│                   │  └────────────────────────────┘
│                   │  每次修改 → 新增一行(version+1)
│                   │  回滚     → 更新 is_active 标记
└────────┬──────────┘
         │ _reload_cache()
         ▼
┌───────────────────┐
│   内存缓存         │  {template_name: PromptVersion}
│   (活跃版本)       │  get_prompt() 优先读取此处
└────────┬──────────┘
         │ get_prompt()
         ▼
┌───────────────────┐
│  text_utils.       │  load_prompt() 调用 PromptManager
│  load_prompt()     │  填充占位符后返回
└───────────────────┘
```

#### config/prototypes/identity_templates.json

身份原型模板，定义各身份标签的视觉特征基线。当原文未描述某特征时，从原型填充默认值。模板同样采用**文件种子 + 数据库版本管理**架构（与 Prompt 管理系统同构），支持线上修改和回滚。

**身份分类体系（MVP 阶段覆盖 15-20 个高频身份）：**

| 域 | 适用小说类型 | MVP 身份标签 | variability 倾向 |
|---|---|---|---|
| 古风域 | 武侠/历史/古言 | 皇帝、将军、书生、和尚、道士、乞丐、侠客、商人、医者、刺客 | 中-高 |
| 仙侠域 | 修仙/玄幻 | 剑修、丹师、宗主、长老、魔修 | 中 |
| 现代域 | 都市/言情/职场 | 总裁、医生、学生、军人 | 低-中 |

**模板结构（含 `_meta` 元字段）：**

```json
{
  "beggar": {
    "_meta": {
      "domain": "ancient",
      "confidence": "high",
      "variability": "high",
      "core_anchors": ["ragged clothing"],
      "notes": "外貌可变性高,原型仅填充clothing/accessories;face/hair/body依赖原文"
    },
    "face": {"skin_tone": "dark", "expression_default": "weary"},
    "body": {"build": "thin", "posture": "hunched"},
    "clothing": {"style": "ragged", "material": "coarse_cloth", "primary_color": "gray_brown"},
    "hair": {"style": "messy", "texture": "unkempt"},
    "color_palette": {"overall_tone": "warm_muted"}
  },
  "emperor": {
    "_meta": {
      "domain": "ancient",
      "confidence": "high",
      "variability": "low",
      "core_anchors": ["dragon robe", "imperial crown"],
      "notes": "视觉高度程式化,原型可靠性高"
    },
    "clothing": {"style": "dragon_robe", "material": "silk", "primary_color": "golden_yellow"},
    "accessories": ["imperial_crown", "jade_belt"],
    "color_palette": {"overall_tone": "regal_gold"}
  },
  "monk": {
    "_meta": {
      "domain": "ancient",
      "confidence": "high",
      "variability": "low",
      "core_anchors": ["shaved head", "monk robe"],
      "notes": "视觉高度程式化"
    },
    "hair": {"length": "bald", "style": "shaved"},
    "clothing": {"style": "monk_robe", "primary_color": "gray_or_yellow"},
    "accessories": ["rosary", "alms_bowl"]
  },
  "warrior": {
    "_meta": {
      "domain": "ancient",
      "confidence": "medium",
      "variability": "medium",
      "core_anchors": ["martial clothing"],
      "notes": "体型和面部变化较多,原型主要锚定服装"
    },
    "body": {"build": "athletic", "posture": "upright"},
    "clothing": {"style": "armor_or_martial", "material": "leather_metal"},
    "color_palette": {"overall_tone": "cool_bold"}
  }
}
```

**`variability` 字段对原型填充策略的影响：**

| variability | 含义 | 填充策略 | 示例身份 |
|---|---|---|---|
| `low` | 身份高度程式化，原型可靠 | 全字段填充（face/hair/body/clothing） | 皇帝、和尚、骑士 |
| `medium` | 有视觉共识但变化较多 | 填充 clothing/accessories/color_palette，face/hair/body 仅作参考 | 将军、书生、医生 |
| `high` | 外貌可变性大 | 仅填充 clothing/accessories，face/hair/body 完全依赖原文 | 乞丐、商人、刺客 |

**原型准备方法（三合一）：**

1. **LLM 辅助生成**：用 DeepSeek API 批量生成初稿（约$0.02/20个身份），Prompt 通过 PromptManager 管理
2. **概念设计参考**：从角色设计资源（水浒图谱、仙侠游戏设定集等）提取视觉共识，人工校验
3. **反向提取验证**：选 3-5 部测试小说，跑完文本理解层后检查 null 字段分布，验证原型覆盖率

---

### 6.2 API层 (api/)

#### api/main.py

FastAPI应用入口，负责应用创建、路由注册、中间件配置、生命周期管理。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `create_app() -> FastAPI` | 创建FastAPI应用实例，注册路由、CORS、异常处理 |
| `lifespan(app: FastAPI) -> AsyncGenerator` | 应用生命周期管理，启动时初始化数据库、PromptManager（文件种子导入+缓存加载），关闭时清理资源 |

#### api/deps.py

依赖注入模块，为路由提供数据库会话、配置、Repository等依赖。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `get_db() -> Generator[Session, None, None]` | 提供数据库会话依赖 |
| `get_settings() -> Settings` | 提供全局配置依赖 |
| `get_novel_repo(db: Session = Depends(get_db)) -> NovelRepository` | 提供小说Repository依赖 |
| `get_character_repo(db: Session = Depends(get_db)) -> CharacterRepository` | 提供角色Repository依赖 |
| `get_image_repo(db: Session = Depends(get_db)) -> ImageRepository` | 提供图像Repository依赖 |
| `get_llm_provider(settings: Settings = Depends(get_settings)) -> BaseLLMProvider` | 提供LLM Provider依赖 |
| `get_comfyui_client(settings: Settings = Depends(get_settings)) -> FalComfyUIClient` | 提供fal.ai云端ComfyUI客户端依赖 |
| `get_prompt_manager(db: Session = Depends(get_db)) -> PromptManager` | 提供Prompt管理器依赖（单例，缓存活跃版本） |

#### api/routes/novels.py

小说管理路由，处理小说上传、列表查询、状态查看、删除等操作。

**关键路由函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def upload_novel(title: str, file: UploadFile, db: Session) -> NovelResponse` | 上传小说文件，存储原文，创建Novel记录 |
| `async def list_novels(skip: int, limit: int, db: Session) -> list[NovelResponse]` | 分页查询小说列表 |
| `async def get_novel(novel_id: str, db: Session) -> NovelResponse` | 获取单部小说详情 |
| `async def delete_novel(novel_id: str, db: Session) -> None` | 删除小说及其关联数据 |
| `async def get_novel_status(novel_id: str, db: Session) -> ProcessingStatusResponse` | 获取小说处理进度 |

#### api/routes/characters.py

角色管理路由，处理角色查询、特征查看/编辑、锁定/解锁等操作。

**关键路由函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def list_characters(novel_id: str, db: Session) -> list[CharacterResponse]` | 查询小说下所有角色 |
| `async def get_character(character_id: str, db: Session) -> CharacterDetailResponse` | 获取角色详情含完整特征Schema |
| `async def update_character_features(character_id: str, features: CharacterFeatureUpdate, db: Session) -> CharacterDetailResponse` | 手动编辑角色特征 |
| `async def lock_character(character_id: str, db: Session) -> CharacterResponse` | 锁定角色特征，锁定后不再增量更新 |
| `async def unlock_character(character_id: str, db: Session) -> CharacterResponse` | 解锁角色特征 |

#### api/routes/images.py

图像生成路由，处理角色插画生成、四视图生成、一致性检查等请求。

**关键路由函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def generate_portrait(character_id: str, params: PortraitParams, db: Session) -> ImageResponse` | 生成角色正面肖像 |
| `async def generate_grid_sheet(character_id: str, params: GridParams, db: Session) -> ImageResponse` | 生成四视图设定图 |
| `async def generate_multi_pose(character_id: str, params: PoseParams, db: Session) -> list[ImageResponse]` | 生成多姿势图（基于锁定肖像） |
| `async def check_consistency(image_id: str, db: Session) -> ConsistencyResponse` | 检查图像CLIP-I一致性 |
| `async def lock_image(image_id: str, db: Session) -> ImageResponse` | 锁定图像作为角色基准 |
| `async def list_images(character_id: str, db: Session) -> list[ImageResponse]` | 查询角色所有生成图像 |

#### api/routes/models3d.py（接口预留）

3D模型生成路由，本期仅定义路由结构和请求/响应模型，实际生成逻辑返回501 Not Implemented。

**关键路由函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def generate_model3d(character_id: str, params: Model3DParams, db: Session) -> Model3DResponse` | 生成3D模型（返回501） |
| `async def list_models3d(character_id: str, db: Session) -> list[Model3DResponse]` | 查询角色3D模型列表（返回空列表） |
| `async def get_model3d(model_id: str, db: Session) -> Model3DResponse` | 获取3D模型详情（返回501） |
| `async def download_model3d(model_id: str, db: Session) -> FileResponse` | 下载3D模型文件（返回501） |

#### api/routes/pipeline.py

完整流水线路由，一键执行从文本到图像的完整处理流程。

**关键路由函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def run_full_pipeline(novel_id: str, config: PipelineConfig, db: Session) -> PipelineResponse` | 执行完整流水线：文本提取→2D生成 |
| `async def run_text_only(novel_id: str, db: Session) -> list[CharacterResponse]` | 仅执行文本理解层 |
| `async def run_image_only(character_id: str, params: ImageGenParams, db: Session) -> ImageResponse` | 仅执行2D生成层 |
| `async def get_pipeline_status(task_id: str) -> PipelineStatusResponse` | 查询流水线异步任务状态 |

#### api/routes/prompts.py

Prompt管理路由，提供线上修改、版本回滚、预览等管理功能。借鉴 `llm-rag-server` 的 admin API 设计，支持不重启服务动态调整Prompt。

**关键路由函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def list_templates(db: Session) -> list[PromptTemplateSummary]` | 列出所有Prompt模板及当前活跃版本信息 |
| `async def get_template(template_name: str, db: Session) -> PromptTemplateDetail` | 获取模板详情，含当前活跃版本内容和占位符列表 |
| `async def get_prompt_content(template_name: str, db: Session) -> str` | 获取模板当前活跃版本的纯文本内容 |
| `async def update_prompt(template_name: str, body: PromptUpdateRequest, db: Session) -> PromptVersionResponse` | 更新Prompt内容（创建新版本，旧版本保留），自动刷新缓存 |
| `async def list_versions(template_name: str, db: Session) -> list[PromptVersionResponse]` | 查看模板的所有历史版本列表 |
| `async def get_version(template_name: str, version: int, db: Session) -> PromptVersionResponse` | 获取指定版本的详细内容 |
| `async def rollback_prompt(template_name: str, version: int, db: Session) -> PromptVersionResponse` | 回滚到指定历史版本，自动刷新缓存 |
| `async def preview_prompt(body: PromptPreviewRequest, db: Session) -> PromptPreviewResponse` | 预览Prompt渲染效果（不保存到数据库），传入内容和样例数据 |
| `async def refresh_cache(db: Session) -> dict` | 手动刷新内存缓存，线上修改后立即生效 |
| `async def diff_versions(template_name: str, v1: int, v2: int, db: Session) -> PromptDiffResponse` | 对比两个版本内容的差异 |

#### api/routes/prototypes.py

身份原型管理路由，提供线上修改、版本回滚、LLM自动生成等管理功能。与 Prompt 管理路由同构设计。

**关键路由函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def list_prototypes(db: Session) -> list[PrototypeSummary]` | 列出所有身份原型及当前活跃版本信息 |
| `async def get_prototype(identity_label: str, db: Session) -> PrototypeDetail` | 获取原型详情，含特征JSON和 variability 元字段 |
| `async def update_prototype(identity_label: str, body: PrototypeUpdateRequest, db: Session) -> PrototypeVersionResponse` | 更新原型内容（创建新版本），自动刷新缓存 |
| `async def list_prototype_versions(identity_label: str, db: Session) -> list[PrototypeVersionResponse]` | 查看原型所有历史版本 |
| `async def rollback_prototype(identity_label: str, version: int, db: Session) -> PrototypeVersionResponse` | 回滚到指定历史版本 |
| `async def generate_prototype(body: PrototypeGenerateRequest, db: Session) -> PrototypeVersionResponse` | LLM自动生成身份原型（未覆盖身份的兜底入口），生成后自动写入数据库 |
| `async def validate_prototype(identity_label: str, db: Session) -> dict` | 触发纯原型生成验证（生成一张测试图），返回验证任务ID |

#### api/schemas/ 目录

请求/响应Pydantic模型定义。每个文件对应一个路由模块的Schema。

| 文件 | 关键类 | 说明 |
|------|--------|------|
| `novel_schemas.py` | `NovelResponse`, `ProcessingStatusResponse` | 小说响应模型 |
| `character_schemas.py` | `CharacterResponse`, `CharacterDetailResponse`, `CharacterFeatureUpdate` | 角色响应和更新模型 |
| `image_schemas.py` | `PortraitParams`, `GridParams`, `PoseParams`, `ImageResponse`, `ConsistencyResponse` | 图像生成参数和响应 |
| `model3d_schemas.py` | `Model3DParams`, `Model3DResponse` | 3D模型参数和响应（预留） |
| `prompt_schemas.py` | `PromptTemplateSummary`, `PromptTemplateDetail`, `PromptUpdateRequest`, `PromptVersionResponse`, `PromptPreviewRequest`, `PromptPreviewResponse`, `PromptDiffResponse` | Prompt管理请求响应 |
| `prototype_schemas.py` | `PrototypeSummary`, `PrototypeDetail`, `PrototypeUpdateRequest`, `PrototypeVersionResponse`, `PrototypeGenerateRequest` | 身份原型管理请求响应 |

**`prompt_schemas.py` 关键模型定义：**

```python
class PromptTemplateSummary(BaseModel):
    """模板列表项"""
    template_name: str
    active_version: int
    total_versions: int
    updated_at: datetime

class PromptTemplateDetail(BaseModel):
    """模板详情"""
    template_name: str
    active_version: int
    content: str
    placeholders: list[str]          # 自动提取的占位符列表
    total_versions: int
    updated_at: datetime

class PromptUpdateRequest(BaseModel):
    """更新Prompt请求"""
    content: str
    notes: str = ""                  # 修改备注（必填，审计用）

class PromptVersionResponse(BaseModel):
    """版本详情响应"""
    template_name: str
    version: int
    content: str
    is_active: bool
    notes: str
    created_at: datetime

class PromptPreviewRequest(BaseModel):
    """预览请求"""
    content: str                     # 待预览的Prompt内容
    sample_data: dict                # 样例数据（占位符→值）

class PromptPreviewResponse(BaseModel):
    """预览响应"""
    rendered: str                    # 渲染后的完整Prompt
    placeholders: list[str]          # 检测到的占位符

class PromptDiffResponse(BaseModel):
    """版本差异响应"""
    template_name: str
    v1: int
    v2: int
    diff: str                        # unified diff 格式文本
```

---

### 6.3 文本理解层 (core/text/)

文本理解层是项目的第一层，使用 LangGraph 编排多Agent协作，从小说文本中提取结构化角色视觉特征。

#### core/text/chunker.py

智能文本分块模块。不按字数硬切，而是按章节边界智能切分，保留上下文完整性。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `def chunk_novel(text: str, max_size: int = 12000, overlap: int = 500) -> list[TextChunk]` | 主函数：将小说文本切分为多个块 |
| `def detect_chapter_boundaries(text: str) -> list[int]` | 检测章节边界，识别"第X章"、"卷X"等模式 |
| `def split_by_chapters(text: str, boundaries: list[int]) -> list[str]` | 按章节边界切分文本 |
| `def merge_small_chunks(chunks: list[str], min_size: int) -> list[str]` | 合并过小章节，避免碎片化 |
| `def split_oversized_chunk(chunk: str, max_size: int) -> list[str]` | 拆分过大章节，在段落边界处切割 |
| `def add_overlap(chunks: list[str], overlap: int) -> list[str]` | 为每个块添加前一块的尾部重叠 |

```python
class TextChunk(BaseModel):
    """文本块数据结构"""
    index: int                # 块索引
    text: str                 # 块文本
    char_start: int           # 原文起始字符位置
    char_end: int             # 原文结束字符位置
    chapter_info: str | None  # 所属章节信息
    token_estimate: int       # Token估算
```

#### core/text/entity_scanner.py

实体预扫描模块。使用 jieba 快速扫描候选人名，减少后续LLM处理的负担。借鉴 AI Reader V2 的实体预扫描策略。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `def scan_entities(text: str) -> list[EntityCandidate]` | 主函数：扫描文本中的候选人名实体 |
| `def extract_name_candidates(text: str) -> list[str]` | 使用jieba词性标注提取人名候选 |
| `def filter_by_frequency(candidates: list[str], min_freq: int = 2) -> list[str]` | 按出现频次过滤，去除噪音 |
| `def merge_substrings(candidates: list[str]) -> list[str]` | 合并子串，如"林冲"和"林教头"分别保留但标记关联 |
| `def build_entity_index(text: str, entities: list[str]) -> dict[str, list[int]]` | 构建实体→位置索引，便于后续定位 |

```python
class EntityCandidate(BaseModel):
    """实体候选"""
    name: str               # 实体名称
    frequency: int          # 出现频次
    positions: list[int]    # 在原文中的字符位置列表
    is_likely_name: bool    # 是否可能是人名（基于上下文）
```

#### core/text/alias_merger.py

中文别名合并模块。判断多个称呼是否指向同一角色，合并别名。借鉴 AI Reader V2 的中文别名合并算法思路，但完全自行实现（注意AGPL协议限制）。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def merge_aliases(entities: list[EntityCandidate], llm_provider: BaseLLMProvider) -> list[CharacterGroup]` | 主函数：合并别名，返回角色组 |
| `def build_alias_prompt(entities: list[EntityCandidate]) -> str` | 构建别名判断Prompt |
| `def parse_alias_response(response: str) -> list[list[str]]` | 解析LLM返回的别名分组 |
| `def apply_merge_rules(groups: list[list[str]], entities: list[EntityCandidate]) -> list[CharacterGroup]` | 应用规则后处理：姓氏匹配、称谓模式匹配 |
| `def select_primary_name(group: list[str]) -> str` | 从别名组中选择主名（优先全名、其次最长名称） |
| `def resolve_conflicts(groups: list[CharacterGroup]) -> list[CharacterGroup]` | 解决跨组冲突（一个别名被分到多组） |

```python
class CharacterGroup(BaseModel):
    """角色别名组"""
    primary_name: str           # 主名
    aliases: list[str]          # 所有别名
    mention_count: int          # 总提及次数
    first_appearance_chunk: int # 首次出现块索引
```

#### core/text/coreference_resolver.py

共指消解模块。处理"他/她/那人/此女"等代词指代，将指代还原为具体角色。采用规则+LLM混合策略：简单指代用规则解决，复杂情况用LLM。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def resolve_coreferences(text_chunk: str, known_characters: list[CharacterGroup], llm_provider: BaseLLMProvider) -> CoreferenceResult` | 主函数：消解共指 |
| `def detect_pronouns(text: str) -> list[PronounMention]` | 检测代词出现位置 |
| `def resolve_by_rules(mentions: list[PronounMention], context: str) -> list[ResolvedMention]` | 规则消解：就近指代、性别匹配 |
| `async def resolve_by_llm(unsolved: list[PronounMention], context: str, characters: list[CharacterGroup], llm_provider: BaseLLMProvider) -> list[ResolvedMention]` | LLM消解：复杂上下文中的指代 |
| `def merge_results(rule_resolved: list, llm_resolved: list) -> CoreferenceResult` | 合并两种策略的结果 |

```python
class PronounMention(BaseModel):
    """代词提及"""
    pronoun: str            # 代词文本
    position: int           # 位置
    sentence: str           # 所在句子

class ResolvedMention(BaseModel):
    """已消解的提及"""
    pronoun: str
    resolved_to: str        # 指向的角色名
    confidence: float       # 置信度
    method: str             # rule/llm

class CoreferenceResult(BaseModel):
    """共指消解结果"""
    resolved: list[ResolvedMention]
    unresolved: list[PronounMention]
```

#### core/text/feature_extractor.py

角色特征提取模块。这是文本理解层的核心，将小说文本转化为 CharacterFeatureSchema。每个角色跨章节增量累积特征。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def extract_features(text_chunk: str, character_name: str, known_features: CharacterFeatureSchema | None, llm_provider: BaseLLMProvider) -> CharacterFeatureSchema` | 主函数：从文本块中提取角色特征，与已知特征合并 |
| `def build_extraction_prompt(text_chunk: str, character_name: str, known_features: CharacterFeatureSchema | None) -> tuple[str, str]` | 构建系统Prompt和用户Prompt |
| `def parse_feature_response(response: str, character_name: str) -> CharacterFeatureSchema` | 解析LLM返回的特征JSON |
| `def merge_features(old: CharacterFeatureSchema, new: CharacterFeatureSchema) -> CharacterFeatureSchema` | 合并增量特征，新特征覆盖旧特征，保留溯源信息 |
| `def detect_contradictions(old: CharacterFeatureSchema, new: CharacterFeatureSchema) -> list[ContradictionItem]` | 检测新旧特征间的矛盾 |
| `def resolve_contradictions(contradictions: list[ContradictionItem], schema: CharacterFeatureSchema) -> CharacterFeatureSchema` | 解决矛盾：优先采信更具体的描述 |
| `def calculate_confidence(schema: CharacterFeatureSchema, source_count: int) -> CharacterFeatureSchema` | 计算各字段的置信度 |
| `def map_chinese_metaphors(text: str) -> str` | 中文比喻→视觉标签映射（如"面如冠玉"→"skin_tone: pale, smooth"） |
| `def extract_text_evidence(text: str, field: str, value: str) -> str` | 提取字段对应的原文引用作为溯源 |

#### core/text/identity_resolver.py

身份原型优先级覆盖模块。处理角色身份与原文描写的矛盾，实现三级优先级：原文明确描写 > 身份原型基线 > 风格模板默认值。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `def resolve_identity_features(schema: CharacterFeatureSchema) -> CharacterFeatureSchema` | 主函数：应用身份原型并处理覆盖 |
| `def load_identity_template(identity_label: str) -> dict` | 从数据库（缓存）加载身份原型，未命中时回退到文件 |
| `def apply_prototype_baseline(schema: CharacterFeatureSchema, template: dict) -> CharacterFeatureSchema` | 将原型基线填充到Schema中未设置的字段，根据 variability 控制填充范围 |
| `def detect_identity_contradiction(schema: CharacterFeatureSchema, template: dict) -> list[ContradictionItem]` | 检测原文特征与原型基线的矛盾 |
| `def override_with_text(schema: CharacterFeatureSchema, contradictions: list[ContradictionItem]) -> CharacterFeatureSchema` | 文本描述优先覆盖原型特征 |
| `def build_contrast_prompt(schema: CharacterFeatureSchema, contradictions: list[ContradictionItem]) -> str` | 构建反差提示Prompt，让AI理解"干净的乞丐"等反差设定 |
| `def adjust_prompt_weights(schema: CharacterFeatureSchema, contradictions: list[ContradictionItem]) -> dict[str, float]` | 调整Prompt权重，增强反差特征的权重 |
| `def get_prototype_fallback(identity_label: str) -> dict` | 兜底：精确匹配→模糊匹配→LLM实时生成→纯文本模式 |
| `def record_usage_stats(stats: PrototypeUsageStats) -> None` | 记录原型使用统计到日志，用于效果分析 |

**variability 驱动的填充策略：**

```python
def apply_prototype_baseline(schema, template):
    """根据 variability 控制原型填充范围"""
    meta = template.get("_meta", {})
    variability = meta.get("variability", "medium")
    stats = PrototypeUsageStats(
        identity_label=schema.identity.identity_label,
        total_fields=count_fields(schema),
        from_text=0, from_prototype=0, from_style_default=0,
        contradictions=0
    )

    if variability == "low":
        # 全字段填充: face/hair/body/clothing/accessories/color_palette
        fillable_categories = ["face", "hair", "body", "clothing", "accessories", "color_palette"]
    elif variability == "medium":
        # 仅填充: clothing/accessories/color_palette, face/hair/body 作参考(低权重)
        fillable_categories = ["clothing", "accessories", "color_palette"]
    else:  # high
        # 仅填充: clothing/accessories
        fillable_categories = ["clothing", "accessories"]

    for category in fillable_categories:
        if category in template and not schema_has_value(schema, category):
            fill_schema_field(schema, category, template[category])
            stats.from_prototype += count_category_fields(template[category])

    return schema, stats
```

**PrototypeUsageStats 数据类：**

```python
@dataclass
class PrototypeUsageStats:
    """原型使用统计 — 记录每个角色的特征来源分布"""
    identity_label: str
    total_fields: int              # Schema总字段数
    from_text: int                 # 来自原文描写的字段数
    from_prototype: int            # 来自原型填充的字段数
    from_style_default: int        # 来自风格模板默认值的字段数
    contradictions: int            # 原文与原型矛盾的字段数

    @property
    def prototype_coverage(self) -> float:
        """原型填充率 = from_prototype / total_fields"""
        return self.from_prototype / max(self.total_fields, 1)
```

**兜底机制（未覆盖身份的降级策略）：**

```
1. 精确匹配：identity_templates 中找到 → 使用原型
2. 模糊匹配：jieba 分词 + 语义相似度找最接近的身份 → 使用近似原型
3. LLM 生成：调用 DeepSeek 实时生成原型 → 缓存到数据库 → 下次直接使用
4. 纯文本模式：完全依赖原文描写，仅使用风格模板默认值
```

第3步 LLM 实时生成的原型会自动写入数据库 `identity_prototypes` 表，下次遇到相同身份直接从缓存读取，系统**越用越完善**。 |

**优先级处理逻辑示例（"干净的乞丐"）：**

```
1. 原型基线：beggar → {skin_tone: dark, build: thin, clothing: ragged}
2. 原文描写：{skin_tone: clean, clothing: tidy}
3. 矛盾检测：skin_tone(dark vs clean), clothing(ragged vs tidy)
4. 覆盖处理：采用原文值 clean/tidy
5. 反差提示：生成 "A beggar who is unusually clean and well-groomed, wearing tidy clothes, creating a striking contrast with typical beggar appearance"
6. 权重调整：clean (+1.3 weight), tidy (+1.2 weight)
7. 保留原型：build: thin 保留（原文未否定）
```

#### core/text/memory_manager.py

四层记忆体系管理模块。支持增量处理小说内容，不丢失已抽取的特征和关系。

**四层记忆结构：**

| 层级 | 名称 | 内容 | 存储方式 |
|------|------|------|----------|
| L1 | 事实记忆 | 已确认的角色特征事实 | CharacterFeatureSchema JSON |
| L2 | 关系记忆 | 角色间关系图谱 | 邻接表 |
| L3 | 事件记忆 | 关键事件及其参与角色 | 事件列表 |
| L4 | 上下文记忆 | 当前处理位置、待解决疑问 | 处理状态 |

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `class MemoryManager` | 记忆管理器，管理四层记忆 |
| `def __init__(self, novel_id: str)` | 初始化，从数据库加载已有记忆 |
| `def load_snapshot(self) -> MemorySnapshot` | 加载记忆快照 |
| `def save_snapshot(self, snapshot: MemorySnapshot) -> None` | 保存记忆快照到数据库 |
| `def update_facts(self, character_id: str, features: CharacterFeatureSchema) -> None` | 更新L1事实记忆 |
| `def update_relations(self, char_a: str, char_b: str, relation: str) -> None` | 更新L2关系记忆 |
| `def update_events(self, event: EventItem) -> None` | 更新L3事件记忆 |
| `def get_context(self, character_name: str) -> str` | 获取角色的完整记忆上下文，用于Prompt构建 |
| `def get_pending_questions(self) -> list[str]` | 获取L4中待解决的问题 |
| `def add_pending_question(self, question: str) -> None` | 添加待解决问题 |
| `def resolve_question(self, question: str, answer: str) -> None` | 标记问题已解决 |
| `def incremental_update(self, new_chunk: TextChunk) -> IncrementalResult` | 增量处理新文本块，更新四层记忆 |

```python
class MemorySnapshot(BaseModel):
    """记忆快照"""
    novel_id: str
    l1_facts: dict[str, CharacterFeatureSchema]   # 角色名→特征
    l2_relations: dict[str, list[RelationEdge]]   # 角色名→关系列表
    l3_events: list[EventItem]                     # 事件列表
    l4_context: ProcessingContext                  # 处理上下文
    snapshot_chunk_index: int                      # 快照对应的块索引

class EventItem(BaseModel):
    """事件项"""
    description: str
    participants: list[str]
    chapter: str | None
    emotional_tone: str | None

class RelationEdge(BaseModel):
    """关系边"""
    target: str              # 目标角色
    relation_type: str       # master/disciple/friend/enemy/lover/family
    description: str | None  # 关系描述
```

#### core/text/graph.py

LangGraph 工作流定义模块。编排上述所有文本处理节点，构成完整的文本理解工作流。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `def build_text_graph() -> CompiledGraph` | 构建LangGraph工作流，定义节点和边 |
| `async def run_text_pipeline(novel_id: str, text: str, llm_provider: BaseLLMProvider) -> list[CharacterFeatureSchema]` | 执行完整文本理解流水线 |
| `async def node_chunk_text(state: TextGraphState) -> TextGraphState` | 节点：文本分块 |
| `async def node_scan_entities(state: TextGraphState) -> TextGraphState` | 节点：实体预扫描 |
| `async def node_merge_aliases(state: TextGraphState) -> TextGraphState` | 节点：别名合并 |
| `async def node_extract_features(state: TextGraphState) -> TextGraphState` | 节点：特征提取（循环，每个块每个角色） |
| `async def node_resolve_coreferences(state: TextGraphState) -> TextGraphState` | 节点：共指消解 |
| `async def node_resolve_identity(state: TextGraphState) -> TextGraphState` | 节点：身份原型覆盖 |
| `async def node_human_review(state: TextGraphState) -> TextGraphState` | 节点：人工审核（可选，默认跳过） |
| `def should_continue_extraction(state: TextGraphState) -> str` | 条件路由：判断是否还有未处理的块 |
| `def route_by_importance(state: TextGraphState) -> str` | 条件路由：按角色重要度选择处理深度 |

```python
class TextGraphState(TypedDict):
    """LangGraph 状态定义"""
    novel_id: str
    raw_text: str
    chunks: list[TextChunk]
    current_chunk_index: int
    entity_candidates: list[EntityCandidate]
    character_groups: list[CharacterGroup]
    memory_manager: MemoryManager
    llm_provider: BaseLLMProvider
    extracted_characters: list[CharacterFeatureSchema]
    pending_coreferences: list[PronounMention]
    errors: list[str]
    status: str  # running/paused/completed/failed
```

**工作流结构：**

```
START
  │
  ▼
node_chunk_text ──► node_scan_entities ──► node_merge_aliases
  │
  ▼
node_extract_features ◄──┐
  │                      │
  ▼                      │
node_resolve_coreferences│
  │                      │
  ▼                      │
should_continue? ───yes──┘
  │
  no
  ▼
node_resolve_identity
  │
  ▼
node_human_review (optional)
  │
  ▼
END
```

---

### 6.4 2D生成层 (core/image/)

2D生成层负责将 CharacterFeatureSchema 转化为高质量角色插画。核心流程为五步管线：抽取→补全→初稿→锁定→量产。

#### core/image/feature_mapper.py

特征到Prompt映射模块。将结构化的 CharacterFeatureSchema 转化为ComfyUI可用的文本Prompt。这是项目的核心自研壁垒之一。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `def map_features_to_prompt(schema: CharacterFeatureSchema, art_style: str = "realistic") -> ImagePrompt` | 主函数：特征Schema→图像Prompt |
| `def map_identity_block(block: IdentityBlock) -> str` | 映射身份特征到Prompt片段 |
| `def map_face_block(block: FaceBlock) -> str` | 映射面部特征到Prompt片段 |
| `def map_body_block(block: BodyBlock) -> str` | 映射体型特征到Prompt片段 |
| `def map_hair_block(block: HairBlock) -> str` | 映射发型特征到Prompt片段 |
| `def map_clothing_block(block: ClothingBlock) -> str` | 映射服装特征到Prompt片段 |
| `def map_color_palette(block: ColorPaletteBlock) -> str` | 映射色彩方案到Prompt片段 |
| `def map_distinctive_marks(marks: list[MarkItem]) -> str` | 映射特殊标记到Prompt片段 |
| `def apply_contrast_prompt(schema: CharacterFeatureSchema, contradictions: list[ContradictionItem]) -> str` | 生成反差提示文本 |
| `def apply_weight_adjustments(prompt: str, weights: dict[str, float]) -> str` | 应用ComfyUI权重语法 (keyword:1.3) |
| `def select_style_template(art_style: str) -> str` | 选择画风模板 |
| `def build_negative_prompt(schema: CharacterFeatureSchema) -> str` | 构建负面Prompt，排除不想要的元素 |

```python
class ImagePrompt(BaseModel):
    """图像Prompt容器"""
    positive: str              # 正面Prompt
    negative: str              # 负面Prompt
    weight_adjustments: dict[str, float]  # 权重调整
    style_template: str        # 使用的画风模板
    contrast_hints: list[str]  # 反差提示
```

#### core/image/prompt_builder.py

ComfyUI Prompt构建模块。将 ImagePrompt 和生成参数组装为完整的ComfyUI工作流参数。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `def build_portrait_prompt(schema: CharacterFeatureSchema, art_style: str) -> dict` | 构建肖像生成的工作流参数 |
| `def build_grid_prompt(schema: CharacterFeatureSchema, art_style: str) -> dict` | 构建四视图网格的工作流参数 |
| `def build_multi_pose_prompt(schema: CharacterFeatureSchema, base_image_path: str, poses: list[str]) -> dict` | 构建多姿势生成的工作流参数 |
| `def apply_instantid_params(params: dict, reference_image: str | None) -> dict` | 应用InstantID一致性参数 |
| `def apply_controlnet_params(params: dict, pose_images: list[str] | None) -> dict` | 应用ControlNet姿态控制参数 |
| `def apply_lora_params(params: dict, lora_path: str | None) -> dict` | 应用LoRA参数（v2功能，MVP阶段为None） |
| `def set_resolution(params: dict, width: int, height: int) -> dict` | 设置输出分辨率 |

#### core/image/workflow_runner.py

云端工作流执行模块。负责通过 fal.ai API 提交 ComfyUI 工作流、轮询状态、下载结果图像。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def run_workflow(workflow_params: dict, client: FalComfyUIClient) -> WorkflowResult` | 主函数：通过fal.ai执行ComfyUI工作流 |
| `async def submit_workflow(params: dict, client: FalComfyUIClient) -> str` | 提交工作流到fal.ai云端，返回request_id |
| `async def poll_status(request_id: str, client: FalComfyUIClient, timeout: int = 300) -> FalResult` | 轮询执行状态 |
| `async def download_result_image(image_url: str, output_dir: str) -> str` | 从fal.ai下载生成的图像到本地 |
| `def save_image(image_data: bytes, output_dir: str, filename: str) -> str` | 保存图像文件 |
| `async def run_replicate_workflow(params: dict, api_token: str) -> list[bytes]` | Replicate API生成（备选方案） |

```python
class WorkflowResult(BaseModel):
    """工作流执行结果"""
    success: bool
    image_paths: list[str]    # 生成的图像文件路径
    generation_time: float    # 生成耗时（秒）
    params_snapshot: dict     # 参数快照
    error: str | None         # 错误信息
```

#### core/image/grid_generator.py

Grid Method 四视图生成模块。在一次生成请求中输出包含多视角的角色设定网格，利用统一潜空间保持一致性。

**四视图定义：**

| 视图 | 视角 | 用途 |
|------|------|------|
| 正面 | front view | 肖像基准、InstantID参考 |
| 侧面 | side profile | 侧面轮廓特征 |
| 背面 | back view | 发型/服装背面细节 |
| 全身 | full body | 体型/服装全貌 |

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def generate_grid_sheet(schema: CharacterFeatureSchema, art_style: str, client: FalComfyUIClient) -> GridResult` | 主函数：生成四视图网格图 |
| `def build_grid_prompt(schema: CharacterFeatureSchema) -> str` | 构建四视图网格Prompt，包含"character sheet, multiple views, front view, side profile, back view, full body"等关键词 |
| `def build_grid_layout_params() -> dict` | 构建网格布局参数（2x2排列） |
| `def split_grid_image(grid_path: str, output_dir: str) -> list[str]` | 将网格图切分为4张单独视图 |
| `def select_front_view(split_images: list[str]) -> str` | 从切分结果中选择正面视图作为基准 |
| `async def refine_single_view(view_path: str, view_type: str, schema: CharacterFeatureSchema, client: FalComfyUIClient) -> str` | 对单张视图进行精修（可选） |

```python
class GridResult(BaseModel):
    """四视图生成结果"""
    grid_image_path: str       # 完整网格图路径
    split_views: dict[str, str]  # view_type→image_path
    front_view_path: str       # 正面视图路径（基准）
    consistency_score: float | None  # 网格内一致性评分
```

#### core/image/consistency_checker.py

CLIP-I 一致性检查模块。量化评估角色插画的一致性，决定是否需要重新生成或锁定。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def check_consistency(reference_image: str, target_image: str) -> ConsistencyResult` | 主函数：计算两张图的CLIP-I相似度 |
| `def compute_clip_i_score(ref_features: np.ndarray, target_features: np.ndarray) -> float` | 计算CLIP-I余弦相似度 |
| `def extract_clip_features(image_path: str) -> np.ndarray` | 提取图像的CLIP特征向量 |
| `async def batch_consistency_check(base_image: str, pose_images: list[str]) -> list[ConsistencyResult]` | 批量检查多姿势一致性 |
| `def evaluate_quality(image_path: str) -> QualityMetrics` | 评估图像质量（清晰度、构图等） |
| `def should_regenerate(score: float, threshold: float) -> bool` | 判断是否需要重新生成 |
| `def should_lock(score: float, threshold: float) -> bool` | 判断是否可以锁定角色形象 |
| `async def check_grid_consistency(grid_views: dict[str, str]) -> float` | 检查四视图间的互相一致性 |

```python
class ConsistencyResult(BaseModel):
    """一致性检查结果"""
    clip_i_score: float        # CLIP-I评分 (0-1)
    is_consistent: bool        # 是否达到阈值
    threshold: float           # 使用的阈值
    recommendation: str        # keep/regenerate/lock

class QualityMetrics(BaseModel):
    """图像质量指标"""
    sharpness: float           # 清晰度
    face_detected: bool        # 是否检测到人脸
    face_landmark_score: float # 人脸关键点评分
    composition_score: float   # 构图评分
```

#### core/image/image_postprocessor.py

图像后处理模块。对生成的图像进行裁剪、增强、格式转换等操作。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `def crop_to_portrait(image_path: str, output_path: str) -> str` | 裁剪为标准肖像比例 |
| `def remove_background(image_path: str, output_path: str) -> str` | 去除背景（用于3D生成输入） |
| `def enhance_resolution(image_path: str, scale: int = 2) -> str` | 超分辨率增强 |
| `def convert_format(input_path: str, target_format: str) -> str` | 格式转换 (png/jpeg) |
| `def add_watermark(image_path: str, text: str) -> str` | 添加水印（可选） |

---

### 6.5 3D生成层 (core/model3d/)

3D生成层本期仅定义接口和数据结构，不实现具体生成逻辑。所有方法返回 `NotImplementedError` 或HTTP 501。接口设计预留了多种3D生成方案的接入点。

#### core/model3d/base.py

3D生成抽象基类，定义所有3D生成Provider必须实现的接口。

```python
class BaseModel3DProvider(ABC):
    """3D模型生成Provider抽象基类"""

    @abstractmethod
    async def generate_from_image(
        self,
        image_path: str,
        params: Model3DGenerationParams
    ) -> Model3DResult:
        """从2D图像生成3D模型"""
        raise NotImplementedError("3D generation will be implemented in the next phase")

    @abstractmethod
    async def generate_from_text(
        self,
        feature_schema: CharacterFeatureSchema,
        params: Model3DGenerationParams
    ) -> Model3DResult:
        """从角色特征Schema直接生成3D模型（文本→3D）"""
        raise NotImplementedError("3D generation will be implemented in the next phase")

    @abstractmethod
    async def refine_model(
        self,
        model_path: str,
        refinement_params: dict
    ) -> Model3DResult:
        """精修3D模型（拓扑优化、纹理增强等）"""
        raise NotImplementedError("3D generation will be implemented in the next phase")

    @abstractmethod
    async def rig_model(
        self,
        model_path: str,
        rigging_params: dict
    ) -> Model3DResult:
        """骨骼绑定（rigging）"""
        raise NotImplementedError("3D generation will be implemented in the next phase")

    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """返回支持的输出格式：obj/fbx/stl/glb"""
        return ["obj", "fbx", "stl", "glb"]

    @abstractmethod
    async def get_generation_cost(self, params: Model3DGenerationParams) -> float:
        """估算生成成本"""
        raise NotImplementedError
```

```python
class Model3DGenerationParams(BaseModel):
    """3D生成参数"""
    output_format: str = "obj"          # obj/fbx/stl/glb
    quality_level: str = "medium"       # low/medium/high
    polygon_count: str = "medium"       # low/medium/high/ultra
    with_texture: bool = True           # 是否生成纹理
    with_rigging: bool = False          # 是否绑定骨骼（v2）
    with_animation: bool = False        # 是否生成动画（v2）
    symmetry: bool = True               # 是否对称
    base_image_path: str | None = None  # 源2D图像
    feature_schema: CharacterFeatureSchema | None = None  # 角色特征
    reference_views: list[str] | None = None  # 多视角参考图

class Model3DResult(BaseModel):
    """3D生成结果"""
    success: bool
    model_path: str | None
    texture_path: str | None
    format: str
    polygon_count: int | None
    generation_time: float | None
    cost: float | None
    error: str | None
```

#### core/model3d/interface.py

3D生成统一接口，封装Provider选择和调用逻辑。业务层通过此接口调用3D生成，无需关心具体Provider。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def generate_model3d(character_id: str, params: Model3DGenerationParams, db: Session) -> Model3DResult` | 主函数：生成3D模型（当前返回501） |
| `def get_provider(provider_name: str | None) -> BaseModel3DProvider` | 获取3D生成Provider（当前返回PlaceholderProvider） |
| `async def estimate_cost(params: Model3DGenerationParams) -> float` | 估算3D生成成本（当前返回0.0） |
| `def list_available_providers() -> list[str]` | 列出可用Provider（当前返回空列表） |
| `def is_3d_enabled() -> bool` | 检查3D功能是否已启用（当前返回False） |

#### core/model3d/placeholder.py

占位实现，所有方法均返回未实现错误。下次实现时替换为真实Provider。

```python
class PlaceholderModel3DProvider(BaseModel3DProvider):
    """3D生成占位Provider - 所有方法返回NotImplementedError"""

    async def generate_from_image(self, image_path: str, params: Model3DGenerationParams) -> Model3DResult:
        return Model3DResult(
            success=False,
            model_path=None,
            error="3D generation is not implemented yet. This interface is reserved for the next phase.",
            format=params.output_format,
            polygon_count=None,
            generation_time=None,
            cost=None
        )

    async def generate_from_text(self, feature_schema: CharacterFeatureSchema, params: Model3DGenerationParams) -> Model3DResult:
        return Model3DResult(success=False, error="Not implemented", ...)

    async def refine_model(self, model_path: str, refinement_params: dict) -> Model3DResult:
        return Model3DResult(success=False, error="Not implemented", ...)

    async def rig_model(self, model_path: str, rigging_params: dict) -> Model3DResult:
        return Model3DResult(success=False, error="Not implemented", ...)

    def get_supported_formats(self) -> list[str]:
        return ["obj", "fbx", "stl", "glb"]

    async def get_generation_cost(self, params: Model3DGenerationParams) -> float:
        return 0.0
```

---

### 6.6 流水线编排 (core/pipeline.py)

流水线编排模块，串联三层处理流程，提供一键执行入口。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `async def run_full_pipeline(novel_id: str, config: PipelineConfig, db: Session) -> PipelineResult` | 主函数：执行完整流水线 |
| `async def stage_text_extraction(novel_id: str, db: Session) -> list[CharacterFeatureSchema]` | 阶段一：文本理解 |
| `async def stage_image_generation(characters: list[CharacterFeatureSchema], config: PipelineConfig, db: Session) -> list[ImageResult]` | 阶段二：2D生成 |
| `async def stage_model3d_generation(characters: list[CharacterFeatureSchema], images: list[ImageResult], db: Session) -> list[Model3DResult]` | 阶段三：3D生成（返回未实现） |
| `async def run_stage(novel_id: str, stage: str, config: PipelineConfig, db: Session) -> Any` | 单独执行某一阶段 |
| `def create_pipeline_task(novel_id: str, config: PipelineConfig) -> str` | 创建异步任务，返回task_id |
| `async def get_pipeline_task_status(task_id: str) -> PipelineStatus` | 查询异步任务状态 |

```python
class PipelineConfig(BaseModel):
    """流水线配置"""
    art_style: str = "realistic"
    generate_grid: bool = True           # 是否生成四视图
    generate_multi_pose: bool = False    # 是否生成多姿势
    consistency_threshold: float = 0.85
    auto_lock: bool = True
    max_characters: int = 30             # 最多处理角色数
    skip_minor: bool = True              # 跳过路人角色
    enable_3d: bool = False              # 是否启用3D（默认False）

class PipelineResult(BaseModel):
    """流水线执行结果"""
    novel_id: str
    characters_extracted: int
    images_generated: int
    models3d_generated: int              # 当前始终为0
    consistency_avg: float | None
    total_cost: float | None
    duration: float
    errors: list[str]
    character_summaries: list[CharacterFeatureSchema]
```

**五步生成管线流程：**

```
Step 1: 抽取 (Extract)
  │  文本理解层 → CharacterFeatureSchema
  ▼
Step 2: 补全 (Supplement)
  │  身份原型填充 + 风格模板默认值
  │  信息不足字段用原型基线补全
  ▼
Step 3: 初稿 (Draft)
  │  Grid Method 生成四视图设定图
  │  从网格中选取正面视图作为基准
  ▼
Step 4: 锁定 (Lock)
  │  CLIP-I 一致性检查
  │  达到阈值(0.85)则锁定形象
  │  InstantID/PuLID 确保后续生成一致
  ▼
Step 5: 量产 (Mass Produce)
  │  基于锁定的基准形象
  │  ControlNet 姿态控制生成多姿势
  │  各姿势一致性目标 0.80+
```

---

### 6.7 模型提供商抽象 (models/)

#### models/providers/base.py

LLM Provider 基类，定义统一的LLM调用接口。所有Provider使用OpenAI兼容格式。

```python
class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类"""

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict | None = None
    ) -> str:
        """对话补全"""
        ...

    @abstractmethod
    async def chat_completion_with_json(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> dict:
        """对话补全（JSON输出模式）"""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """返回当前模型名"""
        ...

    @abstractmethod
    def get_context_window(self) -> int:
        """返回上下文窗口大小"""
        ...

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """估算文本Token数"""
        ...
```

#### models/providers/deepseek_provider.py

DeepSeek API Provider，主力LLM。通过OpenAI兼容格式调用DeepSeek-V3，国内直连无需代理。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `class DeepSeekProvider(BaseLLMProvider)` | DeepSeek Provider实现 |
| `def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com/v1", model: str = "deepseek-chat")` | 初始化 |
| `async def chat_completion(...) -> str` | 调用DeepSeek对话补全 |
| `async def chat_completion_with_json(...) -> dict` | 调用DeepSeek JSON模式输出 |
| `def get_model_name(self) -> str` | 返回 "deepseek-chat" |
| `def get_context_window(self) -> int` | 返回 64000（64K tokens） |
| `async def count_tokens(self, text: str) -> int` | 估算Token数（中文≈1.5字/token） |
| `async def estimate_cost(self, input_tokens: int, output_tokens: int) -> float` | 估算API调用成本 |

#### models/providers/openai_compat_provider.py

通用OpenAI兼容格式Provider，可适配任何兼容OpenAI API格式的模型服务（通义千问、Moonshot/Kimi等）。如需切换LLM，只需修改`.env`中的`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `class OpenAICompatProvider(BaseLLMProvider)` | 通用Provider实现 |
| `def __init__(self, api_key: str, base_url: str, model: str)` | 初始化 |
| `async def chat_completion(...) -> str` | 通用对话补全 |
| `async def chat_completion_with_json(...) -> dict` | 通用JSON模式 |

#### models/providers/factory.py

Provider工厂，根据配置创建对应的Provider实例。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `def create_llm_provider(settings: Settings) -> BaseLLMProvider` | 根据settings.llm_provider创建Provider |
| `def create_deepseek_provider(settings: Settings) -> DeepSeekProvider` | 创建DeepSeek Provider |
| `def create_openai_compat_provider(settings: Settings) -> OpenAICompatProvider` | 创建通用Provider |

#### models/comfyui/client.py

fal.ai 云端 ComfyUI 客户端，封装与 fal.ai API 的交互。fal.ai 在云端运行 ComfyUI 工作流，支持 FLUX/SD 模型和 InstantID/ControlNet 节点，无需本地安装 ComfyUI。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `class FalComfyUIClient` | fal.ai 云端ComfyUI客户端 |
| `def __init__(self, api_key: str)` | 初始化，传入fal.ai API Key |
| `async def queue_workflow(self, workflow_json: dict, app_name: str) -> str` | 提交工作流到fal.ai云端，返回request_id |
| `async def queue_workflow_with_inputs(self, workflow_json: dict, inputs: dict) -> str` | 提交工作流并上传输入图像 |
| `async def get_result(self, request_id: str, timeout: int = 300) -> FalResult` | 轮询并获取执行结果 |
| `async def upload_image(self, image_path: str) -> str` | 上传参考图像到fal.ai |
| `async def upload_image_bytes(self, image_bytes: bytes) -> str` | 上传图像字节数据 |
| `async def list_available_apps(self) -> list[str]` | 列出可用的ComfyUI应用 |
| `def estimate_cost(self, workflow_type: str) -> float` | 估算单次执行成本 |

```python
class FalResult(BaseModel):
    """fal.ai执行结果"""
    success: bool
    image_urls: list[str]       # 生成图像的URL
    execution_time: float       # 执行耗时（秒）
    cost: float                 # 本次执行成本
    error: str | None
```

#### models/comfyui/workflows.py

预定义ComfyUI工作流JSON模板。存储为Python字典，运行时填充参数。

**关键常量/函数：**

| 名称/函数签名 | 说明 |
|---------------|------|
| `PORTRAIT_WORKFLOW` | 肖像生成工作流模板 |
| `GRID_SHEET_WORKFLOW` | 四视图网格生成工作流模板 |
| `MULTI_POSE_WORKFLOW` | 多姿势生成工作流模板 |
| `INSTANTID_WORKFLOW` | InstantID一致性生成工作流模板 |
| `def get_workflow(name: str) -> dict` | 按名称获取工作流模板 |

每个工作流模板包含完整的ComfyUI节点定义：CheckpointLoader、CLIPTextEncode、EmptyLatentImage、KSampler、VAEDecode、SaveImage等节点，以及InstantID/ControlNet节点的占位。

#### models/comfyui/param_filler.py

JSON参数填充器。将业务参数填充到ComfyUI工作流JSON模板的对应节点中。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `def fill_workflow(template: dict, params: WorkflowParams) -> dict` | 主函数：填充工作流参数 |
| `def fill_text_encoders(workflow: dict, positive: str, negative: str) -> dict` | 填充CLIP Text Encode节点 |
| `def fill_sampler(workflow: dict, steps: int, cfg: float, sampler_name: str, scheduler: str) -> dict` | 填充KSampler节点 |
| `def fill_image_size(workflow: dict, width: int, height: int) -> dict` | 填充EmptyLatentImage节点 |
| `def fill_checkpoint(workflow: dict, model_name: str) -> dict` | 填充CheckpointLoader节点 |
| `def fill_instantid(workflow: dict, reference_image: str, weight: float) -> dict` | 填充InstantID节点 |
| `def fill_controlnet(workflow: dict, pose_image: str, strength: float) -> dict` | 填充ControlNet节点 |
| `def fill_lora(workflow: dict, lora_name: str, strength: float) -> dict` | 填充LoRA节点 |

```python
class WorkflowParams(BaseModel):
    """工作流填充参数"""
    positive_prompt: str
    negative_prompt: str
    checkpoint: str = "flux1-dev.safetensors"
    steps: int = 30
    cfg: float = 7.0
    sampler: str = "dpmpp_2m"
    scheduler: str = "karras"
    width: int = 1024
    height: int = 1024
    instantid_reference: str | None = None
    instantid_weight: float = 0.8
    controlnet_pose: str | None = None
    controlnet_strength: float = 0.7
    lora_name: str | None = None
    lora_strength: float = 0.8
    seed: int | None = None  # None=random
```

#### models/schemas/ 目录

| 文件 | 关键类 | 说明 |
|------|--------|------|
| `character_feature.py` | `CharacterFeatureSchema`及所有子Block | 角色视觉特征Schema（见5.2节完整定义） |
| `novel_metadata.py` | `NovelMetadata`, `ChapterInfo` | 小说元数据结构 |
| `generation_config.py` | `GenerationConfig`, `ArtStylePreset` | 生成配置和画风预设 |

---

### 6.8 数据层 (data/)

#### data/database.py

数据库连接管理，使用SQLAlchemy。

**关键函数：**

| 函数签名 | 说明 |
|----------|------|
| `engine = create_engine(settings.database_url)` | 创建数据库引擎 |
| `SessionLocal = sessionmaker(bind=engine)` | 创建会话工厂 |
| `def init_db() -> None` | 初始化数据库，创建所有表 |
| `def get_db() -> Generator[Session, None, None]` | 获取数据库会话生成器 |
| `def drop_db() -> None` | 删除所有表（开发用） |

#### data/models.py

SQLAlchemy ORM模型定义，对应5.1节的5个数据表。

**关键类：**

| 类名 | 对应表 | 说明 |
|------|--------|------|
| `NovelORM` | novels | 小说ORM模型 |
| `CharacterORM` | characters | 角色ORM模型 |
| `UserPreferenceORM` | user_preferences | 用户偏好ORM模型 |
| `GeneratedImageORM` | generated_images | 生成图像ORM模型 |
| `GeneratedModel3DORM` | generated_models3d | 3D模型ORM模型（预留） |
| `PromptTemplateORM` | prompt_templates | Prompt模板版本ORM模型（线上修改/回滚） |
| `IdentityPrototypeORM` | identity_prototypes | 身份原型版本ORM模型（线上修改/回滚/LLM生成） |

每个ORM类定义了表结构（列名、类型、约束）和基本查询方法。

`PromptTemplateORM` 表结构设计：

```python
class PromptTemplateORM(Base):
    """Prompt模板版本表 — 每次修改新增一行,支持版本回滚"""
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_name = Column(String(100), nullable=False, index=True)  # 如 "extraction_system"
    version = Column(Integer, nullable=False)                        # 版本号,从1递增
    content = Column(Text, nullable=False)                           # Prompt模板内容
    is_active = Column(Boolean, default=False, nullable=False)       # 是否为当前活跃版本
    notes = Column(String(500), default="")                          # 修改备注
    created_at = Column(DateTime, default=datetime.utcnow)           # 创建时间

    # 唯一约束: 同一模板名+版本号唯一
    __table_args__ = (
        UniqueConstraint("template_name", "version", name="uq_template_version"),
    )
```

**设计要点：**
- 同一 `template_name` 可有多行记录，每个 `version` 一行
- 同一模板只有一行 `is_active=True`（当前活跃版本）
- 修改操作 → 新增一行（version+1, is_active=True），旧活跃版本设为 is_active=False
- 回滚操作 → 目标版本设为 is_active=True，当前活跃版本设为 is_active=False
- `notes` 字段记录每次修改的原因，便于审计

`IdentityPrototypeORM` 表结构与 `PromptTemplateORM` 同构，额外增加 `source` 字段记录原型来源：

```python
class IdentityPrototypeORM(Base):
    """身份原型版本表 — 与 PromptTemplateORM 同构,额外记录来源"""
    __tablename__ = "identity_prototypes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    identity_label = Column(String(100), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content = Column(JSON, nullable=False)                  # 原型特征JSON(含_meta)
    is_active = Column(Boolean, default=False, nullable=False)
    source = Column(String(50), default="seed_file")        # seed_file/llm_generated/manual_edit
    notes = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("identity_label", "version", name="uq_prototype_version"),
    )
```

#### data/repositories/ 目录

Repository模式实现，封装数据访问逻辑，业务层通过Repository操作数据。

#### data/repositories/novel_repo.py

| 函数签名 | 说明 |
|----------|------|
| `class NovelRepository` | 小说数据访问类 |
| `def __init__(self, db: Session)` | 初始化 |
| `def create(self, title: str, raw_text: str, **kwargs) -> NovelORM` | 创建小说记录 |
| `def get_by_id(self, novel_id: str) -> NovelORM | None` | 按ID查询 |
| `def list_all(self, skip: int = 0, limit: int = 20) -> list[NovelORM]` | 分页查询 |
| `def update_status(self, novel_id: str, status: str, **extra) -> None` | 更新处理状态 |
| `def update_memory_snapshot(self, novel_id: str, snapshot: dict) -> None` | 更新记忆快照 |
| `def delete(self, novel_id: str) -> bool` | 删除小说（级联删除关联数据） |
| `def get_processing_progress(self, novel_id: str) -> dict` | 获取处理进度 |

#### data/repositories/character_repo.py

| 函数签名 | 说明 |
|----------|------|
| `class CharacterRepository` | 角色数据访问类 |
| `def create(self, novel_id: str, name: str, **kwargs) -> CharacterORM` | 创建角色记录 |
| `def get_by_id(self, character_id: str) -> CharacterORM | None` | 按ID查询 |
| `def list_by_novel(self, novel_id: str, role_type: str | None = None) -> list[CharacterORM]` | 查询小说下角色 |
| `def update_features(self, character_id: str, features: CharacterFeatureSchema) -> None` | 更新角色特征 |
| `def lock(self, character_id: str) -> None` | 锁定角色特征 |
| `def unlock(self, character_id: str) -> None` | 解锁角色特征 |
| `def get_by_name(self, novel_id: str, name: str) -> CharacterORM | None` | 按名称查询 |
| `def batch_create(self, characters: list[dict]) -> list[CharacterORM]` | 批量创建 |

#### data/repositories/image_repo.py

| 函数签名 | 说明 |
|----------|------|
| `class ImageRepository` | 图像数据访问类 |
| `def create(self, character_id: str, image_type: str, file_path: str, **kwargs) -> GeneratedImageORM` | 创建图像记录 |
| `def get_by_id(self, image_id: str) -> GeneratedImageORM | None` | 按ID查询 |
| `def list_by_character(self, character_id: str) -> list[GeneratedImageORM]` | 查询角色所有图像 |
| `def update_clip_score(self, image_id: str, score: float) -> None` | 更新CLIP-I评分 |
| `def lock(self, image_id: str) -> None` | 锁定图像 |
| `def get_locked_image(self, character_id: str) -> GeneratedImageORM | None` | 获取角色锁定的基准图像 |
| `def delete(self, image_id: str) -> bool` | 删除图像记录 |

#### data/repositories/model3d_repo.py（预留）

| 函数签名 | 说明 |
|----------|------|
| `class Model3DRepository` | 3D模型数据访问类（预留） |
| `def create(self, character_id: str, **kwargs) -> GeneratedModel3DORM` | 创建3D模型记录（表结构已建，数据为空） |
| `def get_by_id(self, model_id: str) -> GeneratedModel3DORM | None` | 按ID查询 |
| `def list_by_character(self, character_id: str) -> list[GeneratedModel3DORM]` | 查询角色3D模型（返回空列表） |
| `def update_status(self, model_id: str, status: str) -> None` | 更新状态 |

#### data/repositories/prompt_repo.py

Prompt模板数据访问类，提供版本管理、回滚、查询等功能。是 `PromptManager` 的数据层支撑。

| 函数签名 | 说明 |
|----------|------|
| `class PromptRepository` | Prompt模板数据访问类 |
| `def __init__(self, db: Session)` | 初始化 |
| `async def create_version(self, template_name: str, content: str, notes: str = "") -> PromptTemplateORM` | 创建新版本：旧活跃版本置为inactive，新版本version+1并设为active |
| `async def get_active_version(self, template_name: str) -> PromptTemplateORM | None` | 获取模板的当前活跃版本 |
| `async def get_version(self, template_name: str, version: int) -> PromptTemplateORM | None` | 获取指定版本 |
| `async def list_versions(self, template_name: str) -> list[PromptTemplateORM]` | 列出模板所有历史版本（按版本号降序） |
| `async def list_active_versions(self) -> list[PromptTemplateORM]` | 列出所有模板的活跃版本（用于缓存加载） |
| `async def set_active_version(self, template_name: str, version: int) -> None` | 设置活跃版本（回滚用）：取消当前活跃，激活目标版本 |
| `async def list_template_names(self) -> list[str]` | 列出所有模板名称（去重） |
| `async def get_latest_version_number(self, template_name: str) -> int` | 获取模板的最大版本号（新版本号=此值+1） |

**版本创建事务流程：**

```python
async def create_version(self, template_name: str, content: str, notes: str = ""):
    """创建新版本(事务操作)"""
    async with self._db.begin():
        # 1. 获取当前最大版本号
        max_version = await self.get_latest_version_number(template_name)
        new_version = max_version + 1

        # 2. 取消当前活跃版本
        await self._db.execute(
            update(PromptTemplateORM)
            .where(
                PromptTemplateORM.template_name == template_name,
                PromptTemplateORM.is_active == True
            )
            .values(is_active=False)
        )

        # 3. 插入新版本并设为活跃
        new_record = PromptTemplateORM(
            template_name=template_name,
            version=new_version,
            content=content,
            is_active=True,
            notes=notes
        )
        self._db.add(new_record)

    return new_record
```

#### data/repositories/prototype_repo.py

身份原型数据访问类，与 `PromptRepository` 同构，额外支持 LLM 生成原型的缓存写入。

| 函数签名 | 说明 |
|----------|------|
| `class PrototypeRepository` | 身份原型数据访问类 |
| `def __init__(self, db: Session)` | 初始化 |
| `async def create_version(self, identity_label: str, content: dict, source: str = "manual_edit", notes: str = "") -> IdentityPrototypeORM` | 创建新版本，source 记录来源 |
| `async def get_active_version(self, identity_label: str) -> IdentityPrototypeORM | None` | 获取当前活跃版本 |
| `async def get_version(self, identity_label: str, version: int) -> IdentityPrototypeORM | None` | 获取指定版本 |
| `async def list_versions(self, identity_label: str) -> list[IdentityPrototypeORM]` | 列出所有历史版本 |
| `async def list_active_versions(self) -> list[IdentityPrototypeORM]` | 列出所有活跃版本（缓存加载用） |
| `async def set_active_version(self, identity_label: str, version: int) -> None` | 设置活跃版本（回滚用） |
| `async def list_identity_labels(self) -> list[str]` | 列出所有身份标签（去重） |
| `async def find_similar(self, identity_label: str) -> list[str]` | 模糊匹配相似身份（兜底机制用） |

---

### 6.9 工具层 (utils/)

#### utils/text_utils.py

通用文本处理工具。

| 函数签名 | 说明 |
|----------|------|
| `def count_chinese_chars(text: str) -> int` | 统计中文字符数 |
| `async def load_prompt(template_name: str, **kwargs) -> str` | 加载Prompt模板并填充占位符（通过PromptManager从缓存/DB/文件三级获取） |
| `def truncate_text(text: str, max_chars: int, suffix: str = "...") -> str` | 截断文本 |
| `def extract_sentence(text: str, position: int) -> str` | 提取指定位置所在的句子 |
| `def count_tokens_estimate(text: str) -> int` | 估算Token数（中文≈1.5字/token） |
| `def clean_text(text: str) -> str` | 清理文本（去除多余空行、特殊字符） |
| `def split_paragraphs(text: str) -> list[str]` | 按段落切分 |
| `def extract_placeholders(content: str) -> list[str]` | 提取模板中的占位符列表（如 `{text_chunk}`），用于预览和校验 |

**`load_prompt()` 实现逻辑：**

```python
async def load_prompt(template_name: str, **kwargs) -> str:
    """
    加载Prompt模板并填充占位符。

    调用链: PromptManager.get_prompt() → 缓存 → DB → 文件
    获取到模板内容后,用 kwargs 填充占位符。
    """
    # 1. 通过 PromptManager 获取模板内容（缓存→DB→文件三级回退）
    content = await prompt_manager.get_prompt(template_name)

    # 2. 填充占位符
    if kwargs:
        try:
            content = content.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Prompt模板 '{template_name}' 缺少占位符参数: {e}")

    return content
```

#### utils/image_utils.py

图像处理工具。

| 函数签名 | 说明 |
|----------|------|
| `def load_image(path: str) -> Image` | 加载图像 |
| `def save_image(image: Image, path: str, format: str = "PNG") -> None` | 保存图像 |
| `def resize_image(image: Image, width: int, height: int) -> Image` | 调整尺寸 |
| `def get_image_size(path: str) -> tuple[int, int]` | 获取图像尺寸 |
| `def calculate_file_hash(path: str) -> str` | 计算文件MD5（去重用） |
| `def create_thumbnail(path: str, size: tuple[int, int] = (256, 256)) -> str` | 创建缩略图 |
| `def blend_images(base: str, overlay: str, alpha: float) -> str` | 混合图像 |

#### utils/chinese_nlp.py

中文NLP专用工具。

| 函数签名 | 说明 |
|----------|------|
| `def init_jieba() -> None` | 初始化jieba分词器，加载自定义词典 |
| `def segment(text: str) -> list[str]` | 中文分词 |
| `def pos_tag(text: str) -> list[tuple[str, str]]` | 词性标注 |
| `def extract_person_names(text: str) -> list[str]` | 提取人名（基于词性标注） |
| `def detect_metaphor(text: str) -> list[MetaphorMatch]` | 检测中文比喻描写（如"面如冠玉"） |
| `def metaphor_to_visual(metaphor: str) -> str` | 比喻→视觉标签映射 |
| `def is_formal_name(name: str) -> bool` | 判断是否为正式姓名（姓+名模式） |
| `def is_title_or_honorific(name: str) -> bool` | 判断是否为称谓/尊称（如"林教头"） |

```python
class MetaphorMatch(BaseModel):
    """比喻匹配"""
    original_text: str       # 原文比喻
    visual_tag: str          # 映射的视觉标签
    field: str               # 对应的Schema字段
    position: int            # 位置
```

#### utils/logger.py

日志配置。

| 函数签名 | 说明 |
|----------|------|
| `def setup_logger(name: str, level: str = "INFO") -> logging.Logger` | 配置日志器 |
| `def get_logger(name: str) -> logging.Logger` | 获取日志器 |

---

## 7 核心算法设计

### 7.1 中文别名合并算法

**问题**：中文小说中同一角色有多种称呼，如"林冲"、"林教头"、"豹子头"、"林冲"、"他"均指同一人。

**算法流程：**

```
1. 实体预扫描：jieba词性标注提取所有人名候选
2. 频次过滤：出现<2次的人名候选暂存，不直接进入合并
3. 规则初筛：
   a. 姓氏匹配："林冲"和"林教头"共享姓氏"林"
   b. 称谓模式：识别"X教头"、"X大官人"、"X娘子"等模式
   c. 字号匹配："豹子头"可能是某人的绰号
4. LLM精判断：将规则初筛的候选组送入LLM，判断是否为同一人
5. 冲突解决：一个别名被分到多组时，取LLM置信度最高的分组
6. 选择主名：优先全名 > 最长名称 > 最高频名称
```

### 7.2 增量记忆体系

**问题**：百万字小说无法一次性喂入LLM，需要分块处理；且后续可能追加新章节，不能重新处理全文。

**核心思路**：四层记忆体系是整个文本理解层的核心架构。它将百万字小说拆分为1.2万字/块，每块独立送入DeepSeek API处理，提取到的特征增量合并到记忆体系中。这意味着不需要2M上下文窗口的昂贵LLM——每块约8K tokens，加上记忆注入的已知角色信息约2-4K tokens，总消耗控制在12K tokens以内，DeepSeek的64K窗口绰绰有余。单块API调用成本约$0.002，百万字小说约80块，文本理解总成本约$0.16。

**四层记忆设计：**

```
L1 事实记忆（Facts）
  ├── 存储：每个角色的 CharacterFeatureSchema
  ├── 更新：新块提取的特征 merge 到已有特征
  └── 查询：构建Prompt时注入角色的已知特征

L2 关系记忆（Relations）
  ├── 存储：角色关系邻接表 {角色A: [(角色B, "师徒"), ...]}
  ├── 更新：新块中检测到的关系追加到邻接表
  └── 查询：提取某角色特征时，注入其关系网络作为上下文

L3 事件记忆（Events）
  ├── 存储：关键事件列表 [{描述, 参与者, 章节, 情感}]
  ├── 更新：新块中检测到的关键事件追加
  └── 查询：为角色特征提取提供事件上下文

L4 上下文记忆（Context）
  ├── 存储：当前处理位置、待解决问题、矛盾标记
  ├── 更新：每次处理新块时更新
  └── 查询：恢复处理时加载，支持断点续传
```

**增量更新流程：**

```
新文本块到达
  │
  ├──► 扫描实体 → 与L1已知角色匹配
  │
  ├──► 提取特征 → merge到L1事实记忆
  │     └── 矛盾检测 → 记录到L4
  │
  ├──► 检测关系 → 更新L2关系记忆
  │
  ├──► 检测事件 → 更新L3事件记忆
  │
  └──► 更新L4处理位置
```

### 7.3 身份原型优先级覆盖

**三级优先级：**

```
Priority 1 (最高): 原文明确描写
  → 原文中直接描述的特征，如"此人面如冠玉"

Priority 2 (中): 身份原型基线
  → 原型模板中的默认特征，如 beggar → {build: thin, clothing: ragged}

Priority 3 (最低): 风格模板默认值
  → 画风相关的默认值，如 realistic → {skin_tone: average}
```

**覆盖逻辑：**

```
for each field in CharacterFeatureSchema:
    if field has explicit text description:
        use text value (Priority 1)
        if field contradicts prototype baseline:
            mark contradiction
            generate contrast prompt
            adjust weight (+1.2 ~ +1.5)
    elif field has prototype value:
        use prototype value (Priority 2)
    else:
        use style template default (Priority 3)
```

### 7.4 身份原型效果保障机制

**原型验证流水线（"纯原型生成测试"）：**

在无原文描述的情况下，仅用原型特征生成角色图像，人工评估视觉辨识度：

```
身份标签 → 原型特征JSON → FeaturePromptMapper → fal.ai图像生成 → 人工评分(1-5)
```

| 评分 | 标准 | 处理 |
|------|------|------|
| 5分 | 一眼认出身份，视觉特征准确 | 通过 |
| 3分 | 大致方向正确，但不够典型 | 标记待优化 |
| 1分 | 完全看不出身份 | 必须修正 |

MVP阶段对20个身份跑一轮验证，成本约$1-2（20张图 × $0.05/张）。

**原型覆盖率监控：**

运行小说后分析 `PrototypeUsageStats` 统计：

| 指标 | 阈值 | 含义与动作 |
|------|------|-----------|
| `prototype_coverage > 60%` | 警告 | 原文描写太稀疏，原型质量决定效果，需加强原型 |
| `contradictions` 频繁出现 | 警告 | 原型与该类小说常见设定冲突，需调整原型 |
| `from_style_default > 30%` | 警告 | 原型覆盖不足，需新增身份标签 |

**反差场景专项测试用例：**

| 身份 | 原文反差描述 | 期望生成效果 |
|------|-------------|-------------|
| 乞丐 | 总是干干净净 | 异常整洁的乞丐，突出反差感 |
| 和尚 | 满头长发 | 穿僧袍但留长发的怪僧 |
| 将军 | 文弱书生气质 | 穿铠甲但气质文弱的将领 |
| 皇帝 | 微服私访穿布衣 | 穿平民衣服但有贵气的帝王 |

MVP第5周（集成测试阶段）统一验证 `build_contrast_prompt()` 和 `adjust_prompt_weights()` 的效果。

### 7.5 特征到Prompt映射算法

**映射规则：**

| Schema字段 | Prompt片段示例 | 权重 |
|------------|----------------|------|
| identity.gender | "1boy" / "1girl" | 1.5 |
| identity.age_range | "young man" / "middle-aged man" | 1.3 |
| face.face_shape | "oval face" / "square jaw" | 1.1 |
| face.eye_shape | "phoenix eyes" / "almond eyes" | 1.2 |
| face.skin_tone | "pale skin" / "tanned skin" | 1.2 |
| hair.length + hair.color | "long black hair" | 1.3 |
| clothing.style + clothing.primary_color | "wearing dark blue Hanfu robe" | 1.2 |
| body.build | "slender build" / "muscular physique" | 1.1 |
| distinctive_marks | "scar across left eye" | 1.4 |
| color_palette.overall_tone | "warm color palette" | 1.0 |

**Prompt组装顺序：**

```
[画风模板] + [身份锚定] + [面部特征] + [发型] + [体型] + [服装] + [特殊标记] + [色彩方案] + [反差提示]
```

### 7.6 CLIP-I 一致性检查

**算法：**

```
1. 使用 CLIP ViT-L/14 提取图像特征向量
2. 计算参考图像与目标图像特征向量的余弦相似度
3. 相似度范围 [0, 1]，越高越一致
4. 阈值设定：
   - 正面肖像一致性: ≥ 0.85 (锁定标准)
   - 多姿势一致性: ≥ 0.80 (可接受)
   - 四视图网格内一致性: ≥ 0.82
```

**决策逻辑：**

```
if clip_i_score >= 0.90:
    → 锁定角色形象 (auto_lock)
elif clip_i_score >= 0.85:
    → 达标，可锁定或继续优化
elif clip_i_score >= 0.75:
    → 需要重新生成，调整参数
else:
    → 严重不一致，检查特征提取是否有误
```

### 7.7 Grid Method 四视图生成

**核心思路：** 在一次生成请求中生成包含多视角的角色设定网格，利用AI一次生成的统一潜空间上下文保持一致性。

**关键Prompt结构：**

```
positive: "character sheet, multiple views, [front view], [side profile], 
           [back view], [full body], [角色特征描述], white background, 
           neutral pose, reference sheet style, 2x2 grid layout"

negative: "varying appearance, inconsistent features, different characters, 
           complex background"
```

**生成参数：**

```
分辨率: 2048x2048 (2x2网格，每格约1024x1024)
Steps: 35 (略高于单图，确保细节)
CFG: 7.5
Sampler: DPM++ 2M Karras
```

**后处理：** 将2048x2048网格图切分为4张1024x1024单视图，选择正面视图作为基准。

---

## 8 Prompt工程

### 8.1 角色特征提取Prompt

**系统Prompt (`extraction_system.txt`) 设计要点：**

- 明确角色：你是中文小说角色特征提取专家
- 输出格式约束：必须输出符合 CharacterFeatureSchema 的JSON
- 只提取视觉相关特征：不提取性格、能力等非视觉信息
- 溯源要求：每个字段必须附带原文引用
- 置信度要求：对每个字段标注置信度 (high/medium/low)
- 处理留白：原文未描述的字段标注 null，不要编造
- 增量提示：已知的特征会提供，只需提取新信息或更新

**用户Prompt (`extraction_user.txt`) 模板：**

```
小说文本片段：
{text_chunk}

已知角色信息：
{known_characters}

角色名：{character_name}

请从上述文本中提取角色"{character_name}"的视觉特征。
如果该角色在已知信息中已有记录，请仅提取新增或需要更新的特征。
输出格式必须为JSON，符合CharacterFeatureSchema。
每个非null字段必须包含text_evidence（原文引用）和confidence（置信度）。
```

### 8.2 中文比喻映射词典

系统内置中文古典文学常见比喻到视觉标签的映射词典：

| 原文比喻 | 映射字段 | 视觉标签 |
|----------|----------|----------|
| 面如冠玉 | face.skin_tone | pale, smooth, fair skin |
| 面若桃花 | face.skin_tone | rosy, pinkish skin |
| 面如锅底 | face.skin_tone | dark, very dark skin |
| 剑眉星目 | face.eyebrow, face.eye_shape | sharp angled eyebrows, bright starry eyes |
| 柳腰 | body.build | slender waist, slim build |
| 虎背熊腰 | body.build | broad shoulders, muscular build |
| 鹤发童颜 | hair.color, face.skin_tone | white hair, youthful face |
| 明眸皓齿 | face.eye_shape, face.mouth | bright eyes, white teeth |
| 身长八尺 | body.height_relative | tall stature |
| 蜂腰猿背 | body.build | narrow waist, broad back |

运行时由 `chinese_nlp.detect_metaphor()` 检测比喻，`chinese_nlp.metaphor_to_visual()` 转换。

### 8.3 身份原型覆盖Prompt

**矛盾处理Prompt (`identity_override.txt`)：**

```
角色身份：{identity_label}
身份原型特征：{prototype_features}
原文描述特征：{text_features}
检测到的矛盾：{contradictions}

请生成一段英文Prompt描述，准确反映这个角色的外貌。
关键要求：原文描述优先于身份原型。如果原文说一个乞丐是干净的，
就必须描述为一个异常干净的乞丐，突出这种反差感。
对于原文未提及的特征，可以保留身份原型的默认值。
```

### 8.4 Prompt管理系统

借鉴 `llm-rag-server` 的 Prompt 管理设计，本项目实现了完整的 Prompt 生命周期管理系统，支持线上热修改和版本回滚。

**与 llm-rag-server 的设计对比：**

| 维度 | llm-rag-server | 本项目 |
|------|---------------|--------|
| 存储方式 | 数据库（MySQL） | 数据库（SQLite）+ 文件种子 |
| 版本控制 | template_id + 数据库管理 | version + is_active 标记 |
| 缓存机制 | PromptInitializer 内存缓存 | PromptManager 内存缓存 |
| 条件拼接 | build_complete_prompt() 分段组装 | MVP阶段为整模板，v2支持分段 |
| 预览功能 | prompt_preview_service 独立服务 | preview_prompt API接口 |
| 管理API | admin/templates.py | api/routes/prompts.py |
| 回滚能力 | 通过版本管理实现 | 显式 rollback API |

**核心设计决策：**

1. **文件为种子而非运行时源**：`config/prompts/*.txt` 仅在首次启动时导入数据库，之后数据库为唯一运行时源。这确保了线上修改不会丢失，同时保留了文件作为代码版本控制和初始化手段。

2. **三级回退机制**：`get_prompt()` 的调用链为 `内存缓存 → 数据库活跃版本 → 文件回退`。数据库不可用时自动降级到文件读取，保证系统可用性。

3. **版本不可变原则**：修改操作只新增版本，不修改历史版本内容。回滚操作仅切换 `is_active` 标记，不删除任何版本。这确保了完整的修改审计链。

4. **缓存自动刷新**：每次 `update_prompt()` 和 `rollback()` 后自动调用 `_reload_cache()`，确保内存缓存与数据库一致。也提供手动 `refresh()` API。

**线上修改工作流：**

```
1. 管理员调用 GET /api/prompts/{template_name}
   → 查看当前活跃版本内容和占位符列表

2. 管理员调用 POST /api/prompts/{template_name}/preview
   → 传入修改后的内容 + 样例数据
   → 系统渲染并返回预览效果（不保存）

3. 管理员确认效果后调用 PUT /api/prompts/{template_name}
   → 传入修改内容和修改备注
   → 系统创建新版本，自动刷新缓存
   → 下次 load_prompt() 调用即使用新版本

4. 如效果不佳，调用 POST /api/prompts/{template_name}/rollback/{version}
   → 回滚到指定历史版本
   → 自动刷新缓存，立即生效
```

**典型使用场景：**

- 角色特征提取Prompt调优：发现提取质量下降时，对比历史版本，回滚到效果最好的版本
- 别名合并逻辑调整：新增小说类型后，调整别名合并Prompt的判断规则
- 身份覆盖矛盾处理：微调矛盾处理的Prompt措辞，预览确认后发布
- 新增Prompt模板：在 `config/prompts/` 新增文件，重启服务自动导入数据库

---

## 9 3D生成层接口预留

### 9.1 接口设计原则

3D生成层本期仅定义接口，不实现具体逻辑。接口设计遵循以下原则：

- **Provider可插拔**：通过抽象基类支持未来接入不同3D生成服务
- **多输入模式**：支持从2D图像生成和从特征Schema直接生成两种模式
- **格式灵活**：支持OBJ/FBX/STL/GLB多种输出格式
- **渐进式质量**：支持low/medium/high三级质量
- **扩展预留**：为骨骼绑定、动画生成预留接口（v2功能）

### 9.2 已预留的接口清单

| 接口 | 位置 | 说明 |
|------|------|------|
| `BaseModel3DProvider.generate_from_image()` | `core/model3d/base.py` | 2D图像→3D模型 |
| `BaseModel3DProvider.generate_from_text()` | `core/model3d/base.py` | 特征Schema→3D模型 |
| `BaseModel3DProvider.refine_model()` | `core/model3d/base.py` | 3D模型精修 |
| `BaseModel3DProvider.rig_model()` | `core/model3d/base.py` | 骨骼绑定 |
| `interface.generate_model3d()` | `core/model3d/interface.py` | 统一入口函数 |
| `interface.get_provider()` | `core/model3d/interface.py` | Provider选择 |
| `interface.estimate_cost()` | `core/model3d/interface.py` | 成本估算 |
| `api/routes/models3d.py` | API路由 | HTTP接口 |
| `data/repositories/model3d_repo.py` | 数据访问 | 数据持久化 |
| `GeneratedModel3DORM` | `data/models.py` | 数据库表 |
| `Model3DParams` / `Model3DResponse` | `api/schemas/model3d_schemas.py` | 请求响应模型 |

### 9.3 下次实现路径建议

```
阶段1: 接入云端3D生成API（Tripo / Meshy / Stability）
  → 实现 generate_from_image()
  → 支持 OBJ/GLB 输出
  → 成本约 $4.5/角色

阶段2: 多视角输入增强
  → 利用四视图网格图提升3D生成质量
  → 实现 reference_views 参数

阶段3: 本地3D生成
  → 评估 TripoSR / CRM 等开源方案（如需本地3D生成）
  → 也可继续使用云端API（Meshy/Tripo等）

阶段4: 后处理管线
  → 拓扑优化（简化面数）
  → UV展开与纹理烘焙
  → 骨骼自动绑定
```

### 9.4 3D生成Provider候选方案（下次评估）

| 方案 | 类型 | 输入 | 输出 | 预估成本 | 备注 |
|------|------|------|------|----------|------|
| Tripo | 云端API | 单图/多图 | OBJ/FBX/GLB | ~$0.15/次 | 中景NPC级质量 |
| Meshy | 云端API | 单图+文本 | OBJ/FBX/STL/GLB | ~$0.20/次 | 纹理质量较好 |
| Stability SV3D | 云端API | 单图 | MP4/PLY | ~$0.10/次 | 开源模型托管 |
| TripoSR | 开源本地 | 单图 | OBJ | 免费 | 需8GB+显存 |
| CRM | 开源本地 | 多视图 | OBJ | 免费 | 需要四视图输入 |

---

## 10 配置管理

### 10.1 环境变量配置 (.env)

```ini
# === LLM 配置 ===
LLM_PROVIDER=deepseek             # deepseek / openai_compat
LLM_API_KEY=your_deepseek_api_key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat           # DeepSeek-V3

# === 图像生成配置 ===
IMAGE_PROVIDER=fal                # fal / replicate
FAL_API_KEY=your_fal_api_key
REPLICATE_API_TOKEN=

# === 3D 生成配置（预留，本期不使用） ===
MODEL3D_PROVIDER=                # tripo / meshy / stability
MODEL3D_API_KEY=

# === 数据库 ===
DATABASE_URL=sqlite:///./data/novel_char.db

# === 一致性 ===
CONSISTENCY_THRESHOLD=0.85
AUTO_LOCK_ENABLED=true

# === 文本处理 ===
MAX_CHUNK_SIZE=12000
CHUNK_OVERLAP=500
MAX_CHARACTERS_PER_NOVEL=100

# === 图像生成 ===
DEFAULT_ART_STYLE=realistic
IMAGE_OUTPUT_DIR=output/images
DEFAULT_RESOLUTION=1024x1024
```

### 10.2 Provider 切换策略

系统全链路使用云端API，通过修改`.env`配置即可切换Provider，业务代码零改动：

| 场景 | LLM_PROVIDER | IMAGE_PROVIDER | 说明 |
|------|-------------|----------------|------|
| 默认方案（推荐） | deepseek | fal | DeepSeek API + fal.ai云端ComfyUI，国内直连，成本最低 |
| 通义千问替代 | openai_compat | fal | 切换LLM到通义千问API，修改LLM_BASE_URL即可 |
| Kimi替代 | openai_compat | fal | 切换LLM到Moonshot/Kimi API |
| Replicate替代 | deepseek | replicate | 切换图像生成到Replicate平台 |

Provider工厂(`models/providers/factory.py`)根据配置自动创建对应Provider。所有Provider均使用OpenAI兼容格式，切换时只需修改`.env`中的`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`三个字段。

---

## 11 开发计划与里程碑

### 11.1 MVP阶段（4-5周，约3500-4000行Python）

#### 第1周：基础设施搭建

| 任务 | 文件 | 代码量 |
|------|------|--------|
| 项目骨架与依赖配置 | requirements.txt, .env.example | 50行 |
| 数据库与ORM模型（含PromptTemplateORM） | data/database.py, data/models.py | 250行 |
| 全局配置管理 | config/settings.py | 80行 |
| Prompt管理系统（核心） | config/prompt_manager.py, data/repositories/prompt_repo.py | 300行 |
| Prompt模板种子文件 | config/prompts/*.txt | - |
| LLM Provider抽象层 | models/providers/ | 250行 |
| fal.ai客户端 | models/comfyui/client.py | 150行 |
| CharacterFeatureSchema定义 | models/schemas/character_feature.py | 200行 |
| API层骨架 | api/main.py, api/deps.py | 100行 |

#### 第2周：文本理解层

| 任务 | 文件 | 代码量 |
|------|------|--------|
| 智能文本分块 | core/text/chunker.py | 150行 |
| 实体预扫描 | core/text/entity_scanner.py | 120行 |
| 中文别名合并 | core/text/alias_merger.py | 200行 |
| 共指消解 | core/text/coreference_resolver.py | 150行 |
| Prompt模板编写 | config/prompts/*.txt | - |
| 身份原型模板编写（LLM生成+人工审核） | config/prototypes/identity_templates.json | - |
| 身份原型管理API | api/routes/prototypes.py, api/schemas/prototype_schemas.py | 200行 |

#### 第3周：特征提取与LangGraph编排

| 任务 | 文件 | 代码量 |
|------|------|--------|
| 角色特征提取 | core/text/feature_extractor.py | 300行 |
| 身份原型覆盖（含 variability 逻辑+兜底机制） | core/text/identity_resolver.py | 300行 |
| 四层记忆体系 | core/text/memory_manager.py | 200行 |
| LangGraph工作流 | core/text/graph.py | 200行 |
| 中文NLP工具 | utils/chinese_nlp.py | 150行 |

#### 第4周：2D生成层

| 任务 | 文件 | 代码量 |
|------|------|--------|
| 特征→Prompt映射 | core/image/feature_mapper.py | 250行 |
| Prompt构建器 | core/image/prompt_builder.py | 150行 |
| fal.ai工作流模板 | models/comfyui/workflows.py, param_filler.py | 200行 |
| 工作流执行器 | core/image/workflow_runner.py | 150行 |
| Grid Method四视图 | core/image/grid_generator.py | 150行 |
| CLIP-I一致性检查 | core/image/consistency_checker.py | 120行 |

#### 第5周：集成与测试

| 任务 | 文件 | 代码量 |
|------|------|--------|
| 流水线编排 | core/pipeline.py | 150行 |
| API路由实现（含Prompt管理路由） | api/routes/*.py, api/schemas/prompt_schemas.py | 300行 |
| 3D接口预留 | core/model3d/*.py | 100行 |
| 测试用例（含原型验证+反差测试） | tests/*.py | 250行 |
| 原型纯生成验证（20个身份） | 手动 + fal.ai | - |
| 联调与Bug修复 | - | - |

### 11.2 v2阶段规划（MVP之后）

| 功能 | 预估工期 | 说明 |
|------|----------|------|
| Prompt条件拼接 | 1周 | 支持按场景/条件动态组装Prompt分段（借鉴 llm-rag-server 的 build_complete_prompt） |
| LoRA训练编排 | 2-3周 | 基于锁定角色形象训练专属LoRA |
| 3D生成实现 | 2-3周 | 接入Tripo/Meshy云端API |
| 人工审核界面 | 1-2周 | 特征审核与编辑Web界面 |
| 批量处理优化 | 1周 | 多小说并行处理 |
| 关系图谱可视化 | 1周 | 角色关系网络图 |

### 11.3 角色信息充足度参考

在开发特征提取时，需了解不同角色类型的信息充足度预期：

| 角色类型 | 外貌信息充足度 | 处理策略 |
|----------|----------------|----------|
| 主角 | 60-80% | 完整提取，多轮精修 |
| 重要配角 | 40-60% | 提取+原型补全 |
| 路人/杂角 | 0-20% | 原型主导，文本微调 |

小说写作有意留白外貌描写，这是文学特性而非LLM能力问题。成功产品通过"风格模板补全 + Character Block固定描述 + 用户快速调整"解决信息不足问题。

---

## 12 成本估算

### 12.1 MVP单部小说成本（30个角色，全云端API）

| 环节 | 服务 | 用量 | 单价 | 小计 |
|------|------|------|------|------|
| 文本理解 | DeepSeek API | ~80块 x 12K tokens | $0.14/M input, $0.28/M output | ~$0.5 |
| 图像生成 | fal.ai (云端ComfyUI) | 30角色 x 4-5张 | ~$0.05/张 | ~$6.0 |
| 一致性检查 | 本地CLIP (CPU) | 30角色 x 4张 | $0 | $0 |
| 3D生成（预留） | Tripo等 | 0（未实现） | - | $0 |
| 其他（存储等） | - | - | - | ~$0.5 |
| **合计** | | | | **~$7.0/部** |

四层记忆体系是成本控制的关键：每块仅1.2万字送入API，而非整部百万字小说一次性送入，LLM成本从$6.5降至$0.5。

### 12.2 利用免费额度

| 平台 | 免费额度 | 可验证量 |
|------|----------|----------|
| DeepSeek API | 新用户赠送额度 | 约1-2部小说的文本理解 |
| fal.ai | 注册送$10 | ~15-20张角色插画 |
| Replicate | 部分模型免费 | ~5-10次生成 |

利用各平台免费额度，几乎可零成本验证前3-5个角色的完整流程。

### 12.3 运行环境成本

| 资源 | 成本 | 说明 |
|------|------|------|
| 任意联网电脑 | $0 | 无需GPU，无需本地部署 |
| DeepSeek API | 按量付费 | 无月费，用多少付多少 |
| fal.ai | 按量付费 | 无月费，用多少付多少 |
| **合计** | **按量** | 无固定开销，闲置零成本 |

### 12.4 3D生成成本预估（下次实现时参考）

| 方案 | 单角色成本 | 30角色成本 | 质量预期 |
|------|-----------|-----------|----------|
| Tripo | $0.15 | $4.5 | 中景NPC可用 |
| Meshy | $0.20 | $6.0 | 纹理较好 |
| 混合方案 | $0.15 | $4.5 | 云端生成+本地精修 |

---

## 附录：关键设计决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 编排框架 | LangGraph | 支持循环、条件分支、人工审核、状态持久化 |
| LLM | DeepSeek API | 国内直连、价格极低、中文理解强、OpenAI兼容 |
| 四层记忆体系 | 自研核心 | 1.2万字分块增量处理，控制API成本，替代大上下文窗口LLM |
| 图像生成 | fal.ai (云端ComfyUI) | 无需本地GPU，支持FLUX/InstantID/ControlNet |
| 一致性方案 | InstantID/PuLID | 零样本一致性，无需训练LoRA |
| 一致性评估 | CLIP-I score | 业界标准，可量化，CPU即可运行 |
| 数据库 | SQLite | MVP阶段足够，零配置 |
| Provider抽象 | OpenAI兼容格式 | 模型可零成本切换（DeepSeek/通义千问/Kimi等） |
| 3D生成 | 接口预留 | 技术快速进化中，避免过早绑定 |
| 身份处理 | 三级优先级 | 解决"干净乞丐"等反差描写 |
| 部署方式 | 全云端API | 无需本地部署，任意联网电脑可运行 |
