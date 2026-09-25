/* global Excel, Office */
(() => {
  'use strict';
  const MAX_CELLS = 5000;
  function matrix(value) {
    if (!Array.isArray(value) || !value.length || !Array.isArray(value[0]) || !value[0].length ||
        value.length * value[0].length > MAX_CELLS || value.some(row => !Array.isArray(row) || row.length !== value[0].length)) {
      throw new Error('Expected a rectangular result with 1–5000 cells.');
    }
    for (const row of value) for (const cell of row) {
      if (cell !== null && !['string', 'number', 'boolean'].includes(typeof cell)) throw new Error('Unsupported result cell.');
      if (typeof cell === 'number' && !Number.isFinite(cell)) throw new Error('Non-finite result.');
    }
    return value;
  }
  function excelLiteral(value) {
    // Returned strings are data, never executable Excel formulas.
    return typeof value === 'string' && /^[=+\-@]/.test(value) ? "'" + value : value === null ? '' : value;
  }
  function overlaps(a, b) {
    return a.sheetId === b.sheetId && a.row < b.row+b.rows && b.row < a.row+a.rows &&
      a.column < b.column+b.columns && b.column < a.column+a.columns;
  }
  function parseValue(field, input) {
    if (field.type === 'boolean') return input.checked;
    if (field.type === 'number') {
      if (!input.value.trim() || !Number.isFinite(Number(input.value))) throw new Error('Enter a valid number.');
      return Number(input.value);
    }
    if (field.type === 'matrix') return matrix(JSON.parse(input.value));
    if (!input.value.length) throw new Error('Enter a value.');
    return input.value;
  }
  function cellBlock(value, columns) {
    const block = value && !Array.isArray(value) && typeof value === 'object' ? value :
      {values: columns ? [columns, ...matrix(value)] : Array.isArray(value) ? value : [[value]]};
    if (!block || Object.keys(block).some(k => !['values','format'].includes(k))) throw new Error('Invalid cell data.');
    matrix(block.values);
    if (block.format !== undefined) {
      if (!block.format || Object.keys(block.format).some(k => k !== 'fillColors')) throw new Error('Unsupported result format.');
      const colors = block.format.fillColors;
      if (colors !== undefined) {
        matrix(colors);
        if (colors.length !== block.values.length || colors[0].length !== block.values[0].length) throw new Error('Colors must match values dimensions.');
        for (const row of colors) for (const color of row) {
          if (color !== null && color !== '' && (typeof color !== 'string' || !/^#[0-9a-f]{6}$/i.test(color))) throw new Error('Invalid fill color.');
        }
      }
    }
    return block;
  }
  function applyFills(range, colors, offset = 0, count = MAX_CELLS) {
    if (!colors) return;
    const width = colors[0].length;
    for (let i = offset; i < Math.min(offset + count, colors.length * width); i++) {
      const r = Math.floor(i / width), c = i % width, color = colors[r][c];
      if (color === null) continue;
      const fill = range.getCell(r,c).format.fill;
      if (color === '') fill.clear(); else fill.color = color;
    }
  }
  function eventTouchesInput(event, inputs, formatOnly = false) {
    const relevant = inputs.filter(input => input.sheetId === event.worksheetId && (!formatOnly || input.format));
    if (!relevant.length) return false;
    // Structural edits can shift inputs even when the reported cells do not overlap.
    if (!formatOnly && event.changeType && event.changeType !== 'RangeEdited') return true;
    if (typeof event.address !== 'string' || !event.address.trim()) return true;
    const column = text => [...text.toUpperCase()].reduce((n, c) => n * 26 + c.charCodeAt(0) - 64, 0) - 1;
    // Strip optional sheet qualifiers, including quoted names containing commas.
    const address = event.address.replace(/(?:'(?:[^']|'')*'|[^!,]+)!/g, '');
    return address.split(',').some(part => {
      const text = part.trim().replace(/\$/g, '');
      let match = /^([A-Z]+)([1-9]\d*)(?::([A-Z]+)([1-9]\d*))?$/i.exec(text);
      let row, col, lastRow, lastCol;
      if (match) {
        row = Number(match[2]) - 1; col = column(match[1]);
        lastRow = Number(match[4] || match[2]) - 1; lastCol = column(match[3] || match[1]);
      } else if ((match = /^([A-Z]+):([A-Z]+)$/i.exec(text))) {
        row = 0; lastRow = 1048575; col = column(match[1]); lastCol = column(match[2]);
      } else if ((match = /^([1-9]\d*):([1-9]\d*)$/.exec(text))) {
        row = Number(match[1]) - 1; lastRow = Number(match[2]) - 1; col = 0; lastCol = 16383;
      } else return true; // Unknown event addresses must not make stale results writable.
      const changed = {sheetId: event.worksheetId, row: Math.min(row, lastRow), column: Math.min(col, lastCol),
        rows: Math.abs(lastRow - row) + 1, columns: Math.abs(lastCol - col) + 1};
      return relevant.some(input => overlaps(input, changed));
    });
  }
  function createInputMonitor(excel, supportsFormat, invalidate, ignore = () => false) {
    let generation = 0, handles = [], queue = Promise.resolve();
    const enqueue = operation => {
      const pending = queue.then(operation);
      queue = pending.catch(() => {});
      return pending;
    };
    async function removeHandlers() {
      const remaining = [], errors = [];
      for (const handle of handles) {
        try {
          await excel.run(handle.context, async context => {
            handle.remove();
            await context.sync();
          });
        } catch (error) { remaining.push(handle); errors.push(error); }
      }
      handles = remaining;
      if (errors.length) throw errors[0];
    }
    return {
      stop() {
        generation++; // Queued events become inert before asynchronous removal starts.
        return enqueue(removeHandlers);
      },
      start(inputs) {
        const current = ++generation;
        const watched = inputs.map(input => ({...input}));
        return enqueue(async () => {
          await removeHandlers();
          if (current !== generation) return;
          try {
            await excel.run(async context => {
              for (const sheetId of new Set(watched.map(input => input.sheetId))) {
                const sheet = context.workbook.worksheets.getItem(sheetId);
                const handler = format => event => {
                  if (current === generation && !ignore() && eventTouchesInput(event, watched, format)) invalidate();
                };
                handles.push(sheet.onChanged.add(handler(false)));
                if (watched.some(input => input.sheetId === sheetId && input.format)) {
                  if (!supportsFormat()) throw new Error('Monitoring fill changes requires ExcelApi 1.9.');
                  handles.push(sheet.onFormatChanged.add(handler(true)));
                }
              }
              await context.sync();
            });
          } catch (error) {
            if (current === generation) generation++;
            try { await removeHandlers(); } catch (_) { /* Retain failed removals for the next attempt. */ }
            throw error;
          }
        });
      }
    };
  }
  const helpers = {matrix, excelLiteral, overlaps, parseValue, cellBlock, applyFills, eventTouchesInput, createInputMonitor};
  if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
  if (typeof document === 'undefined') return;
  const $ = id => document.getElementById(id);
  let actions = [], controls = [], busy = false, result = null, targets = {}, outputTarget = null;
  let revision = 0, resultRevision = -1, writing = false;
  const inputMonitor = createInputMonitor(Excel,
    () => Office.context.requirements.isSetSupported('ExcelApi', '1.9'), stale, () => writing);
  async function stopMonitoring() {
    try { await inputMonitor.stop(); }
    catch (error) { console.warn('Could not remove action input event handlers:', error); }
  }
  function inputsChanged() {
    stale();
    void stopMonitoring();
  }
  let selectionField = null, selectionSequence = 0;
  function stopSelection() {
    if (selectionField) selectionField.input.classList.remove('range-picking');
    selectionField = null; selectionSequence++;
  }
  function activateSelection(field) {
    if (busy) return;
    stopSelection(); selectionField = field;
    field.input.classList.add('range-picking');
    status(field.output ? 'Select one Starting Cell in Excel.' : 'Select input cells in Excel.');
    captureSelection();
  }
  async function captureSelection() {
    if (!selectionField || busy) return;
    const field = selectionField, sequence = ++selectionSequence;
    try {
      const ref = await selectedReference(field.single, field.limit);
      if (sequence !== selectionSequence || field !== selectionField || busy) return;
      field.set(ref); field.input.value = ref.address; updateButtons();
    } catch (error) {
      if (sequence === selectionSequence && field === selectionField) {
        field.set(null); field.input.value = ''; status(error.message); updateButtons();
      }
    }
  }
  function action() { return actions.find(item => item.id === $('action-select').value); }
  function status(text) { $('action-status').textContent = text; }
  function stale() {
    if (writing) return;
    revision++;
    if (result) { status('Result is out of date. Run again before writing.'); updateButtons(); }
  }
  function element(tag, text) { const e = document.createElement(tag); if (text) e.textContent = text; return e; }
  function validInputs() {
    if (!action()) return false;
    try {
      for (const group of controls) {
        if (!group.entries.length) return false;
        for (const entry of group.entries) {
          if (group.field.source === 'value') parseValue(group.field, entry.input);
          else if (!entry.reference) return false;
        }
      }
      return true;
    } catch (_) { return false; }
  }
  function updateButtons() {
    $('action-run').disabled = busy || !validInputs();
    $('action-inputs').disabled = busy;
    $('action-select').disabled = busy;
    const usable = !!result && resultRevision === revision && !busy;
    $('action-write').disabled = !usable || !outputTarget;
    $('action-updates').disabled = !usable;
    $('action-target').disabled = busy;
    $('action-popup').disabled = !usable;
  }
  async function selectedReference(single, limit = MAX_CELLS) {
    return Excel.run(async context => {
      const range = context.workbook.getSelectedRange();
      range.load('address,rowIndex,columnIndex,rowCount,columnCount');
      range.worksheet.load('id');
      await context.sync();
      if (single && range.rowCount*range.columnCount !== 1) throw new Error('Select exactly one cell.');
      if (range.rowCount*range.columnCount > limit) throw new Error(`Select at most ${limit} cells.`);
      return {sheetId: range.worksheet.id, address: range.address, row: range.rowIndex,
        column: range.columnIndex, rows: range.rowCount, columns: range.columnCount};
    });
  }
  function addEntry(group) {
    const {field, container} = group;
    if (group.entries.length >= 50) return;
    const row = element('div'); row.className = 'action-input-row';
    const input = element(field.type === 'choice' && field.source === 'value' ? 'select' : field.type === 'matrix' && field.source === 'value' ? 'textarea' : 'input');
    input.setAttribute('aria-label', field.label || field.name);
    const entry = {input, reference: null}; group.entries.push(entry);
    if (field.source === 'value') {
      if (field.type === 'choice') for (const choice of field.choices) input.add(new Option(choice, choice));
      else if (field.type === 'boolean') input.type = 'checkbox';
      else if (field.type === 'number') { input.type = 'number'; input.step = 'any'; }
      if ('default' in field) {
        if (field.type === 'boolean') input.checked = field.default;
        else input.value = field.type === 'matrix' ? JSON.stringify(field.default) : field.default;
      }
      input.oninput = () => { inputsChanged(); updateButtons(); };
    } else {
      input.readOnly = true; input.placeholder = 'Click here, then select cells in Excel';
      input.onclick = () => activateSelection({input, single: field.source === 'cell', limit: field.max_cells,
        set: ref => { entry.reference = ref; inputsChanged(); }});

    }
    row.prepend(input);
    if (field.repeatable) {
      const remove = element('button', 'Remove'); remove.type = 'button';
      remove.onclick = () => { stopSelection(); group.entries.splice(group.entries.indexOf(entry), 1); row.remove(); inputsChanged(); updateButtons(); };
      row.appendChild(remove);
    }
    container.appendChild(row); updateButtons();
  }
  function selectAction() {
    void stopMonitoring();
    stopSelection(); controls = []; result = null; targets = {}; outputTarget = null; revision++;
    $('action-inputs').replaceChildren(); $('action-result').replaceChildren(); $('action-target').value = '';
    for (const id of ['action-target-label','action-write','action-popup','action-updates']) $(id).hidden = true;
    const selected = action();
    $('action-target-label').hidden = !selected?.output.destinations.includes('range');
    $('action-description').textContent = selected?.description || '';
    $('action-run').textContent = selected?.button_text || 'Run';
    for (const field of selected?.inputs || []) {
      const container = element('section'); container.appendChild(element('strong', field.label || field.name));
      const group = {field, container, entries: []}; controls.push(group);
      $('action-inputs').appendChild(container); addEntry(group);
      if (field.repeatable) {
        const add = element('button', 'Add input'); add.type = 'button';
        add.onclick = () => { addEntry(group); inputsChanged(); updateButtons(); }; container.appendChild(add);
      }
    }
    status(selected ? 'Choose inputs, then run.' : 'No actions found. Save a notebook with a ribbon_function action, then use Reload add-in on the Token page.');
    updateButtons();
  }
  async function refresh() {
    busy = true; updateButtons();
    try {
      const response = await fetch('actions.json', {cache: 'no-store', credentials: 'omit'});
      if (!response.ok) throw new Error('Could not load actions.json. Regenerate the add-in assets.');
      const catalog = await response.json();
      if (catalog.version !== 1 || !Array.isArray(catalog.actions)) throw new Error('Unsupported action catalog.');
      actions = catalog.actions;
      $('action-select').replaceChildren();
      for (const item of actions) $('action-select').add(new Option(item.label, item.id));
      selectAction();
    } catch (error) { status(error.message); }
    finally { busy = false; updateButtons(); }
  }
  function normalizeColor(color) {
    if (/^#?[0-9a-f]{6}$/i.test(color || '')) return '#' + color.replace('#', '').toUpperCase();
    if (!color || !CSS.supports('color', color)) throw new Error('Could not read a supported fill color.');
    const canvas = document.createElement('canvas'); const context = canvas.getContext('2d');
    context.fillStyle = color;
    if (!/^#[0-9a-f]{6}$/i.test(context.fillStyle)) throw new Error('Unsupported fill color.');
    return context.fillStyle.toUpperCase();
  }
  async function readReference(field, ref) {
    return Excel.run(async context => {
      const range = context.workbook.worksheets.getItem(ref.sheetId).getRangeByIndexes(ref.row, ref.column, ref.rows, ref.columns);
      range.load('values,valueTypes');
      const wantsFill = field.read.some(p => p === 'format.fillColors');
      if (wantsFill && !Office.context.requirements.isSetSupported('ExcelApi', '1.9')) throw new Error('Reading fill patterns requires ExcelApi 1.9.');
      if (wantsFill) range.conditionalFormats.load('items');
      await context.sync();
      if (range.valueTypes.some(row => row.some(type => type === 'Error'))) throw new Error(`Excel error cell in ${ref.address}. Correct it before running.`);
      if (wantsFill && range.conditionalFormats.items.length) throw new Error('Conditional formatting is not supported in version one. Select cells with manual fills only.');
      const data = {values: range.values};
      if (wantsFill) {
        const colors = Array.from({length: ref.rows}, () => Array(ref.columns));
        // Batch host calls instead of syncing once per cell.
        for (let offset = 0; offset < ref.rows*ref.columns; offset += 250) {
          const cells = [];
          for (let i = offset; i < Math.min(offset+250, ref.rows*ref.columns); i++) {
            const r = Math.floor(i/ref.columns), c = i%ref.columns;
            const fill = range.getCell(r,c).format.fill; fill.load('color,pattern'); cells.push({r,c,fill});
          }
          await context.sync();
          for (const {r,c,fill} of cells) {
            // Some hosts return null patterns for individual cells; use their reported background color.
            const pattern = fill.pattern === null && typeof fill.color === 'string'
              ? (fill.color === '' ? 'None' : 'Solid') : fill.pattern;
            if (!['None','Solid'].includes(pattern)) {
              let column = '', n = ref.column + c + 1;
              while (n > 0) { n--; column = String.fromCharCode(65 + n % 26) + column; n = Math.floor(n / 26); }
              const cell = column + (ref.row + r + 1);
              throw new Error(`Unsupported fill pattern ${JSON.stringify(fill.pattern) ?? 'undefined'} at ${cell} (selection ${ref.address}). Use a solid fill or No Fill; patterned and gradient fills are not supported.`);
            }
            colors[r][c] = pattern === 'None' ? '' : normalizeColor(fill.color);
          }
        }
        data.format = {fillColors: colors};
      }
      return data;
    });
  }
  function table(value, columns) {
    const block = cellBlock(value, columns);
    const table = element('table');
    block.values.forEach((row,r) => {
      const tr = element('tr');
      row.forEach((cell,c) => {
        const td = element('td', cell === null ? '' : String(cell));
        const color = block.format?.fillColors?.[r]?.[c];
        if (color) {
          td.style.backgroundColor = color;
          const rgb = color.slice(1).match(/../g).map(v => parseInt(v,16));
          td.style.color = rgb[0]*0.299 + rgb[1]*0.587 + rgb[2]*0.114 < 140 ? 'white' : 'black';
        }
        tr.appendChild(td);
      });
      table.appendChild(tr);
    });
    return table;
  }
  async function run() {
    if (!validInputs() || busy) return;
    stopSelection();
    const selected = action(), startedRevision = revision;
    busy = true; result = null; updateButtons(); $('action-result').replaceChildren(); status('Reading inputs…');
    try {
      await inputMonitor.start(controls.flatMap(group => group.field.source === 'value' ? [] :
        group.entries.map(entry => ({...entry.reference,
          format: (group.field.read || []).includes('format.fillColors')}))));
      const args = []; targets = {};
      for (const group of controls) {
        const values = [];
        for (const entry of group.entries) {
          values.push(group.field.source === 'value' ? parseValue(group.field, entry.input) : await readReference(group.field, entry.reference));
        }
        args.push(group.field.repeatable ? values : values[0]);
        if (group.field.source !== 'value') targets[group.field.name] = group.entries.map(e => ({...e.reference}));
      }
      if (revision !== startedRevision) throw new Error('Workbook changed while reading. Run again.');
      status('Running Python…');
      result = await globalThis.JupyterExcel.callAction(selected.id, args);
      resultRevision = startedRevision;
      $('action-result').appendChild(table(result.result, result.columns));
      const destinations = selected.output.destinations;
      for (const id of ['action-target-label','action-write']) $(id).hidden = !destinations.includes('range');
      $('action-popup').hidden = !destinations.includes('popup');
      $('action-updates').hidden = !Object.keys(result.updates || {}).length;
      status(revision === startedRevision ? 'Completed. Result is a snapshot; run again after changes.' : 'Result is out of date. Run again before writing.');
      if (selected.output.default === 'popup') showPopup();
    } catch (error) {
      result = null;
      await stopMonitoring();
      status(error.message + ' No automatic retry was performed.');
    } finally { busy = false; updateButtons(); }
    if (result && resultRevision === revision && selected.output.default === 'range') {
      if (outputTarget) await write(false);
      else status('Result ready. Select a Starting Cell, then click Write to cells.');
    }
  }
  function showPopup() {
    if (!result) return;
    $('action-dialog-content').replaceChildren(table(result.result, result.columns));
    $('action-dialog').showModal();
  }
  async function write(updates = false) {
    if (!result || resultRevision !== revision || busy) return;
    stopSelection(); busy = true; updateButtons();
    try {
      const jobs = [];
      if (updates) {
        for (const [name, update] of Object.entries(result.updates || {})) {
          const refs = targets[name];
          if (!refs || refs.length !== 1) throw new Error('Invalid input update target.');
          const block = cellBlock(update), values = block.values, ref = refs[0];
          if (values.length !== ref.rows || values[0].length !== ref.columns) throw new Error('Update dimensions must match the selected input.');
          jobs.push({ref,values,colors: block.format?.fillColors});
        }
      } else {
        if (!outputTarget) throw new Error('Select an output cell.');
        const block = cellBlock(result.result, result.columns), values = block.values;
        const ref = {...outputTarget, rows: values.length, columns: values[0].length};
        if (Object.values(targets).flat().some(input => overlaps(input,ref))) throw new Error('Choose an output area outside the input ranges.');
        jobs.push({ref,values,colors: block.format?.fillColors});
      }
      if (jobs.some((job,i) => jobs.slice(0,i).some(other => overlaps(job.ref,other.ref)))) throw new Error('Update targets overlap.');
      const writeRevision = revision;
      await Excel.run(async context => {
        const pending = jobs.map(job => {
          const {ref} = job;
          const range = context.workbook.worksheets.getItem(ref.sheetId).getRangeByIndexes(ref.row,ref.column,ref.rows,ref.columns);
          range.load('values,formulas,address'); return {...job,range};
        });
        await context.sync();
        const occupied = pending.some(p => p.range.formulas.some(row => row.some(v => v !== '' && v !== null)));
        if (updates || occupied) {
          const allowed = await confirmWrite(`Write to ${pending.map(p => p.range.address).join(', ')}? Existing values, formulas, or requested fill colors may be replaced.`, pending);
          if (!allowed) { status('Write cancelled. Result remains available in the task pane.'); return; }
        }
        if (revision !== writeRevision) throw new Error('Workbook changed before writing. Run again.');
        writing = true; // Ignore our own events only during the actual write.
        for (const job of pending) job.range.values = job.values.map(row => row.map(excelLiteral));
        await context.sync();
        for (const job of pending) {
          if (!job.colors) continue;
          for (let offset = 0; offset < job.values.length * job.values[0].length; offset += 250) {
            applyFills(job.range, job.colors, offset, 250);
            await context.sync();
          }
        }
        status('Written to worksheet.' + new Date().toLocaleString());
        resultRevision = -1;
      });
    } catch (error) { status(error.message); }
    finally {
      // A cancelled/preflight-rejected write keeps its preview and monitoring.
      // Once writing starts, discard even on failure: some cells may have changed.
      if (writing) { result = null; await stopMonitoring(); }
      writing = false; busy = false; updateButtons();
    }
  }

  function confirmWrite(message, pending) {
    return new Promise(resolve => {
      const dialog = $('action-dialog'), content = $('action-dialog-content');
      content.replaceChildren(element('p',message));
      const preview = [];
      for (const job of pending) {
        for (let r = 0; r < job.values.length && preview.length < 5; r++) {
          for (let c = 0; c < job.values[r].length && preview.length < 5; c++) {
            const existing = job.range.formulas[r][c];
            if (existing === '' || existing === null) continue;
            let column = '', n = job.ref.column + c + 1;
            while (n > 0) { n--; column = String.fromCharCode(65+n%26) + column; n = Math.floor(n/26); }
            const short = v => String(v ?? '').slice(0,160);
            preview.push([column + (job.ref.row+r+1), short(existing), short(job.values[r][c])]);
          }
        }
        if (preview.length >= 5) break;
      }
      if (preview.length) {
        content.appendChild(element('p','First occupied cells (up to 5); text is shortened to 160 characters:'));
        content.appendChild(table([['Cell','Existing value or formula','New value'], ...preview]));
      }

      const confirm = element('button','Replace cells'); content.appendChild(confirm);
      let answered = false;
      const finish = value => { if (answered) return; answered = true; dialog.removeEventListener('close',cancel); resolve(value); };
      const cancel = () => finish(false);
      dialog.addEventListener('close',cancel);
      confirm.onclick = () => { finish(true); dialog.close(); };
      dialog.showModal();
    });
  }
  Office.onReady(async () => {
    $('action-details').ontoggle = () => { if (!$('action-details').open) stopSelection(); };
    $('action-select').onchange = selectAction;
    $('action-run').onclick = run;
    $('action-write').onclick = () => write(false); $('action-updates').onclick = () => write(true);
    $('action-popup').onclick = showPopup; $('action-dialog-close').onclick = () => $('action-dialog').close();
    $('action-target').onclick = () => activateSelection({input: $('action-target'), single: true, output: true,
      set: ref => { outputTarget = ref; }});
    document.addEventListener('click', event => {
      if (selectionField && event.target !== selectionField.input) stopSelection();
    });
    try {
      await Excel.run(async context => {
        context.workbook.onSelectionChanged.add(captureSelection);
        await context.sync();
      });
    } catch (_) { status('Automatic range selection is unavailable in this Excel host.'); }
    await refresh();

  });
})();
