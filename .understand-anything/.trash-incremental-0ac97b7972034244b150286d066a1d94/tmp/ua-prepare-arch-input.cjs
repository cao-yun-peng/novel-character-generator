const fs = require('fs');

const [graphPath, outputPath] = process.argv.slice(2);
if (!graphPath || !outputPath) {
  console.error('Usage: node ua-prepare-arch-input.cjs <assembled-graph.json> <input.json>');
  process.exit(1);
}

try {
  const graph = JSON.parse(fs.readFileSync(graphPath, 'utf8'));
  const fileTypes = new Set(['file', 'config', 'document', 'service', 'pipeline', 'table', 'schema', 'resource', 'endpoint']);
  const fileNodes = (graph.nodes || []).filter((node) => fileTypes.has(node.type));
  const ids = new Set(fileNodes.map((node) => node.id));
  const allEdges = (graph.edges || []).filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  const importEdges = allEdges.filter((edge) => edge.type === 'imports');
  fs.writeFileSync(outputPath, JSON.stringify({ fileNodes, importEdges, allEdges }, null, 2));
  process.stdout.write(`Prepared ${fileNodes.length} file nodes, ${importEdges.length} import edges, ${allEdges.length} file-level edges.\n`);
} catch (error) {
  console.error(error.stack || error.message);
  process.exit(1);
}
