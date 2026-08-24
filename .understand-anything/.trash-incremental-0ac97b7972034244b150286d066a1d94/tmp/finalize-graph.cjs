const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = process.cwd();
const intermediate = path.join(root, '.understand-anything', 'intermediate');
const base = JSON.parse(fs.readFileSync(path.join(intermediate, 'assembled-graph.json'), 'utf8'));
const layers = JSON.parse(fs.readFileSync(path.join(intermediate, 'layers.json'), 'utf8'));
const tour = JSON.parse(fs.readFileSync(path.join(intermediate, 'tour.json'), 'utf8'));
const scan = JSON.parse(fs.readFileSync(path.join(intermediate, 'scan-result.json'), 'utf8'));
const commit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
const graph = {
  version: '1.0.0',
  project: {
    name: scan.name || 'novel-character-generator',
    languages: [...new Set([...(scan.languages || []), 'css', 'html', 'javascript'])].sort(),
    frameworks: scan.frameworks || ['Alembic', 'FastAPI', 'Pydantic', 'Pytest', 'SQLAlchemy', 'Uvicorn'],
    description: '面向小说文本的角色提取与分阶段图像生成服务，以原文证据、时间线和可审计角色档案为核心，并提供 FastAPI、后台任务与角色造像台界面。',
    analyzedAt: new Date().toISOString(),
    gitCommitHash: commit,
  },
  nodes: base.nodes,
  edges: base.edges,
  layers,
  tour,
};
fs.writeFileSync(path.join(intermediate, 'assembled-graph.json'), JSON.stringify(graph, null, 2));
process.stdout.write(`Assembled graph at ${commit}: ${graph.nodes.length} nodes, ${graph.edges.length} edges.\n`);
