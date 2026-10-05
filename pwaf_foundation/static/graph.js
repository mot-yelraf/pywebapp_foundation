/**
 * Render application-supplied time series in the Graphum dialog.
 *
 * Validate bounded datasets, preserve metric selection, and draw responsive SVG
 * plots with gaps for missing observations. No domain routes or chart dependencies.
 */
(() => {
  const dialog = document.getElementById('graph-dialog');
  if (!dialog) return;
  const metrics = document.getElementById('graph-metrics');
  const plots = document.getElementById('graph-plots');
  const status = document.getElementById('graph-status');
  let series = [], selected = new Set(), hours = Number(dialog.querySelector('[data-graph-hours][aria-pressed=true]')?.dataset.graphHours || 24);
  const colors = ['#91e3c5', '#87b4ff', '#f6c779', '#d8a6fa'];
  function node(tag, text, parent) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    parent?.append(item);
    return item;
  }
  function svgNode(tag, attributes, parent) {
    const item = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, String(value));
    parent.append(item);
    return item;
  }
  function render() {
    // Capture ancestors: desktop scrolls the stage; mobile scrolls the workspace.
    const scrollPositions = [];
    for (let element = plots; element; element = element.parentElement) {
      scrollPositions.push([element, element.scrollLeft, element.scrollTop]);
    }
    // Build off-DOM so measuring a partially rebuilt plot cannot collapse the scroller.
    const replacement = document.createDocumentFragment();
    const plotWidth = Math.max(280, Math.min(900, plots.clientWidth - 34));
    document.getElementById('graph-count').textContent = `${selected.size} of 4`;
    document.getElementById('graph-range-title').textContent = hours < 1 ? `Last ${Math.round(hours * 60)} ${Math.round(hours * 60) === 1 ? 'minute' : 'minutes'}` : `Last ${hours} ${hours === 1 ? 'hour' : 'hours'}`;
    const end = Date.now(), start = end - hours * 3600000;
    const chosen = series.filter(item => selected.has(item.id));
    if (!chosen.length) {
      node('p', series.length ? 'Select a metric to graph it.' : 'No graph data available yet.', replacement)
        .className = 'graph-empty';
    }
    chosen.forEach((item, index) => {
      const section = node('section', undefined, replacement);
      section.className = 'graph-plot';
      node('h4', item.label + (item.unit ? ` (${item.unit})` : ''), section);
      const points = item.points.filter(point => point.x >= start && point.x <= end);
      const valid = points.filter(point => point.y !== null);
      if (!valid.length) {node('p', 'No observations in this time range.', section); return;}
      const values = valid.map(point => point.y);
      const low = Math.min(...values), high = Math.max(...values);
      const padding = high === low ? Math.max(Math.abs(low) * .05, 1) : (high - low) * .1;
      const min = low - padding, max = high + padding;
      const width = plotWidth;
      const svg = svgNode('svg', {viewBox: `0 0 ${width} 220`, role: 'img',
        'aria-label': `${item.label}: ${valid.length} observations; minimum ${low}, maximum ${high} ${item.unit}.`}, section);
      const x = time => 65 + (time - start) / (end - start) * (width - 80);
      const y = value => 180 - (value - min) / (max - min) * 160;
      for (let line = 0; line < 3; line++) {
        const value = min + (max - min) * line / 2;
        svgNode('line', {x1: 65, x2: width - 15, y1: y(value), y2: y(value), stroke: '#36434d'}, svg);
        svgNode('text', {x: 58, y: y(value) + 4, fill: '#a7b3bd', 'text-anchor': 'end',
          'font-size': 12}, svg).textContent = Number(value.toPrecision(4)).toString();
      }
      let path = '', move = true;
      for (const point of points) {
        if (point.y === null) {move = true; continue;}
        path += `${move ? 'M' : 'L'}${x(point.x)},${y(point.y)} `;
        move = false;
      }
      svgNode('path', {d: path, fill: 'none', stroke: colors[index], 'stroke-width': 2.5}, svg);
      for (const point of valid) svgNode('circle', {cx: x(point.x), cy: y(point.y), r: 2.5,
        fill: colors[index]}, svg);
      for (const time of [start, end]) svgNode('text', {x: x(time), y: 210,
        fill: '#a7b3bd', 'text-anchor': time === start ? 'start' : 'end', 'font-size': 12}, svg)
        .textContent = width < 550 ? new Date(time).toLocaleTimeString() : new Date(time).toLocaleString();
      node('p', `${valid.length} observations · Min ${low} · Max ${high} · Latest ${valid.at(-1).y} ${item.unit}`, section);
    });
    plots.replaceChildren(replacement);
    for (const [element, left, top] of scrollPositions) {
      element.scrollLeft = left;
      element.scrollTop = top;
    }
  }
  /**
   * Replace chart data, retaining valid selections and sorting points by time.
   * @param {Array<{id: string, label: string, unit?: string,
   *   points: Array<{x: number, y: (number|null)}>}>} input Up to 100 unique metrics;
   *   each accepts up to 5,000 points with epoch-millisecond x and null for gaps.
   * @returns {void}
   * @throws {TypeError} If a series or point violates the dataset contract.
   */
  function setSeries(input) {
    if (!Array.isArray(input) || input.length > 100) throw new TypeError('Expected up to 100 series.');
    const ids = new Set();
    const next = input.map(item => {
      if (!item || typeof item.id !== 'string' || !item.id || ids.has(item.id) ||
          typeof item.label !== 'string' || (item.unit !== undefined && typeof item.unit !== 'string') ||
          !Array.isArray(item.points) || item.points.length > 5000) throw new TypeError('Invalid graph series.');
      ids.add(item.id);
      const points = item.points.map(point => {
        if (!point || !Number.isFinite(point.x) || Math.abs(point.x) > 8.64e15 ||
            (point.y !== null && !Number.isFinite(point.y))) throw new TypeError('Invalid graph point.');
        return {x: point.x, y: point.y};
      }).sort((a, b) => a.x - b.x);
      return {id: item.id, label: item.label, unit: item.unit || '', points};
    });
    const sameMetrics = JSON.stringify(series.map(s => [s.id, s.label, s.unit])) === JSON.stringify(next.map(s => [s.id, s.label, s.unit]));
    series = next;
    selected = new Set([...selected].filter(id => ids.has(id)));
    if (!selected.size && series.length) selected.add(series[0].id);
    if (!sameMetrics) {
    metrics.replaceChildren();
    for (const item of series) {
      const label = node('label', undefined, metrics);
      const checkbox = node('input', undefined, label);
      checkbox.type = 'checkbox'; checkbox.checked = selected.has(item.id);
      node('span', item.label, label);
      checkbox.addEventListener('change', () => {
        if (checkbox.checked && selected.size >= 4) {
          checkbox.checked = false; status.textContent = 'Select at most four metrics.'; return;
        }
        if (checkbox.checked) selected.add(item.id); else selected.delete(item.id);
        status.textContent = 'Select up to four metrics.';
        render();
      });
    }
    }
    status.textContent = series.length ? 'Select up to four metrics.' : 'No metrics available.';
    render();
  }
  /** Open the modal chart dialog and redraw the current series. */
  function open() {if (!dialog.open) dialog.showModal(); render();}
  document.getElementById('open-graph').addEventListener('click', open);
  document.getElementById('close-graph').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {if (event.target === dialog) {
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right ||
        event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  }});
  dialog.querySelectorAll('[data-graph-hours]').forEach(button => button.addEventListener('click', () => {
    hours = Number(button.dataset.graphHours);
    dialog.querySelectorAll('[data-graph-hours]').forEach(item =>
      item.setAttribute('aria-pressed', String(item === button)));
    render();
  }));
  let resizeFrame;
  window.addEventListener('resize', () => {
    if (!dialog.open) return;
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(render);
  });
  window.PWAF.graph = {
    setSeries,
    open,
    /** Close the chart dialog without discarding its data or selection. */
    close: () => dialog.close(),
    /** Redraw current data for the selected metrics and time window. */
    refresh: render,
  };
})();
