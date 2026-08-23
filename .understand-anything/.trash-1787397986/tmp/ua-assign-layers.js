const fs = require('fs');

const [inputPath, structuralPath, outputPath] = process.argv.slice(2);
if (!inputPath || !structuralPath || !outputPath) {
  console.error('Usage: node ua-assign-layers.js <input.json> <structural.json> <layers.json>');
  process.exit(1);
}

try {
  const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  const structural = JSON.parse(fs.readFileSync(structuralPath, 'utf8'));
  if (!structural.scriptCompleted || structural.fileStats.totalFileNodes !== input.fileNodes.length) {
    throw new Error('结构分析结果不完整，拒绝进行语义分层');
  }
  const definitions = [
    ['layer:api', 'API 与接口层', '承载 FastAPI 应用装配、认证、依赖注入、异常与指标中间件，以及小说、角色、运行和审批等 HTTP 路由。'],
    ['layer:application', '应用编排层', '协调用例服务、端口、命令与查询，编排小说解析、角色生成、审批、运行和制品存储等业务流程。'],
    ['layer:domain', '领域模型与规则层', '定义小说、角色、故事、评估与时间绑定等核心实体、值对象和业务策略，保持框架无关的业务表达。'],
    ['layer:infrastructure-data', '基础设施与数据层', '实现 SQLAlchemy/Alembic 持久化、仓储、LLM 与本地存储适配器，并维护数据库演进迁移。'],
    ['layer:agents-workers', '智能体与后台执行层', '提供结构化智能体运行时、工作流和异步任务处理器，执行提取、摄入与可恢复的后台任务。'],
    ['layer:quality', '测试与质量保障层', '以单元和集成测试验证领域规则、数据迁移、服务编排及 FastAPI 接口的端到端行为。'],
    ['layer:documentation-data', '文档与示例数据层', '沉淀项目导航、架构、领域、API 与运维说明，并提供用于上传和冒烟测试的小说文本样例。'],
    ['layer:project-support', '项目配置与支撑层', '集中项目依赖、环境、Alembic 和知识图谱配置，以及未归入业务层的根目录支撑文件。']
  ];
  const assignments = new Map(definitions.map(([id]) => [id, []]));
  const choose = node => {
    const p = String(node.filePath || '').replace(/\\\\/g, '/');
    if (/\/src\/novel_character_generator\/api\//.test(p)) return 'layer:api';
    if (/\/src\/novel_character_generator\/application\//.test(p)) return 'layer:application';
    if (/\/src\/novel_character_generator\/domain\//.test(p)) return 'layer:domain';
    if (/\/src\/novel_character_generator\/infrastructure\//.test(p) || /\/migrations\//.test(p)) return 'layer:infrastructure-data';
    if (/\/src\/novel_character_generator\/(agents|workers|workflows)\//.test(p)) return 'layer:agents-workers';
    if (/\/tests\//.test(p) || /(^|\/)test_[^/]+\.py$/.test(p)) return 'layer:quality';
    if (node.type === 'document' || /\/docs\//.test(p) || /\/data\/fixtures\//.test(p)) return 'layer:documentation-data';
    return 'layer:project-support';
  };
  for (const node of input.fileNodes) assignments.get(choose(node)).push(node.id);
  const layers = definitions.map(([id, name, description]) => ({ id, name, description, nodeIds: assignments.get(id) })).filter(layer => layer.nodeIds.length);
  const seen = new Set(layers.flatMap(layer => layer.nodeIds));
  if (seen.size !== input.fileNodes.length || layers.reduce((sum, layer) => sum + layer.nodeIds.length, 0) !== input.fileNodes.length) {
    throw new Error('文件节点未被恰好分配一次');
  }
  if (layers.length < 3 || layers.length > 10) throw new Error('层数超出允许范围');
  fs.writeFileSync(outputPath, JSON.stringify(layers, null, 2));
} catch (error) {
  console.error(error.stack || error.message);
  process.exit(1);
}
