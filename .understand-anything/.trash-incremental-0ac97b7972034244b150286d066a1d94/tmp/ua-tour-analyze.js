#!/usr/bin/env node
/* Compute deterministic topology signals for the knowledge-graph tour builder. */
const fs = require('fs');

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  process.stderr.write('Usage: node ua-tour-analyze.js <graph.json> <results.json>\n');
  process.exit(1);
}

try {
  const graph = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  const nodeById = new Map(nodes.map(n => [n.id, n]));
  const fanIn = new Map(nodes.map(n => [n.id, 0]));
  const fanOut = new Map(nodes.map(n => [n.id, 0]));
  const forward = new Map(nodes.map(n => [n.id, []]));
  for (const edge of edges) {
    if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) continue;
    fanOut.set(edge.source, fanOut.get(edge.source) + 1);
    fanIn.set(edge.target, fanIn.get(edge.target) + 1);
    if (edge.type === 'imports' || edge.type === 'calls') forward.get(edge.source).push(edge.target);
  }
  const rank = (map, key) => nodes.map(n => ({ id: n.id, [key]: map.get(n.id), name: n.name }))
    .sort((a, b) => b[key] - a[key] || a.id.localeCompare(b.id)).slice(0, 20);
  const sortedFanOut = [...fanOut.values()].sort((a,b) => a-b);
  const sortedFanIn = [...fanIn.values()].sort((a,b) => a-b);
  const threshold = (xs, pct) => xs[Math.max(0, Math.ceil(xs.length * pct) - 1)] || 0;
  const highOut = threshold(sortedFanOut, .9), lowIn = threshold(sortedFanIn, .25);
  const names = new Set(['index.ts','index.js','main.ts','main.js','app.ts','app.js','server.ts','server.js','mod.rs','main.go','main.py','main.rs','manage.py','app.py','wsgi.py','asgi.py','run.py','__main__.py','Application.java','Main.java','Program.cs','config.ru','index.php','App.swift','Application.kt','main.cpp','main.c']);
  const candidates = nodes.map(n => {
    const path = n.filePath || '';
    const segments = path.split('/');
    let score = 0;
    if (n.type === 'document' && path === 'README.md') score += 5;
    else if (n.type === 'document' && path.endsWith('.md') && segments.length === 1) score += 2;
    if (n.type === 'file') {
      if (names.has(n.name)) score += 3;
      if (segments.length <= 2) score += 1;
      if (fanOut.get(n.id) >= highOut) score += 1;
      if (fanIn.get(n.id) <= lowIn) score += 1;
    }
    return {id:n.id, score, name:n.name, summary:n.summary};
  }).filter(c => c.score > 0).sort((a,b) => b.score-a.score || a.id.localeCompare(b.id)).slice(0,5);
  const start = candidates.find(c => nodeById.get(c.id)?.type === 'file')?.id || null;
  const order = [], depthMap = {}, byDepth = {};
  if (start) {
    const queue = [start]; depthMap[start] = 0;
    while (queue.length) {
      const id = queue.shift(); order.push(id); const d = depthMap[id];
      (byDepth[d] ||= []).push(id);
      for (const next of forward.get(id) || []) if (!(next in depthMap)) { depthMap[next] = d + 1; queue.push(next); }
    }
  }
  const byType = types => nodes.filter(n => types.includes(n.type)).map(n => ({id:n.id,name:n.name,type:n.type,summary:n.summary}));
  const directed = new Set(edges.filter(e => e.type === 'imports' || e.type === 'calls').map(e => `${e.source}\u0000${e.target}`));
  const clusters = []; const claimed = new Set();
  for (const key of directed) {
    const [a,b] = key.split('\u0000');
    if (!directed.has(`${b}\u0000${a}`) || claimed.has(a) || claimed.has(b)) continue;
    const group = [a,b];
    for (const n of nodes) if (group.length < 5 && !group.includes(n.id)) {
      const links = group.filter(g => directed.has(`${n.id}\u0000${g}`) || directed.has(`${g}\u0000${n.id}`)).length;
      if (links >= 2) group.push(n.id);
    }
    group.forEach(id => claimed.add(id));
    const edgeCount = edges.filter(e => group.includes(e.source) && group.includes(e.target)).length;
    clusters.push({nodes:group,edgeCount});
  }
  clusters.sort((a,b) => b.edgeCount-a.edgeCount).splice(10);
  const nodeSummaryIndex = Object.fromEntries(nodes.map(n => [n.id,{name:n.name,type:n.type,summary:n.summary}]));
  const result = {scriptCompleted:true,entryPointCandidates:candidates,fanInRanking:rank(fanIn,'fanIn'),fanOutRanking:rank(fanOut,'fanOut'),bfsTraversal:{startNode:start,order,depthMap,byDepth},nonCodeFiles:{documentation:byType(['document']),infrastructure:byType(['service','pipeline','resource']),data:byType(['table','schema','endpoint']),config:byType(['config'])},clusters,layers:{count:(graph.layers || []).length,list:(graph.layers || []).map(({id,name,description})=>({id,name,description}))},nodeSummaryIndex,totalNodes:nodes.length,totalEdges:edges.length};
  fs.writeFileSync(outputPath, JSON.stringify(result,null,2));
} catch (error) { process.stderr.write(`${error.message}\n`); process.exit(1); }
