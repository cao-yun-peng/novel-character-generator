const fs = require('fs');

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  console.error('Usage: node ua-arch-analyze.js <input.json> <output.json>');
  process.exit(1);
}

const patterns = {
  api: new Set(['routes', 'api', 'controllers', 'endpoints', 'handlers', 'routers', 'serializers', 'blueprints']),
  service: new Set(['services', 'core', 'lib', 'domain', 'logic', 'composables', 'mailers', 'jobs', 'channels', 'signals', 'internal']),
  data: new Set(['models', 'db', 'data', 'persistence', 'repository', 'entities', 'migrations', 'database', 'schema', 'sql', 'entity']),
  ui: new Set(['components', 'views', 'pages', 'ui', 'layouts', 'screens']),
  middleware: new Set(['middleware', 'plugins', 'interceptors', 'guards']),
  utility: new Set(['utils', 'helpers', 'common', 'shared', 'tools', 'pkg']),
  config: new Set(['config', 'constants', 'env', 'settings', 'management', 'commands']),
  test: new Set(['__tests__', 'test', 'tests', 'spec', 'specs']),
  types: new Set(['types', 'interfaces', 'schemas', 'contracts', 'dtos', 'dto', 'request', 'response']),
  documentation: new Set(['docs', 'documentation', 'wiki']),
  infrastructure: new Set(['deploy', 'deployment', 'infra', 'infrastructure', 'k8s', 'kubernetes', 'helm', 'charts', 'terraform', 'tf', 'docker']),
  'ci-cd': new Set(['.github', '.gitlab', '.circleci']),
  entry: new Set(['cmd', 'bin'])
};

function normalizedPath(node) { return String(node.filePath || node.name || '').replace(/\\\\/g, '/').replace(/^\.\//, ''); }
function pathParts(node) { return normalizedPath(node).split('/').filter(Boolean); }
function isTest(path) { return /(^|\/)(test|tests|__tests__)\//i.test(path) || /(^|\/)(test_[^/]+|[^/]+\.(test|spec)\.[^/]+)$/i.test(path) || /_test\.[^/]+$/i.test(path); }
function groupFor(node, prefixParts) {
  const parts = pathParts(node);
  const rest = parts.slice(prefixParts.length);
  if (rest.length <= 1) return '根目录';
  return rest[0];
}
function labelForFile(node, group) {
  const path = normalizedPath(node);
  const base = path.split('/').pop() || '';
  if (isTest(path)) return 'test';
  if (/\.(md|rst)$/i.test(base)) return 'documentation';
  if (/^(Dockerfile|docker-compose)/i.test(base) || /\.(tf|tfvars)$/i.test(base) || /^Makefile$/i.test(base)) return 'infrastructure';
  if (/^\.github\/workflows\//.test(path) || /^(\.gitlab-ci\.yml|Jenkinsfile)$/i.test(base)) return 'ci-cd';
  if (/\.(sql)$/i.test(base)) return 'data';
  if (/\.(graphql|gql|proto)$/i.test(base)) return 'types';
  if (/^(pyproject\.toml|package\.json|Cargo\.toml|go\.mod|Gemfile|pom\.xml|build\.gradle|composer\.json)$/i.test(base)) return 'config';
  if (/^(app\.py|main\.py)$/i.test(base) || /^__init__\.py$/i.test(base)) return 'entry';
  for (const [label, names] of Object.entries(patterns)) if (names.has(group.toLowerCase())) return label;
  return 'other';
}

try {
  const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  const nodes = Array.isArray(input.fileNodes) ? input.fileNodes : [];
  const importEdges = Array.isArray(input.importEdges) ? input.importEdges : [];
  const allEdges = Array.isArray(input.allEdges) ? input.allEdges : [];
  const idToNode = new Map(nodes.map(node => [node.id, node]));
  const allParts = nodes.map(pathParts).filter(parts => parts.length);
  let prefixParts = allParts.length ? [...allParts[0]] : [];
  for (const parts of allParts.slice(1)) {
    let i = 0;
    while (i < prefixParts.length && i < parts.length && prefixParts[i] === parts[i]) i++;
    prefixParts = prefixParts.slice(0, i);
  }
  if (!prefixParts.length || prefixParts.length >= Math.min(...allParts.map(parts => parts.length))) prefixParts = [];
  const directoryGroups = {};
  const groupOf = new Map();
  const patternMatches = {};
  for (const node of nodes) {
    const group = groupFor(node, prefixParts);
    groupOf.set(node.id, group);
    (directoryGroups[group] ||= []).push(node.id);
    patternMatches[group] ||= labelForFile(node, group);
  }
  const nodeTypeGroups = {};
  for (const node of nodes) (nodeTypeGroups[node.type] ||= []).push(node.id);
  const fanIn = Object.fromEntries(nodes.map(node => [node.id, 0]));
  const fanOut = Object.fromEntries(nodes.map(node => [node.id, 0]));
  const pairCounts = new Map();
  const groupRelations = new Map();
  const internal = Object.fromEntries(Object.keys(directoryGroups).map(group => [group, 0]));
  const total = Object.fromEntries(Object.keys(directoryGroups).map(group => [group, 0]));
  for (const edge of importEdges) {
    if (!idToNode.has(edge.source) || !idToNode.has(edge.target)) continue;
    fanOut[edge.source]++;
    fanIn[edge.target]++;
    const from = groupOf.get(edge.source), to = groupOf.get(edge.target);
    const key = `${from}\u0000${to}`;
    pairCounts.set(key, (pairCounts.get(key) || 0) + 1);
    if (from === to) internal[from]++;
    total[from]++; total[to]++;
  }
  const interGroupImports = [...pairCounts.entries()].map(([key, count]) => {
    const [from, to] = key.split('\u0000'); return { from, to, count };
  });
  const intraGroupDensity = Object.fromEntries(Object.keys(directoryGroups).map(group => [group, {
    internalEdges: internal[group], totalEdges: total[group], density: total[group] ? Number((internal[group] / total[group]).toFixed(3)) : 0
  }]));
  const crossMap = new Map();
  for (const edge of allEdges) {
    const source = idToNode.get(edge.source), target = idToNode.get(edge.target);
    if (!source || !target) continue;
    const key = `${source.type}\u0000${target.type}\u0000${edge.type}`;
    crossMap.set(key, (crossMap.get(key) || 0) + 1);
  }
  const crossCategoryEdges = [...crossMap.entries()].map(([key, count]) => {
    const [fromType, toType, edgeType] = key.split('\u0000'); return { fromType, toType, edgeType, count };
  });
  const dependencyDirection = [];
  const paired = new Set();
  for (const { from, to } of interGroupImports) {
    if (from === to) continue;
    const pairKey = [from, to].sort().join('\u0000');
    if (paired.has(pairKey)) continue;
    paired.add(pairKey);
    const forward = pairCounts.get(`${from}\u0000${to}`) || 0;
    const reverse = pairCounts.get(`${to}\u0000${from}`) || 0;
    if (forward > reverse) dependencyDirection.push({ dependent: from, dependsOn: to });
    else if (reverse > forward) dependencyDirection.push({ dependent: to, dependsOn: from });
  }
  const paths = nodes.map(normalizedPath);
  const docsGroups = new Set(paths.filter(path => /(^|\/)(README\.md|docs\/|documentation\/)/i.test(path)).map(path => path.split('/')[0] || '根目录'));
  const groupNames = Object.keys(directoryGroups);
  const infraFiles = paths.filter(path => /(^|\/)(Dockerfile|docker-compose|\.github\/workflows|k8s|kubernetes|helm|terraform|infra|deployment)/i.test(path));
  const result = {
    scriptCompleted: true,
    directoryGroups,
    nodeTypeGroups,
    crossCategoryEdges,
    interGroupImports,
    intraGroupDensity,
    patternMatches,
    deploymentTopology: {
      hasDockerfile: paths.some(path => /(^|\/)Dockerfile/i.test(path)),
      hasCompose: paths.some(path => /docker-compose/i.test(path)),
      hasK8s: paths.some(path => /(^|\/)(k8s|kubernetes|helm)\//i.test(path)),
      hasTerraform: paths.some(path => /\.(tf|tfvars)$/i.test(path)),
      hasCI: paths.some(path => /(^|\/)(\.github\/workflows|\.gitlab-ci\.yml|Jenkinsfile)/i.test(path)),
      infraFiles
    },
    dataPipeline: {
      schemaFiles: paths.filter(path => /\.(sql|graphql|gql|proto|prisma)$/i.test(path)),
      migrationFiles: paths.filter(path => /(^|\/)migrations\//i.test(path)),
      dataModelFiles: nodes.filter(node => /(^|\/)(models|db|repositories|repository)\//i.test(normalizedPath(node))).map(node => normalizedPath(node)),
      apiHandlerFiles: nodes.filter(node => /(^|\/)(api|routes|routers|controllers)\//i.test(normalizedPath(node))).map(node => normalizedPath(node))
    },
    docCoverage: {
      groupsWithDocs: docsGroups.size,
      totalGroups: groupNames.length,
      coverageRatio: groupNames.length ? Number((docsGroups.size / groupNames.length).toFixed(3)) : 0,
      undocumentedGroups: groupNames.filter(group => !docsGroups.has(group))
    },
    dependencyDirection,
    fileStats: {
      totalFileNodes: nodes.length,
      filesPerGroup: Object.fromEntries(Object.entries(directoryGroups).map(([group, ids]) => [group, ids.length])),
      nodeTypeCounts: Object.fromEntries(Object.entries(nodeTypeGroups).map(([type, ids]) => [type, ids.length]))
    },
    fileFanIn: fanIn,
    fileFanOut: fanOut
  };
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
} catch (error) {
  console.error(error.stack || error.message);
  process.exit(1);
}
