const fs = require('fs');

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  console.error('Usage: node ua-arch-analyze.js <input.json> <output.json>');
  process.exit(1);
}

const patterns = {
  routes: 'api', api: 'api', controllers: 'api', endpoints: 'api', handlers: 'api', routers: 'api', blueprints: 'api', serializers: 'api',
  services: 'service', core: 'service', lib: 'service', domain: 'service', logic: 'service', composables: 'service', signals: 'service', mailers: 'service', jobs: 'service', channels: 'service', internal: 'service',
  models: 'data', db: 'data', data: 'data', persistence: 'data', repository: 'data', entities: 'data', migrations: 'data', sql: 'data', database: 'data', schema: 'data',
  components: 'ui', views: 'ui', pages: 'ui', ui: 'ui', layouts: 'ui', screens: 'ui',
  middleware: 'middleware', plugins: 'middleware', interceptors: 'middleware', guards: 'middleware',
  utils: 'utility', helpers: 'utility', common: 'utility', shared: 'utility', tools: 'utility', templatetags: 'utility', pkg: 'utility',
  config: 'config', constants: 'config', env: 'config', settings: 'config', management: 'config', commands: 'config',
  __tests__: 'test', test: 'test', tests: 'test', spec: 'test', specs: 'test',
  types: 'types', interfaces: 'types', schemas: 'types', contracts: 'types', dtos: 'types', dto: 'types', request: 'types', response: 'types',
  hooks: 'hooks', store: 'state', state: 'state', reducers: 'state', actions: 'state', slices: 'state',
  assets: 'assets', static: 'assets', public: 'assets', cmd: 'entry', bin: 'entry',
  docs: 'documentation', documentation: 'documentation', wiki: 'documentation',
  deploy: 'infrastructure', deployment: 'infrastructure', infra: 'infrastructure', infrastructure: 'infrastructure', k8s: 'infrastructure', kubernetes: 'infrastructure', helm: 'infrastructure', charts: 'infrastructure', terraform: 'infrastructure', tf: 'infrastructure', docker: 'infrastructure',
  '.github': 'ci-cd', '.gitlab': 'ci-cd', '.circleci': 'ci-cd'
};

function normalizePath(node) { return String(node.filePath || node.name || '').replace(/\\/g, '/').replace(/^\.\//, ''); }
function commonPrefix(paths) {
  const segments = paths.map((path) => normalizePath({ filePath: path }).split('/').filter(Boolean));
  if (!segments.length) return [];
  const result = [];
  for (let i = 0; ; i += 1) {
    const value = segments[0][i];
    if (!value || !segments.every((parts) => parts[i] === value)) break;
    result.push(value);
  }
  return result;
}
function groupFor(node, prefix) {
  const parts = normalizePath(node).split('/').filter(Boolean);
  const remainder = parts.slice(prefix.length);
  if (remainder.length > 1) return remainder[0];
  if (remainder.length === 1) return 'root';
  return 'root';
}
function filePattern(node) {
  const path = normalizePath(node);
  const base = path.split('/').pop();
  if (/\.(test|spec)\.[^/]+$/i.test(path) || /(^|\/)test_[^/]+\.py$/i.test(path) || /_test\.go$/i.test(path) || /Test\.java$/i.test(path) || /_spec\.rb$/i.test(path) || /Test(s)?\.cs$/i.test(path)) return 'test';
  if (/\.d\.ts$/i.test(path)) return 'types';
  if (['index.ts', 'index.js', '__init__.py'].includes(base)) return 'entry';
  if (base === 'manage.py') return 'entry';
  if (base === 'wsgi.py' || base === 'asgi.py') return 'config';
  if (['Cargo.toml', 'go.mod', 'Gemfile', 'pom.xml', 'build.gradle', 'composer.json'].includes(base)) return 'config';
  if (/^Dockerfile/i.test(base) || /^docker-compose\./i.test(base) || /\.(tf|tfvars)$/i.test(base) || base === 'Makefile') return 'infrastructure';
  if (/(^|\/)\.github\/workflows\//.test(path) || base === '.gitlab-ci.yml' || base === 'Jenkinsfile') return 'ci-cd';
  if (/\.sql$/i.test(path)) return 'data';
  if (/\.(graphql|gql|proto)$/i.test(path)) return 'types';
  if (/\.(md|rst)$/i.test(path)) return 'documentation';
  return null;
}
function hasPath(nodes, regex) { return nodes.some((node) => regex.test(normalizePath(node))); }

try {
  const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  const nodes = Array.isArray(input.fileNodes) ? input.fileNodes : [];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const prefix = commonPrefix(nodes.map(normalizePath));
  const directoryGroups = {};
  const nodeTypeGroups = {};
  const groupById = new Map();
  for (const node of nodes) {
    const group = groupFor(node, prefix);
    groupById.set(node.id, group);
    (directoryGroups[group] ||= []).push(node.id);
    (nodeTypeGroups[node.type] ||= []).push(node.id);
  }
  const fanIn = Object.fromEntries(nodes.map((node) => [node.id, 0]));
  const fanOut = Object.fromEntries(nodes.map((node) => [node.id, 0]));
  const groupImports = new Map();
  const groupTotals = new Map();
  const groupInternal = new Map();
  for (const edge of input.importEdges || []) {
    if (!byId.has(edge.source) || !byId.has(edge.target)) continue;
    fanOut[edge.source] += 1;
    fanIn[edge.target] += 1;
    const from = groupById.get(edge.source), to = groupById.get(edge.target);
    const key = `${from}\u0000${to}`;
    groupImports.set(key, (groupImports.get(key) || 0) + 1);
    groupTotals.set(from, (groupTotals.get(from) || 0) + 1);
    groupTotals.set(to, (groupTotals.get(to) || 0) + 1);
    if (from === to) groupInternal.set(from, (groupInternal.get(from) || 0) + 1);
  }
  const interGroupImports = [...groupImports.entries()].map(([key, count]) => {
    const [from, to] = key.split('\u0000'); return { from, to, count };
  });
  const intraGroupDensity = Object.fromEntries(Object.keys(directoryGroups).map((group) => {
    const internalEdges = groupInternal.get(group) || 0, totalEdges = groupTotals.get(group) || 0;
    return [group, { internalEdges, totalEdges, density: totalEdges ? Number((internalEdges / totalEdges).toFixed(3)) : 0 }];
  }));
  const cross = new Map();
  for (const edge of input.allEdges || []) {
    const source = byId.get(edge.source), target = byId.get(edge.target);
    if (!source || !target) continue;
    const key = `${source.type}\u0000${target.type}\u0000${edge.type}`;
    cross.set(key, (cross.get(key) || 0) + 1);
  }
  const crossCategoryEdges = [...cross.entries()].map(([key, count]) => {
    const [fromType, toType, edgeType] = key.split('\u0000'); return { fromType, toType, edgeType, count };
  });
  const patternMatches = {};
  for (const group of Object.keys(directoryGroups)) patternMatches[group] = patterns[group.toLowerCase()] || null;
  const deploymentFiles = nodes.filter((node) => {
    const p = normalizePath(node); return node.type === 'service' || node.type === 'resource' || node.type === 'pipeline' || /(^|\/)(Dockerfile|docker-compose|k8s|kubernetes|helm|terraform|\.github\/workflows)/i.test(p);
  }).map(normalizePath);
  const dataPipeline = {
    schemaFiles: nodes.filter((node) => node.type === 'schema' || /\.(sql|graphql|gql|proto)$/i.test(normalizePath(node))).map(normalizePath),
    migrationFiles: nodes.filter((node) => /(^|\/)(alembic|migrations)(\/|$)/i.test(normalizePath(node))).map(normalizePath),
    dataModelFiles: nodes.filter((node) => /(^|\/)(models|entities|db)(\/|$)/i.test(normalizePath(node))).map(normalizePath),
    apiHandlerFiles: nodes.filter((node) => /(^|\/)(api|routes|controllers|routers)(\/|$)/i.test(normalizePath(node))).map(normalizePath)
  };
  const docsForGroup = new Set(nodes.filter((node) => node.type === 'document').map((node) => groupFor(node, prefix)));
  const groups = Object.keys(directoryGroups);
  const dependencyDirection = interGroupImports.filter((item) => item.from !== item.to).map((item) => ({ dependent: item.from, dependsOn: item.to }));
  const result = {
    scriptCompleted: true, directoryGroups, nodeTypeGroups, crossCategoryEdges, interGroupImports, intraGroupDensity, patternMatches,
    deploymentTopology: { hasDockerfile: hasPath(nodes, /(^|\/)Dockerfile/i), hasCompose: hasPath(nodes, /(^|\/)docker-compose\./i), hasK8s: hasPath(nodes, /(^|\/)(k8s|kubernetes|helm)\//i), hasTerraform: hasPath(nodes, /\.tf(vars)?$/i), hasCI: hasPath(nodes, /(^|\/)\.github\/workflows\//i) || hasPath(nodes, /\.gitlab-ci\.yml$|Jenkinsfile$/i), infraFiles: deploymentFiles },
    dataPipeline,
    docCoverage: { groupsWithDocs: docsForGroup.size, totalGroups: groups.length, coverageRatio: groups.length ? Number((docsForGroup.size / groups.length).toFixed(3)) : 0, undocumentedGroups: groups.filter((group) => !docsForGroup.has(group)) },
    dependencyDirection,
    fileStats: { totalFileNodes: nodes.length, filesPerGroup: Object.fromEntries(Object.entries(directoryGroups).map(([group, ids]) => [group, ids.length])), nodeTypeCounts: Object.fromEntries(Object.entries(nodeTypeGroups).map(([type, ids]) => [type, ids.length])) },
    fileFanIn: fanIn, fileFanOut: fanOut
  };
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
  process.stdout.write(`Analyzed ${nodes.length} file nodes and ${(input.importEdges || []).length} import edges.\n`);
} catch (error) {
  console.error(error.stack || error.message);
  process.exit(1);
}
