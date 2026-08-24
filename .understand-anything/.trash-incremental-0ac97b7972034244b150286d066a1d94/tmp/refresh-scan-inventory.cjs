const fs = require('fs');
const path = require('path');

const root = process.cwd();
const scanPath = path.join(root, '.understand-anything', 'intermediate', 'scan-result.json');
const graphPath = path.join(root, '.understand-anything', 'knowledge-graph.json');
const scan = JSON.parse(fs.readFileSync(scanPath, 'utf8'));
const graph = JSON.parse(fs.readFileSync(graphPath, 'utf8'));
const existing = new Set(scan.files.map((file) => file.path));
const fileTypes = new Set(['file', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
const additions = [];
for (const node of graph.nodes.filter((node) => fileTypes.has(node.type) && node.filePath && !existing.has(node.filePath))) {
  const fullPath = path.join(root, ...node.filePath.split('/'));
  const ext = path.extname(node.filePath).toLowerCase();
  const language = ext === '.py' ? 'python' : ext === '.js' ? 'javascript' : ext === '.css' ? 'css' : ext === '.html' ? 'html' : ext === '.svg' ? 'svg' : 'markdown';
  const fileCategory = ext === '.py' || ext === '.js' ? 'code' : ['.css', '.html', '.svg'].includes(ext) ? 'markup' : 'docs';
  additions.push({ path: node.filePath, language, sizeLines: fs.readFileSync(fullPath, 'utf8').split(/\r?\n/).length, fileCategory });
  scan.importMap[node.filePath] = [];
}
scan.files.push(...additions);
scan.files.sort((a, b) => a.path.localeCompare(b.path));
scan.totalFiles = scan.files.length;
scan.languages = [...new Set([...scan.languages, ...additions.map((file) => file.language)])].sort();
fs.writeFileSync(scanPath, JSON.stringify(scan, null, 2));
process.stdout.write(`Added ${additions.length} missing inventory entries; total ${scan.totalFiles}.\n`);
