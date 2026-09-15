/** Saving must finish before requesting server execution. */
export async function saveAndReload<T>(
  save: () => Promise<void>,
  path: () => string,
  reload: (path: string) => Promise<T>
): Promise<T> {
  await save();
  const savedPath = path();
  if (!savedPath.endsWith('.ipynb')) {
    throw new Error('Select a saved notebook.');
  }
  return reload(savedPath);
}
