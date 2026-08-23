const fs = require("fs");
const extract = JSON.parse(fs.readFileSync(".understand-anything/tmp/ua-file-extract-results-2.json", "utf8"));
const input = JSON.parse(fs.readFileSync(".understand-anything/tmp/ua-file-analyzer-input-2.json", "utf8"));

const meta = {
  "api/routes/characters.py": ["角色 API 路由，查询角色证据、外观状态和冲突，并提供渲染档案审批、合并与拆分操作。", ["api-路由", "角色管理", "fastapi", "异步接口"]],
  "api/routes/story.py": ["故事 API 路由，公开时间线、事件和场景查询，并支持修改场景的时序绑定。", ["api-路由", "故事管理", "fastapi", "异步接口"]],
  "application/services/appearance_service.py": ["外观应用服务，汇聚角色外观状态和渲染档案，处理冲突解决、审批及指定叙事时点的快照计算。", ["应用服务", "外观管理", "冲突解决", "渲染档案"]],
  "application/services/character_entity_service.py": ["角色实体应用服务，执行带版本与幂等性保护的角色合并和拆分，并重绑定相关证据和资源。", ["应用服务", "角色管理", "实体合并", "事务处理"]],
  "application/services/story_service.py": ["故事应用服务，读取时间线、事件和场景，并以乐观并发控制更新场景时序。", ["应用服务", "故事管理", "时序绑定", "并发控制"]],
  "domain/entities/evaluation.py": ["评测领域实体，定义数据集、用例、评分器、运行和结果的验证规则与数据契约。", ["领域模型", "评测", "pydantic", "验证"]],
  "domain/entities/pipeline.py": ["流水线领域实体，定义运行、步骤和外部操作的状态枚举与合法状态迁移。", ["领域模型", "流水线", "状态机", "pydantic"]],
  "infrastructure/db/base.py": ["SQLAlchemy 声明式 ORM 基类，为所有持久化模型提供统一映射基础。", ["数据库", "sqlalchemy", "orm", "基础设施"]],
  "infrastructure/db/orm.py": ["SQLAlchemy ORM 映射集合，持久化小说摄取、角色抽取、流水线、智能体运行、审批和评测等核心数据。", ["数据库", "sqlalchemy", "orm", "持久化"]],
  "infrastructure/db/repositories/evaluation.py": ["评测仓储，实现评测数据集、用例、评分器、评测运行和结果的事务性读写与冲突检查。", ["仓储", "评测", "sqlalchemy", "持久化"]],
  "infrastructure/db/repositories/external_operations.py": ["外部操作仓储，创建、租约式迁移和查询异步外部操作记录。", ["仓储", "外部操作", "状态机", "sqlalchemy"]]
};
const fnSummary = {
  "_revision": "解析 If-Match 头中的修订号，并校验其是否满足当前操作的并发控制要求。",
  "list_characters": "查询指定小说中的角色并序列化为 API 响应。",
  "list_mentions": "读取角色已解析的提及片段及其文本定位信息。",
  "list_observations": "读取角色特征观察记录并按创建顺序返回。",
  "list_expressions": "读取角色表情与情绪观察记录。",
  "list_appearance_states": "读取角色的外观状态版本。",
  "list_character_conflicts": "查询角色未决或指定状态的外观冲突。",
  "resolve_character_conflict": "调用外观服务解决冲突，并返回更新后的冲突记录。",
  "get_render_profile": "获取角色当前渲染档案。",
  "put_render_profile": "更新角色渲染档案并应用乐观并发修订检查。",
  "approve_character_profile": "审批角色渲染档案，固化可用于生成的版本。",
  "get_character_snapshot": "计算给定时间线、事件、场景或章节位置的角色外观快照。",
  "merge_characters": "调用实体服务执行多个角色的合并并返回审计操作。",
  "split_character": "调用实体服务将一个角色拆分为多个目标角色。",
  "_if_match_revision": "解析并验证请求携带的 If-Match 修订号。",
  "list_timelines": "列出小说的叙事时间线。",
  "list_events": "按时间线或章节筛选并返回故事事件及参与者。",
  "list_scenes": "列出小说场景及其时序元数据。",
  "update_scene_temporal_binding": "用服务层校验与乐观锁更新场景时序绑定。",
  "_scope_overlaps": "判断两个外观时序范围是否存在重叠。",
  "_replace_ids": "在字符串标识符列表中将源角色标识替换为目标角色标识。"
};
const level = (start, end) => end - start + 1 > 200 ? "complex" : end - start + 1 >= 50 ? "moderate" : "simple";
function classSummary(name, path) {
  if (/(Response|Request)$/.test(name)) return "为 API 边界定义 " + name + " 请求或响应数据模型。";
  if (/ORM$/.test(name)) return name + " 是 SQLAlchemy ORM 映射，用于持久化对应的业务记录。";
  if (/(Conflict|Error)$/.test(name)) return name + " 表示该模块在校验、并发或状态迁移时抛出的业务异常。";
  if (/Service$/.test(name)) return name + " 封装该模块的应用用例、业务规则与数据访问编排。";
  if (/Repository$/.test(name)) return name + " 封装相关持久化记录的查询、创建和一致性控制。";
  if (/Mixin$/.test(name)) return name + " 为 ORM 模型提供可复用的字段映射能力。";
  if (/(Status|State)$/.test(name)) return name + " 定义该领域流程可使用的状态枚举。";
  return "在 " + path.split("/").pop() + " 中定义 " + name + "，表达该模块的核心数据与状态。";
}
function classTags(name) {
  if (/ORM|Mixin/.test(name)) return ["数据库", "sqlalchemy", "orm", "持久化"];
  if (/Response|Request/.test(name)) return ["api-模型", "pydantic", "序列化", "角色管理"];
  if (/Service/.test(name)) return ["应用服务", "业务规则", "事务处理", "领域编排"];
  if (/Repository/.test(name)) return ["仓储", "数据库", "sqlalchemy", "持久化"];
  if (/Conflict|Error/.test(name)) return ["异常", "业务规则", "并发控制"];
  if (/Status|State/.test(name)) return ["领域模型", "状态机", "枚举"];
  return ["领域模型", "python", "数据契约"];
}
const nodes = [], edges = [];
for (const result of extract.results) {
  const path = result.path, relative = path.slice(path.indexOf("/api/") > 0 ? path.indexOf("/api/") + 1 : path.indexOf("/application/") > 0 ? path.indexOf("/application/") + 1 : path.indexOf("/domain/") > 0 ? path.indexOf("/domain/") + 1 : path.indexOf("/infrastructure/") + 1);
  const [summary, tags] = meta[relative];
  const fileId = "file:" + path;
  nodes.push({id:fileId, type:"file", name:path.split("/").pop(), filePath:path, summary, tags, complexity:result.nonEmptyLines > 200 ? "complex" : result.nonEmptyLines >= 50 ? "moderate" : "simple"});
  const exported = new Set((result.exports || []).map(item => item.name));
  for (const item of result.classes || []) {
    const id = "class:" + path + ":" + item.name;
    nodes.push({id, type:"class", name:item.name, filePath:path, lineRange:[item.startLine, item.endLine], summary:classSummary(item.name, path), tags:classTags(item.name), complexity:level(item.startLine, item.endLine)});
    edges.push({source:fileId, target:id, type:"contains", direction:"forward", weight:1.0});
    if (exported.has(item.name)) edges.push({source:fileId, target:id, type:"exports", direction:"forward", weight:0.8});
  }
  for (const item of result.functions || []) {
    if (item.endLine - item.startLine + 1 < 10) continue;
    const id = "function:" + path + ":" + item.name;
    nodes.push({id, type:"function", name:item.name, filePath:path, lineRange:[item.startLine, item.endLine], summary:fnSummary[item.name] || ("在 " + path.split("/").pop() + " 中实现 " + item.name + "，承担该模块的局部业务处理。"), tags:["业务函数", "python", "异步处理", "角色管理"], complexity:level(item.startLine, item.endLine)});
    edges.push({source:fileId, target:id, type:"contains", direction:"forward", weight:1.0});
    if (exported.has(item.name)) edges.push({source:fileId, target:id, type:"exports", direction:"forward", weight:0.8});
  }
  for (const target of input.batchImportData[path] || []) edges.push({source:fileId, target:"file:" + target, type:"imports", direction:"forward", weight:0.7});
}
const partCount = Math.ceil(Math.max(nodes.length / 60, edges.length / 120));
const paths = input.batchFiles.map(item => item.path).sort(), groupSize = Math.ceil(paths.length / partCount), parts = [];
for (let i = 0; i < partCount; i++) {
  const partPaths = new Set(paths.slice(i * groupSize, (i + 1) * groupSize));
  const partNodes = nodes.filter(item => partPaths.has(item.filePath)), ids = new Set(partNodes.map(item => item.id));
  parts.push({filename:"batch-2-part-" + (i + 1) + ".json", content:{nodes:partNodes, edges:edges.filter(item => ids.has(item.source))}});
}
const stats = {nodes:nodes.length, edges:edges.length, imports:edges.filter(item => item.type === "imports").length, filesSkipped:extract.filesSkipped};
if (process.argv[2] !== undefined) console.log(JSON.stringify({part:parts[Number(process.argv[2])], stats}));
else console.log(JSON.stringify({parts, stats}));
