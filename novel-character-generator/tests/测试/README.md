# v3 视觉候选检查器

`inspect_visual_candidates.py` 只检查当前 `visual-observation-v3` 链路：组合请求、实体候选、原子视觉候选、deferred 项，以及服务端定位后的 mention/Observation。旧八类联合抽取和关系检查器已删除。

仅生成请求预览，不调用模型：

```powershell
.venv\Scripts\python.exe tests\测试\inspect_visual_candidates.py "tests\测试\你的小说.txt" --prompt-only
```

只对第一个 Chunk 发起真实 v3 调用：

```powershell
.venv\Scripts\python.exe tests\测试\inspect_visual_candidates.py "tests\测试\你的小说.txt" --max-chunks 1
```

按确定性预检选定一个或多个 Chunk，避免为了跳过低信息开头而付费调用无关分块：

```powershell
.venv\Scripts\python.exe tests\测试\inspect_visual_candidates.py "tests\测试\你的小说.txt" --chunk-tokens 2500 --chunk-ordinals 1,5
```

`--chunk-ordinals` 与 `--max-chunks` 互斥，ordinal 从 0 开始。选择依据只能是分块长度、章节边界或通用视觉关键词密度，不能根据已知答案挑选模型容易成功的段落。

结果写入 `data/diagnostics/*.visual-v3.*.json`。真实调用读取项目 `.env` 的 Provider 配置；输出包含小说原文、模型响应和 usage，但不包含 API Key。扩大 `--max-chunks` 会增加费用。
