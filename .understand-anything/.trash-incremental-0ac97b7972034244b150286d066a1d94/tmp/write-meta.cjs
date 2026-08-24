const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = process.cwd();
const graph = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything', 'intermediate', 'assembled-graph.json'), 'utf8'));
const fileTypes = new Set(['file', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
const meta = {
  lastAnalyzedAt: new Date().toISOString(),
  gitCommitHash: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
  version: '1.0.0',
  analyzedFiles: graph.nodes.filter((node) => fileTypes.has(node.type)).length,
};
fs.writeFileSync(path.join(root, '.understand-anything', 'meta.json'), JSON.stringify(meta, null, 2));
process.stdout.write(JSON.stringify(meta));
