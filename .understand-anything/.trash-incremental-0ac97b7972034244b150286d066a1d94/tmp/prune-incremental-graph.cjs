const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = process.cwd();
const graphPath = path.join(root, '.understand-anything', 'knowledge-graph.json');
const metaPath = path.join(root, '.understand-anything', 'meta.json');
const outputPath = path.join(root, '.understand-anything', 'intermediate', 'batch-existing.json');
const graph = JSON.parse(fs.readFileSync(graphPath, 'utf8'));
const base = JSON.parse(fs.readFileSync(metaPath, 'utf8')).gitCommitHash;
const changed = new Set(
  execFileSync('git', ['diff', `${base}..HEAD`, '--name-only'], { cwd: root, encoding: 'utf8' })
    .split(/\r?\n/)
    .filter((file) => file && !file.startsWith('.understand-anything/')),
);
const nodes = graph.nodes.filter((node) => !changed.has(node.filePath));
const nodeIds = new Set(nodes.map((node) => node.id));
const edges = graph.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));
fs.writeFileSync(outputPath, JSON.stringify({ nodes, edges }, null, 2));
process.stdout.write(`Retained ${nodes.length} nodes and ${edges.length} edges; removed ${graph.nodes.length - nodes.length} changed-file nodes.\n`);
