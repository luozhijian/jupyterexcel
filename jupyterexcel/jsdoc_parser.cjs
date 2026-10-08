/* Build: npm exec -- esbuild jupyterexcel/jsdoc_parser.cjs --bundle --platform=node --outfile=jupyterexcel/jsdoc_parser.bundle.cjs */
const acorn = require('acorn');
const doctrine = require('doctrine');
const scope = require('eslint-scope');
const fs = require('node:fs');

const globals = new Set(['Math', 'Number', 'String', 'Boolean', 'Array', 'Object', 'JSON',
  'Date', 'RegExp', 'Map', 'Set', 'Promise', 'Error', 'TypeError', 'RangeError',
  'Intl', 'NaN', 'Infinity', 'undefined', 'parseInt', 'parseFloat', 'isNaN',
  'isFinite', 'encodeURIComponent', 'decodeURIComponent', 'console']);

function literal(node) {
  if (node.type === 'Literal' && !node.regex && typeof node.value !== 'bigint') return node.value;
  if (node.type === 'UnaryExpression' && node.operator === '-' && node.argument.type === 'Literal' && typeof node.argument.value === 'number') return -node.argument.value;
  throw new Error('Defaults must be scalar literals.');
}
function valueType(node) {
  if (!node) throw new Error('Declare a parameter/return type.');
  if (node.type === 'OptionalType') return valueType(node.expression);
  if (node.type === 'TypeApplication') {
    if (node.expression.name === 'Promise' && node.applications.length === 1) return valueType(node.applications[0]);
    if (node.expression.name === 'Array' && node.applications.length === 1) return valueType(node.applications[0]) + '[]';
  }
  if (node.type === 'NameExpression' && ['number', 'string', 'boolean'].includes(node.name)) return node.name;
  throw new Error('Supported types: number, string, boolean, their 2D arrays, and Promise of these.');
}
function parse(source) {
  const comments = [];
  const ast = acorn.parse(source, {ecmaVersion: 2022, sourceType: 'module', ranges: true, onComment: comments});
  const found = [];
  for (const comment of comments.filter(c => c.type === 'Block' && c.value.startsWith('*'))) {
    const normalized = comment.value.replace(/@jupyter_function\b/g, '@excelFunction').replace(/@ribbon_function\b/g, '@ribbonFunction')
      .replace(/(@(?:param|returns|return)\s*\{)([^}]+)(\})/g, (_, start, type, end) =>
        start + type.replace(/\b(number|string|boolean)\[\]\[\]/g, 'Array.<Array.<$1>>') + end);
    const doc = doctrine.parse(normalized, {unwrap: true, sloppy: true, recoverable: true});
    const exports = doc.tags.filter(t => ['excelFunction', 'jupyter_function', 'ribbonFunction', 'ribbon_function'].includes(t.title));
    if (!exports.length) continue;
    for (const tag of doc.tags) if (tag.errors?.length) throw new Error('@' + tag.title + ': ' + tag.errors.join(', '));
    if (exports.length !== 1) throw new Error('Use exactly one export annotation per function.');
    const node = ast.body.find(n => n.start >= comment.end);
    if (!node || node.type !== 'FunctionDeclaration' || !node.id || node.generator || source.slice(comment.end, node.start).trim()) {
      throw new Error('Export annotations must immediately precede a named top-level function declaration.');
    }
    const single = title => {
      const tags = doc.tags.filter(t => t.title === title);
      if (tags.length > 1) throw new Error('Duplicate @' + title);
      return tags[0]?.description?.trim();
    };
    const execution = single('execution');
    const ribbon = exports[0].title.startsWith('ribbon');
    const output = single('output');
    if (output !== undefined && (output !== 'status' || !ribbon || execution !== 'local')) throw new Error('@output status requires a local ribbon function.');
    if (!['local', 'server'].includes(execution)) throw new Error('Declare @execution local or @execution server.');
    const parameters = doc.tags.filter(t => t.title === 'param');
    const selectors = new Map();
    for (const tag of doc.tags.filter(t => ['rangeInput', 'cellInput'].includes(t.title))) {
      const name = tag.description?.trim();
      if (!ribbon || execution !== 'local' || selectors.has(name) || !parameters.some(p => p.name === name)) throw new Error('Range/cell inputs require unique local ribbon parameters.');
      selectors.set(name, tag.title === 'cellInput' ? 'cell' : 'range');
    }
    if (parameters.length !== node.params.length) throw new Error('@param entries must match the function parameters in order.');
    const inputs = node.params.map((p, i) => {
      const identifier = p.type === 'AssignmentPattern' ? p.left : p;
      const tag = parameters[i];
      if (identifier.type !== 'Identifier' || tag.name !== identifier.name) throw new Error('@param names/order must match plain named parameters.');
      const optional = p.type === 'AssignmentPattern';
      if (optional !== (tag.type?.type === 'OptionalType')) throw new Error('Optional JSDoc parameters must match JavaScript defaults.');
      const result = {name: tag.name, type: valueType(tag.type), description: tag.description || tag.name, optional};
      if (selectors.has(tag.name)) {
        if (result.type !== 'string' || optional) throw new Error('Range/cell selectors require a required string parameter.');
        result.selector = selectors.get(tag.name);
      }
      if (optional) {
        result.default = literal(p.right);
        if (tag.default === undefined) throw new Error('Include the default in @param [name=value].');
        const expression = acorn.parseExpressionAt(tag.default, 0, {ecmaVersion: 2022});
        if (expression.end !== tag.default.length || literal(expression) !== result.default) throw new Error('JSDoc default differs from JavaScript default.');
      }
      return result;
    });
    const returns = doc.tags.filter(t => ['returns', 'return'].includes(t.title));
    if (returns.length !== 1) throw new Error('Declare exactly one @returns type.');
    const code = source.slice(node.start, node.end);
    if (execution === 'local') {
      const tree = acorn.parse(code, {ecmaVersion: 2022, sourceType: 'module', ranges: true});
      const unresolved = scope.analyze(tree, {ecmaVersion: 2022, sourceType: 'module'}).globalScope.through;
      const unsupported = [...new Set(unresolved.map(r => r.identifier.name).filter(n => !globals.has(n) && !(ribbon && ['Excel', 'Office', 'JupyterExcelCharts'].includes(n))))];
      if (unsupported.length) throw new Error('Local exports must be self-contained. Unsupported dependencies: ' + unsupported.join(', ') + '. Use @execution server.');
    }
    found.push({name: node.id.name, id: exports[0].description?.trim() || node.id.name,
      kind: exports[0].title.startsWith('ribbon') ? 'ribbon' : 'jupyter', execution, source: code,
      execution_profile: single('executionProfile'), output,
      description: single('description') || doc.description || node.id.name,
      label: single('label'), button_text: single('buttonText'), inputs,
      result: valueType(returns[0].type), result_description: returns[0].description || '',
      remarks: single('remarks') || '', side_effects: single('sideEffects') || '',
      examples: doc.tags.filter(t => t.title === 'example').map(t => t.description || ''),
      related: doc.tags.filter(t => t.title === 'see').map(t => t.description || '')});
  }
  return found;
}
try {
  const cells = JSON.parse(fs.readFileSync(0, 'utf8'));
  console.log(JSON.stringify(cells.map((source, index) => {
    try { return parse(source); }
    catch (error) {
      if (!/@(?:excelFunction|jupyter_function|ribbonFunction|ribbon_function)\b/.test(source)) return [];
      throw new Error('Cell ' + (index + 1) + ': ' + error.message);
    }
  })));
} catch (error) { console.error(error.message); process.exitCode = 1; }
