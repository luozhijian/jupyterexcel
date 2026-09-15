import { readFile, writeFile } from 'node:fs/promises';
const base = new URL('../jupyterexcel/labextension/', import.meta.url);
const path = new URL('package.json', base);
const metadata = JSON.parse(await readFile(path, 'utf8'));
// A Windows build must also load when the wheel is installed on Linux.
metadata.jupyterlab._build.load = metadata.jupyterlab._build.load.replaceAll('\\', '/');
await writeFile(path, JSON.stringify(metadata, null, 2) + '\n');
await writeFile(new URL('install.json', base), JSON.stringify({
  packageManager: 'python', packageName: 'jupyterexcel',
  uninstallInstructions: 'Use pip uninstall jupyterexcel to remove this extension.'
}, null, 2) + '\n');
