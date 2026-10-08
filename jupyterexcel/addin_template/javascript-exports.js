(() => {
  'use strict';
  const registry = new Map();
  function validate(value, type, matrix = false) {
    if (matrix) {
      if (!Array.isArray(value) || !value.length || !Array.isArray(value[0]) || !value[0].length ||
          value.length * value[0].length > 5000 || value.some(row => !Array.isArray(row) || row.length !== value[0].length)) {
        throw new Error('Expected a rectangular matrix with 1-5000 cells.');
      }
      value.forEach(row => row.forEach(cell => validate(cell, type)));
    } else if (typeof value !== type || (type === 'number' && !Number.isFinite(value))) {
      throw new Error('Expected ' + type + '.');
    }
  }
  async function call(id, args, version) {
    const entry = registry.get(id);
    if (!entry) throw new Error('Unknown JavaScript export: ' + id);
    const {metadata, fn} = entry;
    if (version && version !== metadata.version) throw new Error('Function catalog changed. Reload the add-in.');
    args = args.slice();
    while (args.length && args[args.length - 1] === undefined) args.pop();
    if (args.length > metadata.parameters.length) throw new Error('Too many arguments.');
    metadata.parameters.forEach((p, i) => {
      if (args[i] === undefined && p.optional) return;
      validate(args[i], p.type, p.dimensionality === 'matrix');
    });
    let result;
    if (metadata.execution === 'local') result = await fn(...args);
    else result = await globalThis.JupyterExcel.call(metadata.endpoint + '?version=' + encodeURIComponent(metadata.version), args, true);
    const output = metadata.output;
    const parameterType = output.type === 'matrix' ? metadata.result_type : output.type;
    validate(result, parameterType, output.type === 'matrix');
    return result;
  }
  globalThis.JupyterExcelJavaScript = {call, validate,
    register(metadata, fn) { registry.set(metadata.id, {metadata, fn}); }};
})();
