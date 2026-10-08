import {sankey} from 'd3-sankey';

function graphFromRows(rows) {
  if (!Array.isArray(rows) || rows.length < 2 || rows.length > 501) throw new Error('Select headers and 1-500 flow rows.');
  const headers = rows[0].map(v => String(v).trim().toLowerCase());
  const columns = ['source', 'target', 'value'].map(name => {
    const index = headers.indexOf(name);
    if (index < 0 || headers.lastIndexOf(name) !== index) throw new Error('Required unique column: ' + name);
    return index;
  });
  const nodes = new Map(), pairs = new Map();
  for (const [i, row] of rows.slice(1).entries()) {
    const [a, b, value] = columns.map(c => row[c]);
    if (typeof a !== 'string' || typeof b !== 'string' || !a.trim() || !b.trim()) throw new Error('Flow row ' + (i + 1) + ': source and target must be text.');
    const source = a.trim(), target = b.trim();
    if (source.length > 60 || target.length > 60) throw new Error('Node labels must be at most 60 characters.');
    if (source === target) throw new Error('Self-links are not supported: ' + source);
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) throw new Error('Flow row ' + (i + 1) + ': value must be a positive number.');
    nodes.set(source, {id: source}); nodes.set(target, {id: target});
    const key = JSON.stringify([source, target]);
    const link = pairs.get(key) || {source, target, value: 0};
    link.value += value;
    if (!Number.isFinite(link.value)) throw new Error('Flow total is too large.');
    pairs.set(key, link);
  }
  if (nodes.size > 40) throw new Error('Use at most 40 nodes for a readable diagram.');
  const graph = {nodes: [...nodes.values()], links: [...pairs.values()]};
  const height = Math.max(440, nodes.size * 24);
  try {
    sankey().nodeId(d => d.id).nodeWidth(18).nodePadding(16)
      .extent([[190, 55], [810, height - 35]])(graph);
  } catch (error) {
    if (/circular/i.test(error.message)) throw new Error('Circular flows are not supported. Remove the cycle and try again.');
    throw error;
  }
  if (graph.nodes.some(n => ![n.x0, n.x1, n.y0, n.y1].every(Number.isFinite))) throw new Error('Flow magnitudes cannot be laid out.');
  return {...graph, width: 1000, height};
}

function render(graph) {
  const canvas = document.createElement('canvas');
  canvas.width = graph.width * 2; canvas.height = graph.height * 2;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas rendering is unavailable.');
  ctx.scale(2, 2);
  ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, graph.width, graph.height);
  ctx.fillStyle = '#20252B'; ctx.font = 'bold 20px Arial'; ctx.fillText('Sankey Diagram', 24, 30);
  const colors = ['#2878A0', '#239476', '#AD597F', '#B98422', '#6C72B5', '#B55746'];
  for (const link of graph.links) {
    ctx.beginPath(); ctx.moveTo(link.source.x1, link.y0);
    const mid = (link.source.x1 + link.target.x0) / 2;
    ctx.bezierCurveTo(mid, link.y0, mid, link.y1, link.target.x0, link.y1);
    ctx.strokeStyle = colors[link.source.index % colors.length];
    ctx.globalAlpha = 0.32; ctx.lineWidth = Math.max(0.5, link.width); ctx.stroke();
  }
  ctx.globalAlpha = 1;
  for (const node of graph.nodes) {
    ctx.fillStyle = colors[node.index % colors.length];
    ctx.fillRect(node.x0, node.y0, node.x1 - node.x0, Math.max(1, node.y1 - node.y0));
    const left = node.x0 < graph.width / 2;
    ctx.textAlign = left ? 'right' : 'left';
    ctx.fillStyle = '#20252B'; ctx.font = '12px Arial';
    const label = node.id + ' (' + Number(node.value.toPrecision(5)).toLocaleString() + ')';
    ctx.fillText(label, left ? node.x0 - 7 : node.x1 + 7, (node.y0 + node.y1) / 2 + 4, 180);
  }
  return canvas.toDataURL('image/png').split(',')[1];
}

function reference(json, single) {
  const ref = JSON.parse(json);
  if (!ref || typeof ref.sheetId !== 'string' || !ref.sheetId ||
      !['row', 'column', 'rows', 'columns'].every(k => Number.isInteger(ref[k])) ||
      ref.row < 0 || ref.column < 0 || ref.rows < 1 || ref.columns < 1 ||
      ref.row + ref.rows > 1048576 || ref.column + ref.columns > 16384 ||
      ref.rows * ref.columns > 1503 || (single && (ref.rows !== 1 || ref.columns !== 1))) {
    throw new Error('Select a valid ' + (single ? 'target cell.' : 'source range.'));
  }
  return ref;
}

async function createSankey(sourceJson, targetJson) {
  if (!Office.context.requirements.isSetSupported('ExcelApi', '1.9')) throw new Error('Create Sankey requires ExcelApi 1.9 or later.');
  const source = reference(sourceJson, false), target = reference(targetJson, true);
  return Excel.run(async context => {
    const sourceSheet = context.workbook.worksheets.getItem(source.sheetId);
    const targetSheet = context.workbook.worksheets.getItem(target.sheetId);
    const data = sourceSheet.getRangeByIndexes(source.row, source.column, source.rows, source.columns).load('values');
    const cell = targetSheet.getRangeByIndexes(target.row, target.column, 1, 1).load('left,top,address');
    targetSheet.shapes.load('items/name,items/alternativeTextDescription');
    await context.sync();
    const graph = graphFromRows(data.values), png = render(graph);
    const marker = 'JupyterExcel:CREATE_SANKEY:' + target.row + ':' + target.column;
    const previous = targetSheet.shapes.items.filter(s => s.alternativeTextDescription === marker);
    const image = targetSheet.shapes.addImage(png);
    image.left = cell.left; image.top = cell.top;
    image.width = graph.width * 0.75; image.height = graph.height * 0.75;
    image.alternativeTextDescription = marker;
    try {
      // Commit the replacement before removing our previous image.
      await context.sync();
    } catch (error) {
      try { image.delete(); await context.sync(); } catch (_) { /* Preserve original host error. */ }
      throw error;
    }
    for (const old of previous) old.delete();
    targetSheet.activate();
    await context.sync();
    return 'Sankey created at ' + cell.address + '. Edit source values and rerun to refresh the image.';
  });
}

globalThis.JupyterExcelCharts = {createSankey, graphFromRows, render};
