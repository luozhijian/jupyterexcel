// Local diagnostics: no authentication, network request, or Python kernel.
// Capture this bundle's configuration, rather than another subsequently loaded version.
(() => {
  const config = { ...globalThis.JupyterExcelConfig };
  CustomFunctions.associate('MANIFESTURL', () => config.manifestUrl || '');
  CustomFunctions.associate('SERVERURL', () => config.apiBase || '');
  CustomFunctions.associate('ADDINVERSION', () => config.addinVersion || '');
  CustomFunctions.associate('ASSETVERSION', () => config.assetVersion || '');
})();

// Workbook-runtime-local schedules. Descriptors are data, never executable code.
(() => {
  const PREFIX = 'JupyterExcel.RtTimer.v1:';
  const DAY = 86400000;
  const schedules = new Map();
  const error = (message, code = 'invalidValue') => new CustomFunctions.Error(CustomFunctions.ErrorCode[code], message);
  function finite(value, name) {
    if (typeof value !== 'number' || !Number.isFinite(value)) throw error(name + ' must be a finite number.');
    return value;
  }
  function interval(value) {
    finite(value, 'Frequency');
    if (value < 0.001 || value * 1000 > Number.MAX_SAFE_INTEGER) throw error('Frequency must be at least 0.001 seconds and within the supported range.');
    return value * 1000;
  }
  // Excel's default 1900 date system, interpreted in the computer's local time.
  function fromSerial(value) {
    finite(value, 'Start time');
    if (value < 61 || value >= 2958466) throw error('Start time must be an Excel date from March 1900 through December 9999.');
    const d = new Date(Math.round((value - 25569) * DAY));
    return new Date(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds(), d.getUTCMilliseconds()).getTime();
  }
  function toSerial(now) {
    const d = new Date(now);
    return (now - d.getTimezoneOffset() * 60000) / DAY + 25569;
  }
  CustomFunctions.associate('RTTIMER', (start, frequency, duration) => {
    try {
      const startMs = fromSerial(start), period = interval(frequency);
      finite(duration, 'Duration');
      const end = startMs + duration * 60000;
      if (duration <= 0 || !Number.isSafeInteger(Math.round(end)) || end <= startMs) throw error('Duration must be positive and within the supported range.');
      return PREFIX + JSON.stringify({start: startMs, period, end});
    } catch (e) { return e; }
  });
  function parse(value, duration) {
    if (typeof value === 'number') {
      const start = Date.now(), period = interval(value);
      let end = null;
      if (duration != null) {
        finite(duration, 'Countdown duration');
        end = start + duration * 1000;
        if (duration <= 0 || !Number.isSafeInteger(Math.round(end))) throw error('Countdown duration must be positive and within the supported range.');
      }
      return {start, period, end};
    }
    if (typeof value !== 'string' || !value.startsWith(PREFIX)) throw error('Use refresh seconds or an RtTimer result.');
    let s;
    try { s = JSON.parse(value.slice(PREFIX.length)); } catch (_) { throw error('Invalid RtTimer descriptor.'); }
    if (!s || typeof s !== 'object') throw error('Invalid RtTimer descriptor.');
    finite(s.start, 'Start'); finite(s.end, 'End'); finite(s.period, 'Frequency'); interval(s.period / 1000);
    if (!Number.isSafeInteger(Math.round(s.start)) || !Number.isSafeInteger(Math.round(s.end)) || s.end <= s.start) throw error('Invalid RtTimer dates.');
    if (duration != null) throw error('Do not supply countdown duration with RtTimer.');
    return {start: s.start, period: s.period, end: s.end};
  }
  function stream(value, invocation, make, duration, countdown = false) {
    let s, generate;
    try {
      s = parse(value, duration);
      if (countdown && s.end === null) throw error('Supply duration_in_seconds or use RtTimer.');
      generate = make(s);
    } catch (e) { invocation.setResult(e); return; }
    const key = JSON.stringify(s);
    let group = schedules.get(key);
    if (!group) {
      group = {s, subscribers: new Set(), timer: null};
      schedules.set(key, group);
    }
    let active = true, hasValue = false, count = 0;
    const subscriber = (now) => {
      if (!active) return;
      if (now < s.start) {
        invocation.setResult(error('Timer has not started.', 'notAvailable'));
        return;
      }
      // At expiration retain the last value; countdown alone publishes zero.
      if (s.end !== null && now >= s.end && hasValue && !countdown) return;
      try { invocation.setResult(generate(Math.min(now, s.end === null ? now : s.end), count++)); hasValue = true; }
      catch (e) { invocation.setResult(e); invocation.onCanceled(); }
    };
    invocation.onCanceled = () => {
      active = false;
      group.subscribers.delete(subscriber);
      if (!group.subscribers.size) {
        if (group.timer !== null) clearTimeout(group.timer);
        if (schedules.get(key) === group) schedules.delete(key);
      }
    };
    group.subscribers.add(subscriber);
    function arm() {
      const now = Date.now();
      if (!group.subscribers.size || (s.end !== null && now >= s.end)) {
        if (schedules.get(key) === group) schedules.delete(key);
        group.subscribers.clear();
        return;
      }
      const next = now < s.start ? s.start : s.start + (Math.floor((now - s.start) / s.period) + 1) * s.period;
      const due = s.end === null ? next : Math.min(next, s.end);
      group.timer = setTimeout(() => {
        group.timer = null;
        const current = Date.now();
        // Long waits are chunked to avoid the platform's 32-bit timer overflow.
        if (current >= due) for (const publish of [...group.subscribers]) publish(current);
        arm();
      }, Math.max(1, Math.min(2147483647, due - now)));
    }
    subscriber(Date.now());
    if (group.timer === null) arm();
  }
  CustomFunctions.associate('RTNOW', (timer, invocation) => stream(timer, invocation, () => now => toSerial(now)));
  CustomFunctions.associate('RTRAND', (timer, invocation) => stream(timer, invocation, () => () => Math.random()));
  CustomFunctions.associate('RTCOUNT', (timer, invocation) => stream(timer, invocation, () => (_now, count) => count));
  CustomFunctions.associate('RTELAPSED', (timer, invocation) => stream(timer, invocation, s => now => (now - s.start) / 1000));
  CustomFunctions.associate('RTCOUNTDOWN', (timer, duration, invocation) => stream(timer, invocation, s => now => Math.max(0, (s.end - now) / 1000), duration, true));
  function bounds(min, max, whole) {
    finite(min, 'Minimum'); finite(max, 'Maximum');
    if (whole) { min = Math.ceil(min); max = Math.floor(max); }
    if (min > max || !Number.isFinite(max - min) || (whole && (!Number.isSafeInteger(min) || !Number.isSafeInteger(max) || max - min >= Number.MAX_SAFE_INTEGER))) throw error('Invalid random bounds.', 'invalidNumber');
    return () => whole ? min + Math.floor(Math.random() * (max - min + 1)) : min + Math.random() * (max - min);
  }
  CustomFunctions.associate('RTRANDBETWEEN', (timer, bottom, top, invocation) => stream(timer, invocation, () => bounds(bottom, top, true)));
  CustomFunctions.associate('RTRANDARRAY', (timer, rows, columns, min, max, whole, invocation) => stream(timer, invocation, () => {
    rows = rows == null ? 1 : rows; columns = columns == null ? 1 : columns;
    min = min == null ? 0 : min; max = max == null ? 1 : max; whole = whole == null ? false : whole;
    if (!Number.isInteger(rows) || !Number.isInteger(columns) || rows < 1 || columns < 1 || rows > 1048576 || columns > 16384 || rows * columns > 100000) throw error('Use positive integer dimensions with at most 100,000 elements.', 'invalidNumber');
    if (typeof whole !== 'boolean') throw error('whole_number must be TRUE or FALSE.');
    const draw = bounds(min, max, whole);
    return () => Array.from({length: rows}, () => Array.from({length: columns}, draw));
  }));
})();
