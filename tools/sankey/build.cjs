const path = require('node:path');
require('esbuild').buildSync({
  entryPoints: [path.resolve(__dirname, '../../jupyterexcel/sankey-client.js')],
  nodePaths: [path.join(__dirname, 'node_modules')], bundle: true,
  format: 'iife', platform: 'browser',
  outfile: path.resolve(__dirname, '../../jupyterexcel/addin_template/sankey.bundle.js')
});
