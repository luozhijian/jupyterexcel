// Supply credentials at runtime; no token is persisted in generated files.
// Optional integration hook: globalThis.jupyterExcelAuth = async () => ({token: '...', hub: false});
async function jupyterExcelCall(endpoint, args) {
  while (args.length && args[args.length - 1] === undefined) args.pop();
  const auth = typeof globalThis.jupyterExcelAuth === 'function' ? await globalThis.jupyterExcelAuth() : {};
  const url = new URL(endpoint);
  const headers = {'Content-Type': 'application/json'};
  if (auth.token) {
    if (auth.hub) headers.Authorization = 'token ' + auth.token;
    else url.searchParams.set('token', auth.token);
  }
  if (typeof document !== 'undefined') {
    const match = document.cookie.match(/(?:^|; )_xsrf=([^;]*)/);
    if (match) headers['X-XSRFToken'] = decodeURIComponent(match[1]);
  }
  const response = await fetch(url.toString(), {method: 'POST', credentials: 'include', headers, body: JSON.stringify(args)});
  const value = await response.json();
  if (!response.ok || !value.ok) throw new Error(value.error?.message || `Jupyter returned ${response.status}`);
  return value.result;
}
