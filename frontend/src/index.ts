import { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { ICommandPalette, Notification, ToolbarButton } from '@jupyterlab/apputils';
import { URLExt } from '@jupyterlab/coreutils';
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { ServerConnection } from '@jupyterlab/services';
import { DisposableDelegate } from '@lumino/disposable';
import { saveAndReload } from './workflow.js';

const command = 'jupyterexcel:save-and-reload';
const plugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyterexcel/labextension:save-and-reload',
  autoStart: true,
  requires: [INotebookTracker, ICommandPalette],
  activate: (app: JupyterFrontEnd, tracker: INotebookTracker, palette: ICommandPalette) => {
    const pending = new Set<NotebookPanel>();
    const panelFor = (id: unknown) => typeof id === 'string'
      ? tracker.find(panel => panel.id === id) : tracker.currentWidget;
    app.commands.addCommand(command, {
      label: 'Save and reload JupyterExcel',
      caption: 'Save this notebook, publish add-in assets, and rerun its code in the shared JupyterExcel kernel',
      isEnabled: args => {
        const panel = panelFor(args.notebookId);
        return !!panel && !panel.isDisposed && !panel.context.model.readOnly && !pending.has(panel);
      },
      execute: async args => {
        const panel = panelFor(args.notebookId);
        if (!panel || panel.isDisposed || pending.has(panel)) return;
        pending.add(panel);
        app.commands.notifyCommandChanged(command);
        const notice = Notification.emit('Saving notebook for JupyterExcel…', 'in-progress', {autoClose: false});
        try {
          await panel.context.ready;
          const settings = ServerConnection.makeSettings();
          const result = await saveAndReload(
            () => panel.context.save(),
            () => panel.context.path,
            async path => {
              Notification.update({id: notice, message: 'Generating assets and waiting for the JupyterExcel kernel…'});
              const url = URLExt.join(settings.baseUrl, 'jupyterexcel', 'api', 'reload');
              const response = await ServerConnection.makeRequest(url, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path})
              }, settings);
              const value = await response.json();
              if (!response.ok || !value.ok) {
                throw new Error(value.error?.message || `JupyterExcel returned HTTP ${response.status}`);
              }
              return value as {path: string};
            }
          );
          Notification.update({id: notice, type: 'success', message: `JupyterExcel reloaded: ${result.path}`, autoClose: 6000});
        } catch (error) {
          Notification.update({id: notice, type: 'error', autoClose: false,
            message: `JupyterExcel reload failed: ${error instanceof Error ? error.message : String(error)}`});
        } finally {
          pending.delete(panel);
          app.commands.notifyCommandChanged(command);
        }
      }
    });
    palette.addItem({command, category: 'JupyterExcel'});
    tracker.currentChanged.connect(() => app.commands.notifyCommandChanged(command));
    app.docRegistry.addWidgetExtension('Notebook', {
      createNew: widget => {
        const button = new ToolbarButton({label: 'Save & reload Excel',
          tooltip: 'Save and reload JupyterExcel: reruns notebook code; earlier cells may remain changed if a later cell fails',
          onClick: () => { void app.commands.execute(command, {notebookId: widget.id}); }});
        const update = () => { button.enabled = app.commands.isEnabled(command, {notebookId: widget.id}); };
        app.commands.commandChanged.connect(update);
        (widget as NotebookPanel).toolbar.insertItem(1, 'jupyterexcel-save-reload', button);
        update();
        return new DisposableDelegate(() => { app.commands.commandChanged.disconnect(update); button.dispose(); });
      }
    });
  }
};
export default plugin;
