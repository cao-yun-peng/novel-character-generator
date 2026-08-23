#!/usr/bin/env node
const fs = require('fs');

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  console.error('Usage: node ua-tour-analyze.js <graph.json> <results.json>');
  process.exit(1);
}

try {
  const graph = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  const fileTypes = new Set(['file', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
  const nodes = (Array.isArray(graph.nodes) ? graph.nodes : []).filter((node) => fileTypes.has(node.type));
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  const fanIn = new Map(nodes.map((node) => [node.id, 0]));
  const fanOut = new Map(nodes.map((node) => [node.id, 0]));
  const adjacency = new Map(nodes.map((node) => [node.id, []]));

  for (const edge of edges) {
    if (nodeById.has(edge.source) && nodeById.has(edge.target)) {
      fanOut.set(edge.source, fanOut.get(edge.source) + 1);
      fanIn.set(edge.target, fanIn.get(edge.target) + 1);
      if (edge.type === 'imports' || edge.type === 'calls') adjacency.get(edge.source).push(edge.target);
    }
  }

  const rank = (metric, key) => nodes
    .map((node) => ({ id: node.id, [key]: metric.get(node.id), name: node.name, summary: node.summary }))
    .sort((a, b) => b[key] - a[key] || a.id.localeCompare(b.id))
    .slice(0, 20);
  const fanInRanking = rank(fanIn, 'fanIn');
  const fanOutRanking = rank(fanOut, 'fanOut');
  const fanOutThreshold = [...fanOut.values()].sort((a, b) => b - a)[Math.max(0, Math.ceil(nodes.length * 0.1) - 1)] ?? 0;
  const fanInAscending = [...fanIn.values()].sort((a, b) => a - b);
  const lowFanInThreshold = fanInAscending[Math.max(0, Math.ceil(nodes.length * 0.25) - 1)] ?? 0;
  const entryNames = new Set(['index.ts', 'index.js', 'main.ts', 'main.js', 'app.ts', 'app.js', 'server.ts', 'server.js', 'mod.rs', 'main.go', 'main.py', 'main.rs', 'manage.py', 'app.py', 'wsgi.py', 'asgi.py', 'run.py', '__main__.py', 'Application.java', 'Main.java', 'Program.cs', 'config.ru', 'index.php', 'App.swift', 'Application.kt', 'main.cpp', 'main.c']);
  const entryPointCandidates = nodes.map((node) => {
    const path = node.filePath || '';
    const parts = path.split('/');
    let score = 0;
    if (node.type === 'document' && path === 'README.md') score += 5;
    else if (node.type === 'document' && path.endsWith('.md') && parts.length === 1) score += 2;
    if (node.type === 'file' && entryNames.has(node.name)) score += 3;
    if (node.type === 'file' && parts.length <= 2) score += 1;
    if (node.type === 'file' && fanOut.get(node.id) >= fanOutThreshold) score += 1;
    if (node.type === 'file' && fanIn.get(node.id) <= lowFanInThreshold) score += 1;
    return { id: node.id, score, name: node.name, summary: node.summary };
  }).filter((candidate) => candidate.score > 0).sort((a, b) => b.score - a.score || a.id.localeCompare(b.id)).slice(0, 5);

  const codeStart = entryPointCandidates.find((candidate) => nodeById.get(candidate.id)?.type === 'file');
  const order = [], depthMap = {}, byDepth = {};
  if (codeStart) {
    const queue = [codeStart.id]; depthMap[codeStart.id] = 0;
    for (let head = 0; head < queue.length; head += 1) {
      const current = queue[head]; const depth = depthMap[current]; order.push(current);
      (byDepth[depth] ||= []).push(current);
      for (const next of adjacency.get(current) || []) if (!(next in depthMap)) { depthMap[next] = depth + 1; queue.push(next); }
    }
  }

  const nonCodeFiles = { documentation: [], infrastructure: [], data: [], config: [] };
  for (const node of nodes) {
    const item = { id: node.id, name: node.name, type: node.type, summary: node.summary };
    if (node.type === 'document') nonCodeFiles.documentation.push(item);
    else if (['service', 'pipeline', 'resource'].includes(node.type)) nonCodeFiles.infrastructure.push(item);
    else if (['table', 'schema', 'endpoint'].includes(node.type)) nonCodeFiles.data.push(item);
    else if (node.type === 'config') nonCodeFiles.config.push(item);
  }

  const undirected = new Map(nodes.map((node) => [node.id, new Set()]));
  for (const edge of edges) if (nodeById.has(edge.source) && nodeById.has(edge.target)) undirected.get(edge.source).add(edge.target);
  const pairs = [];
  for (const [source, targets] of undirected) for (const target of targets) if (undirected.get(target)?.has(source) && source < target) pairs.push([source, target]);
  const clusters = pairs.map(([a, b]) => {
    const group = new Set([a, b]);
    for (const candidate of nodes) {
      if (group.has(candidate.id)) continue;
      let links = 0; for (const member of group) if (undirected.get(candidate.id).has(member) || undirected.get(member).has(candidate.id)) links += 1;
      if (links >= 2 && group.size < 5) group.add(candidate.id);
    }
    let edgeCount = 0; for (const x of group) for (const y of undirected.get(x)) if (group.has(y)) edgeCount += 1;
    return { nodes: [...group], edgeCount };
  }).sort((a, b) => b.edgeCount - a.edgeCount).slice(0, 10);
  const layers = Array.isArray(graph.layers) ? graph.layers.map(({ id, name, description }) => ({ id, name, description })) : [];
  const nodeSummaryIndex = Object.fromEntries(nodes.map((node) => [node.id, { name: node.name, type: node.type, summary: node.summary }]));
  const result = { scriptCompleted: true, entryPointCandidates, fanInRanking, fanOutRanking, bfsTraversal: { startNode: codeStart?.id || null, order, depthMap, byDepth }, nonCodeFiles, clusters, layers: { count: layers.length, list: layers }, nodeSummaryIndex, totalNodes: nodes.length, totalEdges: edges.length };
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
  process.exit(0);
} catch (error) {
  console.error(error.stack || error.message);
  process.exit(1);
}
