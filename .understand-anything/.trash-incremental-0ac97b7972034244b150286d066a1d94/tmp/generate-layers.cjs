const fs = require('fs');
const path = require('path');

const root = process.cwd();
const graph = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything', 'intermediate', 'assembled-graph.json'), 'utf8'));
const fileTypes = new Set(['file', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
const layers = [
  ['layer:api', 'API 与接口层', '承载 FastAPI 应用装配、认证、依赖注入、异常与指标中间件，以及小说、角色、运行、审批和 UI 路由。'],
  ['layer:web-interface', 'Web 界面层', '提供角色造像台的静态 HTML、JavaScript、CSS 与图标资源，并由 API 的 UI 路由提供服务。'],
  ['layer:application', '应用编排层', '协调用例服务、端口、命令与查询，编排小说解析、角色生成、审批、运行和制品存储等业务流程。'],
  ['layer:domain', '领域模型与规则层', '定义小说、角色、故事、评估与时间绑定等核心实体、值对象和业务策略，保持框架无关的业务表达。'],
  ['layer:infrastructure-data', '基础设施与数据层', '实现 SQLAlchemy/Alembic 持久化、仓储、LLM 与本地存储适配器，并维护数据库演进迁移。'],
  ['layer:agents-workers', '智能体与后台执行层', '提供结构化智能体运行时、工作流和异步任务处理器，执行提取、摄入与可恢复的后台任务。'],
  ['layer:quality', '测试与质量保障层', '以单元和集成测试验证领域规则、数据迁移、服务编排及 FastAPI 接口与 UI 静态资源的端到端行为。'],
  ['layer:documentation-data', '文档与示例数据层', '沉淀项目导航、架构、领域、实施契约、API、运维与评测说明，并提供用于上传和冒烟测试的小说文本样例。'],
  ['layer:project-support', '项目配置与支撑层', '集中项目依赖、环境、Alembic 和知识图谱配置，以及未归入业务层的根目录支撑文件。'],
].map(([id, name, description]) => ({ id, name, description, nodeIds: [] }));
const byId = new Map(layers.map((layer) => [layer.id, layer]));
function layerFor(node) {
  const p = node.filePath || '';
  if (node.type === 'document') return 'layer:documentation-data';
  if (p.includes('/tests/')) return 'layer:quality';
  if (p.includes('/src/novel_character_generator/web/')) return 'layer:web-interface';
  if (p.includes('/src/novel_character_generator/api/')) return 'layer:api';
  if (p.includes('/src/novel_character_generator/application/')) return 'layer:application';
  if (p.includes('/src/novel_character_generator/domain/')) return 'layer:domain';
  if (p.includes('/migrations/') || p.includes('/src/novel_character_generator/infrastructure/')) return 'layer:infrastructure-data';
  if (p.includes('/src/novel_character_generator/agents/') || p.includes('/src/novel_character_generator/workers/') || p.includes('/src/novel_character_generator/workflows/')) return 'layer:agents-workers';
  return 'layer:project-support';
}
for (const node of graph.nodes.filter((node) => fileTypes.has(node.type))) byId.get(layerFor(node)).nodeIds.push(node.id);
for (const layer of layers) layer.nodeIds.sort();
const assigned = layers.flatMap((layer) => layer.nodeIds);
const expected = graph.nodes.filter((node) => fileTypes.has(node.type)).map((node) => node.id);
if (assigned.length !== expected.length || new Set(assigned).size !== expected.length || expected.some((id) => !assigned.includes(id))) throw new Error('Layer assignment is incomplete or duplicated.');
fs.writeFileSync(path.join(root, '.understand-anything', 'intermediate', 'layers.json'), JSON.stringify(layers.filter((layer) => layer.nodeIds.length), null, 2));
process.stdout.write(`Assigned ${expected.length} file-level nodes to ${layers.length} layers.\n`);
