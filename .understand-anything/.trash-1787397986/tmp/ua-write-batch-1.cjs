const fs = require('fs');
const path = require('path');
const root = process.cwd();
const input = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/tmp/ua-file-analyzer-input-1.json'), 'utf8'));
const F = 'novel-character-generator/src/novel_character_generator/';
const files = [
  ['api/app.py', '装配 FastAPI 应用、生命周期钩子、中间件、指标端点与全部 API 路由，是 HTTP 服务入口。', 'simple', ['entry-point','fastapi','api','application']],
  ['api/auth.py', '提供用户与管理员 API Key 校验依赖，并根据运行环境实施访问控制。', 'simple', ['authentication','security','fastapi','dependency']],
  ['api/deps.py', '为路由层提供异步数据库会话和本地制品存储依赖。', 'simple', ['dependency-injection','database','storage','fastapi']],
  ['api/errors.py', '统一生成含请求标识的错误响应，并注册 FastAPI 异常处理器与请求 ID 中间件。', 'moderate', ['error-handling','middleware','fastapi','api']],
  ['api/metrics.py', '累计 HTTP 请求计数和时长，并以 Prometheus 文本格式暴露指标端点。', 'moderate', ['metrics','middleware','monitoring','prometheus']],
  ['api/routes/__init__.py', '声明 API 路由包，供应用入口导入各个路由模块。', 'simple', ['package','routes','api','python']],
  ['api/routes/agent_runs.py', '提供智能体运行、回合、工具调用和决策记录的只读查询接口。', 'moderate', ['api-handler','agent-runtime','database','fastapi']],
  ['api/routes/approvals.py', '提供待处理人工审批列表和带乐观并发控制的审批决策接口。', 'moderate', ['api-handler','approval','security','fastapi']],
  ['api/routes/capabilities.py', '公开当前部署支持的文本分析、智能体、审批和故事处理能力开关。', 'simple', ['api-handler','capabilities','configuration','fastapi']],
  ['api/routes/health.py', '提供存活和就绪探针，供部署平台执行健康检查。', 'simple', ['api-handler','health-check','fastapi','monitoring']],
  ['api/routes/novels.py', '处理小说文本上传、版本管理、详情查询以及文本分析运行的创建。', 'moderate', ['api-handler','ingestion','novel','fastapi']],
  ['api/routes/runs.py', '提供运行详情、SSE 事件流、外部操作、智能体运行及取消重试接口。', 'moderate', ['api-handler','run-management','sse','fastapi']],
  ['infrastructure/db/session.py', '创建异步 SQLAlchemy 引擎与会话工厂，并在 SQLite 连接时启用关键 PRAGMA。', 'simple', ['database','sqlalchemy','sqlite','infrastructure']],
  ['infrastructure/storage/local.py', '实现基于本地文件系统和内容哈希分层目录的异步制品读写存储。', 'simple', ['storage','artifact','filesystem','infrastructure']],
  ['settings.py', '集中定义环境变量驱动的运行配置，并校验生产环境中的模型提供方和密钥约束。', 'moderate', ['configuration','pydantic','security','settings']]
];
const symbols = {
  'api/app.py': [
    ['function','lifespan',24,26,'在应用关闭阶段释放数据库引擎资源。','simple',['lifecycle','database','fastapi']],
    ['function','create_app',29,49,'创建并配置 FastAPI 实例，注册中间件、指标端点和全部业务路由。','moderate',['factory','fastapi','routes']]],
  'api/auth.py': [
    ['function','_matches',11,12,'以恒定时间比较候选 API Key 与期望密钥。','simple',['security','authentication','utility']],
    ['function','_configured_keys',15,19,'从应用设置中读取用户和管理员 API Key。','simple',['configuration','authentication','utility']],
    ['function','require_user_api_key',22,37,'验证请求 API Key，并授予开发、用户或管理员主体权限。','moderate',['authentication','authorization','fastapi']],
    ['function','require_admin_api_key',40,55,'验证管理员 API Key，并区分无效密钥与权限不足。','moderate',['authentication','authorization','fastapi']]],
  'api/deps.py': [
    ['function','get_session',10,12,'生成并自动关闭供 FastAPI 注入的异步数据库会话。','simple',['dependency-injection','database','fastapi']],
    ['function','get_artifact_store',15,16,'依据运行设置构造本地制品存储实例。','simple',['dependency-injection','storage','factory']]],
  'api/errors.py': [
    ['class','ErrorResponse',12,15,'定义包含错误代码、消息和请求标识的统一错误响应模型。','simple',['error-model','pydantic','api']],
    ['class','RequestIdMiddleware',18,26,'为每个请求注入或传播 X-Request-ID，并写回响应头。','simple',['middleware','request-id','fastapi']],
    ['function','_request_id',29,30,'获取请求上下文中的请求标识，缺失时生成新的 UUID。','simple',['request-id','utility','error-handling']],
    ['function','_error',33,42,'将状态码和业务错误信息序列化为标准 JSON 错误响应。','simple',['error-handling','serialization','api']],
    ['function','http_exception_handler',45,56,'将 FastAPI HTTPException 转换为统一的错误响应格式。','moderate',['error-handling','fastapi','exception']],
    ['function','validation_exception_handler',59,66,'将请求校验异常映射为 422 标准错误响应。','simple',['validation','error-handling','fastapi']],
    ['function','unhandled_exception_handler',69,75,'将未处理异常隐藏为通用内部错误响应。','simple',['error-handling','security','fastapi']],
    ['function','configure_error_handling',78,82,'向应用注册请求 ID 中间件和全部异常处理器。','simple',['configuration','middleware','fastapi']]],
  'api/metrics.py': [
    ['class','MetricsRegistry',11,50,'在线程锁保护下累计按路由和状态码分组的请求数与处理时长。','moderate',['metrics','monitoring','prometheus']],
    ['class','MetricsMiddleware',56,70,'测量每个 HTTP 请求的耗时并写入全局指标注册表。','moderate',['middleware','metrics','monitoring']],
    ['function','metrics',73,76,'以 Prometheus 兼容的纯文本格式返回当前 HTTP 指标。','simple',['metrics','prometheus','api']]],
  'api/routes/agent_runs.py': [
    ['class','AgentRunSummaryResponse',27,47,'定义智能体运行摘要的 API 响应模型。','moderate',['api-schema','agent-runtime','pydantic']],
    ['class','AgentTurnResponse',50,56,'定义智能体单回合上下文、输出和用量的响应模型。','simple',['api-schema','agent-runtime','pydantic']],
    ['class','ToolCallResponse',59,70,'定义智能体工具调用审计信息的响应模型。','simple',['api-schema','agent-runtime','pydantic']],
    ['class','AgentRunDetailsResponse',73,79,'扩展运行摘要，聚合回合、工具调用和决策记录。','simple',['api-schema','agent-runtime','pydantic']],
    ['function','agent_run_summary',82,83,'将 ORM 智能体运行记录转换为摘要响应。','simple',['serialization','agent-runtime','api']],
    ['function','get_agent_run',87,126,'查询指定智能体运行及其回合、工具调用和决策记录。','complex',['api-handler','agent-runtime','database']]],
  'api/routes/approvals.py': [
    ['class','ApprovalResponse',24,40,'定义人工审批请求及其决策状态的 API 响应模型。','moderate',['api-schema','approval','pydantic']],
    ['class','ApprovalPageResponse',43,45,'定义游标分页的审批列表响应模型。','simple',['api-schema','pagination','approval']],
    ['class','ResolveApprovalRequest',48,51,'定义批准、拒绝、修改或延期审批的请求载荷。','simple',['api-schema','validation','approval']],
    ['function','_response',54,55,'将审批 ORM 记录转换为 API 响应模型。','simple',['serialization','approval','api']],
    ['function','_revision',58,66,'解析并校验 If-Match 乐观并发版本号。','simple',['concurrency','validation','approval']],
    ['function','list_approvals',70,89,'按状态和类型分页读取待人工处理的审批请求。','moderate',['api-handler','approval','pagination']],
    ['function','resolve_approval',93,119,'提交审批决策并把冲突和业务校验错误映射为 HTTP 响应。','moderate',['api-handler','approval','concurrency']]],
  'api/routes/capabilities.py': [
    ['class','CapabilitiesResponse',9,20,'定义服务功能可用性清单的响应模型。','simple',['api-schema','capabilities','pydantic']],
    ['function','capabilities',24,38,'根据设置与已实现特性返回客户端可查询的能力矩阵。','moderate',['api-handler','capabilities','configuration']]],
  'api/routes/health.py': [
    ['class','HealthResponse',9,10,'定义健康探针的固定成功响应模型。','simple',['api-schema','health-check','pydantic']],
    ['function','live',14,15,'返回进程存活探针结果。','simple',['api-handler','health-check','liveness']],
    ['function','ready',19,20,'返回服务就绪探针结果。','simple',['api-handler','health-check','readiness']]],
  'api/routes/novels.py': [
    ['class','NovelResponse',21,24,'定义小说基础信息的响应模型。','simple',['api-schema','novel','pydantic']],
    ['class','NovelDetailsResponse',27,30,'扩展小说响应，包含源文件哈希和解析统计信息。','simple',['api-schema','novel','pydantic']],
    ['class','RunResponse',33,37,'定义文本分析运行的简要响应模型。','simple',['api-schema','run-management','pydantic']],
    ['class','DocumentVersionResponse',40,44,'定义小说源文档版本的响应模型。','simple',['api-schema','versioning','pydantic']],
    ['function','upload_novel',48,66,'校验文本上传并调用导入服务创建小说及其初始内容。','moderate',['api-handler','upload','ingestion']],
    ['function','get_novel',70,78,'查询指定小说的详情和文本切分统计。','simple',['api-handler','novel','database']],
    ['function','upload_novel_version',86,114,'校验并上传指定小说的新源文档版本。','moderate',['api-handler','upload','versioning']],
    ['function','create_text_analysis_run',118,132,'为小说创建可幂等的文本分析流水线运行。','moderate',['api-handler','run-management','ingestion']]],
  'api/routes/runs.py': [
    ['class','StepResponse',39,45,'定义流水线步骤状态的响应模型。','simple',['api-schema','pipeline','pydantic']],
    ['class','RunDetailsResponse',48,54,'定义包含步骤状态的分析运行详情响应模型。','simple',['api-schema','run-management','pydantic']],
    ['class','ExternalOperationResponse',57,66,'定义外部提供方操作及其协调状态的响应模型。','simple',['api-schema','external-operation','pydantic']],
    ['function','_run_or_404',69,73,'获取运行详情，缺失时抛出 404 错误。','simple',['utility','run-management','api']],
    ['function','get_run',77,80,'返回指定分析运行的聚合详情。','simple',['api-handler','run-management','database']],
    ['function','stream_run_events',84,116,'以 Server-Sent Events 持续推送运行事件并处理终态与心跳。','complex',['api-handler','sse','run-events']],
    ['function','list_external_operations',123,132,'列出指定运行关联的外部提供方操作。','simple',['api-handler','external-operation','database']],
    ['function','list_agent_runs',136,149,'查询运行下各流水线步骤关联的智能体执行记录。','moderate',['api-handler','agent-runtime','database']],
    ['function','cancel_run',157,167,'请求取消运行并返回更新后的运行详情。','moderate',['api-handler','run-management','cancellation']],
    ['function','retry_run',175,185,'使用配置的最大尝试次数重新调度失败或可重试运行。','moderate',['api-handler','run-management','retry']]],
  'infrastructure/db/session.py': [
    ['function','configure_sqlite',15,23,'在 SQLite 连接建立时开启外键、超时和 WAL 日志配置。','simple',['database','sqlite','configuration']],
    ['function','dispose_engine',26,27,'异步释放 SQLAlchemy 引擎持有的连接资源。','simple',['database','lifecycle','sqlalchemy']]],
  'infrastructure/storage/local.py': [
    ['class','LocalArtifactStore',7,29,'以内容哈希 URI 保存并安全读取本地制品，防止路径越界访问。','moderate',['storage','artifact','filesystem']]],
  'settings.py': [
    ['class','Settings',10,54,'定义数据库、制品、LLM、智能体和鉴权设置，并验证生产环境约束。','complex',['configuration','pydantic','security']],
    ['function','get_settings',58,59,'缓存并返回全局 Settings 实例。','simple',['configuration','singleton','pydantic']]]
};
const nodes = [];
const edges = [];
const fileId = rel => `file:${F}${rel}`;
for (const [rel, summary, complexity, tags] of files) {
  nodes.push({id:fileId(rel), type:'file', name:path.basename(rel), filePath:F+rel, summary, tags, complexity});
  for (const [type, name, start, end, subSummary, subComplexity, subTags] of (symbols[rel] || [])) {
    const id = `${type}:${F}${rel}:${name}`;
    nodes.push({id, type, name, filePath:F+rel, lineRange:[start,end], summary:subSummary, tags:subTags, complexity:subComplexity});
    edges.push({source:fileId(rel), target:id, type:'contains', direction:'forward', weight:1.0});
    edges.push({source:fileId(rel), target:id, type:'exports', direction:'forward', weight:0.8});
  }
}
for (const [source, targets] of Object.entries(input.batchImportData)) {
  for (const target of targets) edges.push({source:`file:${source}`, target:`file:${target}`, type:'imports', direction:'forward', weight:0.7});
}
const groups = [
  new Set(['api/app.py','api/auth.py','api/deps.py','api/errors.py','api/metrics.py','api/routes/__init__.py','api/routes/agent_runs.py','api/routes/approvals.py'].map(x=>F+x)),
  new Set(['api/routes/capabilities.py','api/routes/health.py','api/routes/novels.py','api/routes/runs.py','infrastructure/db/session.py','infrastructure/storage/local.py','settings.py'].map(x=>F+x))
];
groups.forEach((paths, i) => {
  const partNodes = nodes.filter(n => paths.has(n.filePath));
  const ids = new Set(partNodes.map(n => n.id));
  const partEdges = edges.filter(e => ids.has(e.source));
  fs.writeFileSync(path.join(root, `.understand-anything/intermediate/batch-1-part-${i+1}.json`), JSON.stringify({nodes:partNodes, edges:partEdges}, null, 2) + '\n');
});
console.log(JSON.stringify({nodes:nodes.length, edges:edges.length, parts:groups.length}));
