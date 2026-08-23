const fs = require('fs');
const path = require('path');

const root = process.argv[2];
const intermediate = path.join(root, '.understand-anything', 'intermediate');
const scan = JSON.parse(fs.readFileSync(path.join(intermediate, 'scan-result.json'), 'utf8'));
const fragment = JSON.parse(fs.readFileSync(path.join(intermediate, 'assembled-graph.json'), 'utf8'));
let layers = JSON.parse(fs.readFileSync(path.join(intermediate, 'layers.json'), 'utf8'));
let tour = JSON.parse(fs.readFileSync(path.join(intermediate, 'tour.json'), 'utf8'));
const knownPrefixes = /^(file|config|document|service|pipeline|table|schema|resource|endpoint):/;
const nodeIds = new Set(fragment.nodes.map(node => node.id));
const kebab = value => String(value || 'layer').trim().toLowerCase()
  .replace(/[^a-z0-9\u4e00-\u9fff]+/g, '-').replace(/^-+|-+$/g, '') || 'layer';

if (!Array.isArray(layers)) layers = layers.layers || [];
layers = layers.map((layer, index) => {
  let ids = layer.nodeIds || layer.nodes || [];
  ids = ids.map(id => typeof id === 'object' ? id.id : id)
    .map(id => knownPrefixes.test(id) ? id : `file:${id}`)
    .filter(id => nodeIds.has(id));
  return {
    id: layer.id || `layer:${kebab(layer.name || index + 1)}`,
    name: layer.name || `层 ${index + 1}`,
    description: layer.description || '项目文件分层。',
    nodeIds: [...new Set(ids)]
  };
}).filter(layer => layer.nodeIds.length);

if (!Array.isArray(tour)) tour = tour.steps || [];
tour = tour.map((step, index) => {
  let ids = step.nodeIds || step.nodesToInspect || [];
  ids = ids.map(id => knownPrefixes.test(id) ? id : `file:${id}`).filter(id => nodeIds.has(id));
  const out = {
    order: Number.isInteger(step.order) ? step.order : index + 1,
    title: step.title || `导览步骤 ${index + 1}`,
    description: step.description || step.whyItMatters || '查看此组件在项目中的职责。',
    nodeIds: [...new Set(ids)]
  };
  if (typeof step.languageLesson === 'string') out.languageLesson = step.languageLesson;
  return out;
}).filter(step => step.nodeIds.length).sort((a, b) => a.order - b.order)
  .map((step, index) => ({ ...step, order: index + 1 }));

const graph = {
  version: '1.0.0',
  project: {
    name: scan.name,
    languages: scan.languages,
    frameworks: scan.frameworks,
    description: scan.description,
    analyzedAt: new Date().toISOString(),
    gitCommitHash: require('child_process').execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
  },
  nodes: fragment.nodes,
  edges: fragment.edges,
  layers,
  tour
};
fs.writeFileSync(path.join(intermediate, 'assembled-graph.json'), JSON.stringify(graph, null, 2));
fs.writeFileSync(path.join(intermediate, 'fingerprint-input.json'), JSON.stringify({
  projectRoot: root,
  sourceFilePaths: scan.files.map(file => file.path),
  gitCommitHash: graph.project.gitCommitHash
}, null, 2));
