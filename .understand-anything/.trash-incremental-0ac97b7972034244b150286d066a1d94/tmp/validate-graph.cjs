const fs = require('fs');
const graph = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const issues = [], warnings = [];
const validTypes = new Set(['file', 'function', 'class', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
const ids = new Set();
for (const [index, node] of graph.nodes.entries()) {
  if (!node.id || ids.has(node.id)) issues.push(`invalid or duplicate node at ${index}`);
  ids.add(node.id);
  if (!validTypes.has(node.type) || !node.name || !node.summary || !Array.isArray(node.tags) || !node.tags.length) issues.push(`invalid node metadata: ${node.id}`);
}
for (const edge of graph.edges) if (!ids.has(edge.source) || !ids.has(edge.target)) issues.push(`dangling edge: ${edge.source} -> ${edge.target}`);
const fileTypes = new Set(['file', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
const fileIds = graph.nodes.filter((node) => fileTypes.has(node.type)).map((node) => node.id);
const assigned = new Set();
for (const layer of graph.layers) {
  if (!layer.id || !layer.name || !layer.description || !Array.isArray(layer.nodeIds) || !layer.nodeIds.length) issues.push(`invalid layer: ${layer.id}`);
  for (const id of layer.nodeIds) { if (!ids.has(id) || assigned.has(id)) issues.push(`invalid layer reference: ${id}`); assigned.add(id); }
}
for (const id of fileIds) if (!assigned.has(id)) issues.push(`unassigned file node: ${id}`);
const orders = graph.tour.map((step) => step.order);
if (orders.some((order, index) => order !== index + 1)) issues.push('tour ordering is invalid');
for (const step of graph.tour) if (!step.title || !step.description || !Array.isArray(step.nodeIds) || !step.nodeIds.length || step.nodeIds.some((id) => !ids.has(id))) issues.push(`invalid tour step: ${step.order}`);
for (const node of graph.nodes) if (!graph.edges.some((edge) => edge.source === node.id || edge.target === node.id)) warnings.push(`orphan node: ${node.id}`);
const stats = { totalNodes: graph.nodes.length, totalEdges: graph.edges.length, totalLayers: graph.layers.length, tourSteps: graph.tour.length, nodeTypes: Object.fromEntries([...validTypes].map((type) => [type, graph.nodes.filter((node) => node.type === type).length])), edgeTypes: graph.edges.reduce((out, edge) => ((out[edge.type] = (out[edge.type] || 0) + 1), out), {}) };
fs.writeFileSync(process.argv[3], JSON.stringify({ issues, warnings, stats }, null, 2));
process.stdout.write(`Validation completed with ${issues.length} issue(s) and ${warnings.length} warning(s).\n`);
