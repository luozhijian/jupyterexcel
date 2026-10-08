const path = require('node:path');
require('esbuild').buildSync({
  entryPoints: [path.resolve(__dirname, '../../jupyterexcel/jsdoc_parser.cjs')],
  bundle: true,
  platform: 'node',
  nodePaths: [path.join(__dirname, 'node_modules')],
  outfile: path.resolve(__dirname, '../../jupyterexcel/jsdoc_parser.bundle.cjs'),
});
