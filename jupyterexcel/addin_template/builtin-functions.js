// Local diagnostics: no authentication, network request, or Python kernel.
// Capture this bundle's configuration, rather than another subsequently loaded version.
(() => {
  const config = { ...globalThis.JupyterExcelConfig };
  CustomFunctions.associate('MANIFESTURL', () => config.manifestUrl || '');
  CustomFunctions.associate('SERVERURL', () => config.apiBase || '');
  CustomFunctions.associate('ADDINVERSION', () => config.addinVersion || '');
  CustomFunctions.associate('ASSETVERSION', () => config.assetVersion || '');
})();
