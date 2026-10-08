(() => {
  // tools/sankey/node_modules/d3-array/src/max.js
  function max(values, valueof) {
    let max2;
    if (valueof === void 0) {
      for (const value2 of values) {
        if (value2 != null && (max2 < value2 || max2 === void 0 && value2 >= value2)) {
          max2 = value2;
        }
      }
    } else {
      let index = -1;
      for (let value2 of values) {
        if ((value2 = valueof(value2, ++index, values)) != null && (max2 < value2 || max2 === void 0 && value2 >= value2)) {
          max2 = value2;
        }
      }
    }
    return max2;
  }

  // tools/sankey/node_modules/d3-array/src/min.js
  function min(values, valueof) {
    let min2;
    if (valueof === void 0) {
      for (const value2 of values) {
        if (value2 != null && (min2 > value2 || min2 === void 0 && value2 >= value2)) {
          min2 = value2;
        }
      }
    } else {
      let index = -1;
      for (let value2 of values) {
        if ((value2 = valueof(value2, ++index, values)) != null && (min2 > value2 || min2 === void 0 && value2 >= value2)) {
          min2 = value2;
        }
      }
    }
    return min2;
  }

  // tools/sankey/node_modules/d3-array/src/sum.js
  function sum(values, valueof) {
    let sum2 = 0;
    if (valueof === void 0) {
      for (let value2 of values) {
        if (value2 = +value2) {
          sum2 += value2;
        }
      }
    } else {
      let index = -1;
      for (let value2 of values) {
        if (value2 = +valueof(value2, ++index, values)) {
          sum2 += value2;
        }
      }
    }
    return sum2;
  }

  // tools/sankey/node_modules/d3-sankey/src/align.js
  function justify(node, n) {
    return node.sourceLinks.length ? node.depth : n - 1;
  }

  // tools/sankey/node_modules/d3-sankey/src/constant.js
  function constant(x) {
    return function() {
      return x;
    };
  }

  // tools/sankey/node_modules/d3-sankey/src/sankey.js
  function ascendingSourceBreadth(a, b) {
    return ascendingBreadth(a.source, b.source) || a.index - b.index;
  }
  function ascendingTargetBreadth(a, b) {
    return ascendingBreadth(a.target, b.target) || a.index - b.index;
  }
  function ascendingBreadth(a, b) {
    return a.y0 - b.y0;
  }
  function value(d) {
    return d.value;
  }
  function defaultId(d) {
    return d.index;
  }
  function defaultNodes(graph) {
    return graph.nodes;
  }
  function defaultLinks(graph) {
    return graph.links;
  }
  function find(nodeById, id) {
    const node = nodeById.get(id);
    if (!node) throw new Error("missing: " + id);
    return node;
  }
  function computeLinkBreadths({ nodes }) {
    for (const node of nodes) {
      let y0 = node.y0;
      let y1 = y0;
      for (const link of node.sourceLinks) {
        link.y0 = y0 + link.width / 2;
        y0 += link.width;
      }
      for (const link of node.targetLinks) {
        link.y1 = y1 + link.width / 2;
        y1 += link.width;
      }
    }
  }
  function Sankey() {
    let x0 = 0, y0 = 0, x1 = 1, y1 = 1;
    let dx = 24;
    let dy = 8, py;
    let id = defaultId;
    let align = justify;
    let sort;
    let linkSort;
    let nodes = defaultNodes;
    let links = defaultLinks;
    let iterations = 6;
    function sankey() {
      const graph = { nodes: nodes.apply(null, arguments), links: links.apply(null, arguments) };
      computeNodeLinks(graph);
      computeNodeValues(graph);
      computeNodeDepths(graph);
      computeNodeHeights(graph);
      computeNodeBreadths(graph);
      computeLinkBreadths(graph);
      return graph;
    }
    sankey.update = function(graph) {
      computeLinkBreadths(graph);
      return graph;
    };
    sankey.nodeId = function(_) {
      return arguments.length ? (id = typeof _ === "function" ? _ : constant(_), sankey) : id;
    };
    sankey.nodeAlign = function(_) {
      return arguments.length ? (align = typeof _ === "function" ? _ : constant(_), sankey) : align;
    };
    sankey.nodeSort = function(_) {
      return arguments.length ? (sort = _, sankey) : sort;
    };
    sankey.nodeWidth = function(_) {
      return arguments.length ? (dx = +_, sankey) : dx;
    };
    sankey.nodePadding = function(_) {
      return arguments.length ? (dy = py = +_, sankey) : dy;
    };
    sankey.nodes = function(_) {
      return arguments.length ? (nodes = typeof _ === "function" ? _ : constant(_), sankey) : nodes;
    };
    sankey.links = function(_) {
      return arguments.length ? (links = typeof _ === "function" ? _ : constant(_), sankey) : links;
    };
    sankey.linkSort = function(_) {
      return arguments.length ? (linkSort = _, sankey) : linkSort;
    };
    sankey.size = function(_) {
      return arguments.length ? (x0 = y0 = 0, x1 = +_[0], y1 = +_[1], sankey) : [x1 - x0, y1 - y0];
    };
    sankey.extent = function(_) {
      return arguments.length ? (x0 = +_[0][0], x1 = +_[1][0], y0 = +_[0][1], y1 = +_[1][1], sankey) : [[x0, y0], [x1, y1]];
    };
    sankey.iterations = function(_) {
      return arguments.length ? (iterations = +_, sankey) : iterations;
    };
    function computeNodeLinks({ nodes: nodes2, links: links2 }) {
      for (const [i, node] of nodes2.entries()) {
        node.index = i;
        node.sourceLinks = [];
        node.targetLinks = [];
      }
      const nodeById = new Map(nodes2.map((d, i) => [id(d, i, nodes2), d]));
      for (const [i, link] of links2.entries()) {
        link.index = i;
        let { source, target } = link;
        if (typeof source !== "object") source = link.source = find(nodeById, source);
        if (typeof target !== "object") target = link.target = find(nodeById, target);
        source.sourceLinks.push(link);
        target.targetLinks.push(link);
      }
      if (linkSort != null) {
        for (const { sourceLinks, targetLinks } of nodes2) {
          sourceLinks.sort(linkSort);
          targetLinks.sort(linkSort);
        }
      }
    }
    function computeNodeValues({ nodes: nodes2 }) {
      for (const node of nodes2) {
        node.value = node.fixedValue === void 0 ? Math.max(sum(node.sourceLinks, value), sum(node.targetLinks, value)) : node.fixedValue;
      }
    }
    function computeNodeDepths({ nodes: nodes2 }) {
      const n = nodes2.length;
      let current = new Set(nodes2);
      let next = /* @__PURE__ */ new Set();
      let x = 0;
      while (current.size) {
        for (const node of current) {
          node.depth = x;
          for (const { target } of node.sourceLinks) {
            next.add(target);
          }
        }
        if (++x > n) throw new Error("circular link");
        current = next;
        next = /* @__PURE__ */ new Set();
      }
    }
    function computeNodeHeights({ nodes: nodes2 }) {
      const n = nodes2.length;
      let current = new Set(nodes2);
      let next = /* @__PURE__ */ new Set();
      let x = 0;
      while (current.size) {
        for (const node of current) {
          node.height = x;
          for (const { source } of node.targetLinks) {
            next.add(source);
          }
        }
        if (++x > n) throw new Error("circular link");
        current = next;
        next = /* @__PURE__ */ new Set();
      }
    }
    function computeNodeLayers({ nodes: nodes2 }) {
      const x = max(nodes2, (d) => d.depth) + 1;
      const kx = (x1 - x0 - dx) / (x - 1);
      const columns = new Array(x);
      for (const node of nodes2) {
        const i = Math.max(0, Math.min(x - 1, Math.floor(align.call(null, node, x))));
        node.layer = i;
        node.x0 = x0 + i * kx;
        node.x1 = node.x0 + dx;
        if (columns[i]) columns[i].push(node);
        else columns[i] = [node];
      }
      if (sort) for (const column of columns) {
        column.sort(sort);
      }
      return columns;
    }
    function initializeNodeBreadths(columns) {
      const ky = min(columns, (c) => (y1 - y0 - (c.length - 1) * py) / sum(c, value));
      for (const nodes2 of columns) {
        let y = y0;
        for (const node of nodes2) {
          node.y0 = y;
          node.y1 = y + node.value * ky;
          y = node.y1 + py;
          for (const link of node.sourceLinks) {
            link.width = link.value * ky;
          }
        }
        y = (y1 - y + py) / (nodes2.length + 1);
        for (let i = 0; i < nodes2.length; ++i) {
          const node = nodes2[i];
          node.y0 += y * (i + 1);
          node.y1 += y * (i + 1);
        }
        reorderLinks(nodes2);
      }
    }
    function computeNodeBreadths(graph) {
      const columns = computeNodeLayers(graph);
      py = Math.min(dy, (y1 - y0) / (max(columns, (c) => c.length) - 1));
      initializeNodeBreadths(columns);
      for (let i = 0; i < iterations; ++i) {
        const alpha = Math.pow(0.99, i);
        const beta = Math.max(1 - alpha, (i + 1) / iterations);
        relaxRightToLeft(columns, alpha, beta);
        relaxLeftToRight(columns, alpha, beta);
      }
    }
    function relaxLeftToRight(columns, alpha, beta) {
      for (let i = 1, n = columns.length; i < n; ++i) {
        const column = columns[i];
        for (const target of column) {
          let y = 0;
          let w = 0;
          for (const { source, value: value2 } of target.targetLinks) {
            let v = value2 * (target.layer - source.layer);
            y += targetTop(source, target) * v;
            w += v;
          }
          if (!(w > 0)) continue;
          let dy2 = (y / w - target.y0) * alpha;
          target.y0 += dy2;
          target.y1 += dy2;
          reorderNodeLinks(target);
        }
        if (sort === void 0) column.sort(ascendingBreadth);
        resolveCollisions(column, beta);
      }
    }
    function relaxRightToLeft(columns, alpha, beta) {
      for (let n = columns.length, i = n - 2; i >= 0; --i) {
        const column = columns[i];
        for (const source of column) {
          let y = 0;
          let w = 0;
          for (const { target, value: value2 } of source.sourceLinks) {
            let v = value2 * (target.layer - source.layer);
            y += sourceTop(source, target) * v;
            w += v;
          }
          if (!(w > 0)) continue;
          let dy2 = (y / w - source.y0) * alpha;
          source.y0 += dy2;
          source.y1 += dy2;
          reorderNodeLinks(source);
        }
        if (sort === void 0) column.sort(ascendingBreadth);
        resolveCollisions(column, beta);
      }
    }
    function resolveCollisions(nodes2, alpha) {
      const i = nodes2.length >> 1;
      const subject = nodes2[i];
      resolveCollisionsBottomToTop(nodes2, subject.y0 - py, i - 1, alpha);
      resolveCollisionsTopToBottom(nodes2, subject.y1 + py, i + 1, alpha);
      resolveCollisionsBottomToTop(nodes2, y1, nodes2.length - 1, alpha);
      resolveCollisionsTopToBottom(nodes2, y0, 0, alpha);
    }
    function resolveCollisionsTopToBottom(nodes2, y, i, alpha) {
      for (; i < nodes2.length; ++i) {
        const node = nodes2[i];
        const dy2 = (y - node.y0) * alpha;
        if (dy2 > 1e-6) node.y0 += dy2, node.y1 += dy2;
        y = node.y1 + py;
      }
    }
    function resolveCollisionsBottomToTop(nodes2, y, i, alpha) {
      for (; i >= 0; --i) {
        const node = nodes2[i];
        const dy2 = (node.y1 - y) * alpha;
        if (dy2 > 1e-6) node.y0 -= dy2, node.y1 -= dy2;
        y = node.y0 - py;
      }
    }
    function reorderNodeLinks({ sourceLinks, targetLinks }) {
      if (linkSort === void 0) {
        for (const { source: { sourceLinks: sourceLinks2 } } of targetLinks) {
          sourceLinks2.sort(ascendingTargetBreadth);
        }
        for (const { target: { targetLinks: targetLinks2 } } of sourceLinks) {
          targetLinks2.sort(ascendingSourceBreadth);
        }
      }
    }
    function reorderLinks(nodes2) {
      if (linkSort === void 0) {
        for (const { sourceLinks, targetLinks } of nodes2) {
          sourceLinks.sort(ascendingTargetBreadth);
          targetLinks.sort(ascendingSourceBreadth);
        }
      }
    }
    function targetTop(source, target) {
      let y = source.y0 - (source.sourceLinks.length - 1) * py / 2;
      for (const { target: node, width } of source.sourceLinks) {
        if (node === target) break;
        y += width + py;
      }
      for (const { source: node, width } of target.targetLinks) {
        if (node === source) break;
        y -= width;
      }
      return y;
    }
    function sourceTop(source, target) {
      let y = target.y0 - (target.targetLinks.length - 1) * py / 2;
      for (const { source: node, width } of target.targetLinks) {
        if (node === source) break;
        y += width + py;
      }
      for (const { target: node, width } of source.sourceLinks) {
        if (node === target) break;
        y -= width;
      }
      return y;
    }
    return sankey;
  }

  // jupyterexcel/sankey-client.js
  function graphFromRows(rows) {
    if (!Array.isArray(rows) || rows.length < 2 || rows.length > 501) throw new Error("Select headers and 1-500 flow rows.");
    const headers = rows[0].map((v) => String(v).trim().toLowerCase());
    const columns = ["source", "target", "value"].map((name) => {
      const index = headers.indexOf(name);
      if (index < 0 || headers.lastIndexOf(name) !== index) throw new Error("Required unique column: " + name);
      return index;
    });
    const nodes = /* @__PURE__ */ new Map(), pairs = /* @__PURE__ */ new Map();
    for (const [i, row] of rows.slice(1).entries()) {
      const [a, b, value2] = columns.map((c) => row[c]);
      if (typeof a !== "string" || typeof b !== "string" || !a.trim() || !b.trim()) throw new Error("Flow row " + (i + 1) + ": source and target must be text.");
      const source = a.trim(), target = b.trim();
      if (source.length > 60 || target.length > 60) throw new Error("Node labels must be at most 60 characters.");
      if (source === target) throw new Error("Self-links are not supported: " + source);
      if (typeof value2 !== "number" || !Number.isFinite(value2) || value2 <= 0) throw new Error("Flow row " + (i + 1) + ": value must be a positive number.");
      nodes.set(source, { id: source });
      nodes.set(target, { id: target });
      const key = JSON.stringify([source, target]);
      const link = pairs.get(key) || { source, target, value: 0 };
      link.value += value2;
      if (!Number.isFinite(link.value)) throw new Error("Flow total is too large.");
      pairs.set(key, link);
    }
    if (nodes.size > 40) throw new Error("Use at most 40 nodes for a readable diagram.");
    const graph = { nodes: [...nodes.values()], links: [...pairs.values()] };
    const height = Math.max(440, nodes.size * 24);
    try {
      Sankey().nodeId((d) => d.id).nodeWidth(18).nodePadding(16).extent([[190, 55], [810, height - 35]])(graph);
    } catch (error) {
      if (/circular/i.test(error.message)) throw new Error("Circular flows are not supported. Remove the cycle and try again.");
      throw error;
    }
    if (graph.nodes.some((n) => ![n.x0, n.x1, n.y0, n.y1].every(Number.isFinite))) throw new Error("Flow magnitudes cannot be laid out.");
    return { ...graph, width: 1e3, height };
  }
  function render(graph) {
    const canvas = document.createElement("canvas");
    canvas.width = graph.width * 2;
    canvas.height = graph.height * 2;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas rendering is unavailable.");
    ctx.scale(2, 2);
    ctx.fillStyle = "#FFFFFF";
    ctx.fillRect(0, 0, graph.width, graph.height);
    ctx.fillStyle = "#20252B";
    ctx.font = "bold 20px Arial";
    ctx.fillText("Sankey Diagram", 24, 30);
    const colors = ["#2878A0", "#239476", "#AD597F", "#B98422", "#6C72B5", "#B55746"];
    for (const link of graph.links) {
      ctx.beginPath();
      ctx.moveTo(link.source.x1, link.y0);
      const mid = (link.source.x1 + link.target.x0) / 2;
      ctx.bezierCurveTo(mid, link.y0, mid, link.y1, link.target.x0, link.y1);
      ctx.strokeStyle = colors[link.source.index % colors.length];
      ctx.globalAlpha = 0.32;
      ctx.lineWidth = Math.max(0.5, link.width);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    for (const node of graph.nodes) {
      ctx.fillStyle = colors[node.index % colors.length];
      ctx.fillRect(node.x0, node.y0, node.x1 - node.x0, Math.max(1, node.y1 - node.y0));
      const left2 = node.x0 < graph.width / 2;
      ctx.textAlign = left2 ? "right" : "left";
      ctx.fillStyle = "#20252B";
      ctx.font = "12px Arial";
      const label = node.id + " (" + Number(node.value.toPrecision(5)).toLocaleString() + ")";
      ctx.fillText(label, left2 ? node.x0 - 7 : node.x1 + 7, (node.y0 + node.y1) / 2 + 4, 180);
    }
    return canvas.toDataURL("image/png").split(",")[1];
  }
  function reference(json, single) {
    const ref = JSON.parse(json);
    if (!ref || typeof ref.sheetId !== "string" || !ref.sheetId || !["row", "column", "rows", "columns"].every((k) => Number.isInteger(ref[k])) || ref.row < 0 || ref.column < 0 || ref.rows < 1 || ref.columns < 1 || ref.row + ref.rows > 1048576 || ref.column + ref.columns > 16384 || ref.rows * ref.columns > 1503 || single && (ref.rows !== 1 || ref.columns !== 1)) {
      throw new Error("Select a valid " + (single ? "target cell." : "source range."));
    }
    return ref;
  }
  async function createSankey(sourceJson, targetJson) {
    if (!Office.context.requirements.isSetSupported("ExcelApi", "1.9")) throw new Error("Create Sankey requires ExcelApi 1.9 or later.");
    const source = reference(sourceJson, false), target = reference(targetJson, true);
    return Excel.run(async (context) => {
      const sourceSheet = context.workbook.worksheets.getItem(source.sheetId);
      const targetSheet = context.workbook.worksheets.getItem(target.sheetId);
      const data = sourceSheet.getRangeByIndexes(source.row, source.column, source.rows, source.columns).load("values");
      const cell = targetSheet.getRangeByIndexes(target.row, target.column, 1, 1).load("left,top,address");
      targetSheet.shapes.load("items/name,items/alternativeTextDescription");
      await context.sync();
      const graph = graphFromRows(data.values), png = render(graph);
      const marker = "JupyterExcel:CREATE_SANKEY:" + target.row + ":" + target.column;
      const previous = targetSheet.shapes.items.filter((s) => s.alternativeTextDescription === marker);
      const image = targetSheet.shapes.addImage(png);
      image.left = cell.left;
      image.top = cell.top;
      image.width = graph.width * 0.75;
      image.height = graph.height * 0.75;
      image.alternativeTextDescription = marker;
      try {
        await context.sync();
      } catch (error) {
        try {
          image.delete();
          await context.sync();
        } catch (_) {
        }
        throw error;
      }
      for (const old of previous) old.delete();
      targetSheet.activate();
      await context.sync();
      return "Sankey created at " + cell.address + ". Edit source values and rerun to refresh the image.";
    });
  }
  globalThis.JupyterExcelCharts = { createSankey, graphFromRows, render };
})();
