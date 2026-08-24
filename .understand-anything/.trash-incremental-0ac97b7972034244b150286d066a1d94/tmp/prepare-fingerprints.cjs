const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = process.cwd();
const graph = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything', 'intermediate', 'assembled-graph.json'), 'utf8'));
const fileTypes = new Set(['file', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
const sourceFilePaths = [...new Set(graph.nodes.filter((node) => fileTypes.has(node.type) && node.filePath).map((node) => node.filePath))].sort();
const payload = { projectRoot: root, sourceFilePaths, gitCommitHash: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim() };
fs.writeFileSync(path.join(root, '.understand-anything', 'intermediate', 'fingerprint-input.json'), JSON.stringify(payload, null, 2));
process.stdout.write(`Prepared ${sourceFilePaths.length} fingerprint paths.\n`);
