const fs = require('fs');
const path = require('path');
const root = process.argv[2];
const scan = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything', 'intermediate', 'scan-result.json'), 'utf8'));
const graph = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything', 'knowledge-graph.json'), 'utf8'));
fs.writeFileSync(path.join(root, '.understand-anything', 'meta.json'), JSON.stringify({
  lastAnalyzedAt: new Date().toISOString(),
  gitCommitHash: graph.project.gitCommitHash,
  version: '1.0.0',
  analyzedFiles: scan.totalFiles
}, null, 2));
