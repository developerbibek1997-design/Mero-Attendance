/**
 * Reusable print-configuration panel: paper size, orientation, margins,
 * fit-to-width, and per-report column visibility. One instance per printable
 * page — see templates/partials/print_settings_panel.html for the markup it
 * attaches to.
 *
 * A report opts in by:
 *   - tagging optional table columns with data-print-col="<key>"
 *     (and optionally data-print-col-label="Human label")
 *   - tagging its widest table/container with data-print-fit so "fit to
 *     width" can shrink it to the chosen paper size at print time
 */
(function () {
  const MARGIN_MM = { normal: 15, narrow: 6, none: 0 };
  const PAGE_MM = {
    A4: { portrait: [210, 297], landscape: [297, 210] },
    Letter: { portrait: [216, 279], landscape: [279, 216] },
    Legal: { portrait: [216, 356], landscape: [356, 216] },
  };
  const MM_TO_PX = 96 / 25.4;

  function debounce(fn, wait) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), wait);
    };
  }

  function init(opts) {
    const mount = document.getElementById(opts.mountId);
    if (!mount) return;
    const reportKey = opts.reportKey;
    const saveUrl = mount.dataset.saveUrl;
    const csrfToken = mount.dataset.csrf;
    const defaults = { paper: 'A4', orientation: 'portrait', margin: 'normal', fit_to_width: true, hidden_columns: [] };
    let state = Object.assign({}, defaults, opts.initial || {});
    if (!opts.initial || Object.keys(opts.initial).length === 0) {
      try {
        const cached = localStorage.getItem('printSettings:' + reportKey);
        if (cached) state = Object.assign({}, defaults, JSON.parse(cached));
      } catch (e) { /* ignore corrupt cache */ }
    }

    const columns = Array.from(document.querySelectorAll('[data-print-col]')).map((el) => ({
      key: el.getAttribute('data-print-col'),
      label: el.getAttribute('data-print-col-label') || el.textContent.trim() || el.getAttribute('data-print-col'),
    })).filter((c, i, arr) => arr.findIndex((x) => x.key === c.key) === i);

    const persist = debounce((s) => {
      try { localStorage.setItem('printSettings:' + reportKey, JSON.stringify(s)); } catch (e) { /* ignore */ }
      if (!saveUrl) return;
      fetch(saveUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ settings: s }),
      }).catch(() => { /* best-effort; localStorage already has it */ });
    }, 500);

    buildPanel(mount, state, columns);
    applyStyles(state);
    wireControls(mount, state, columns, () => {
      applyStyles(state);
      persist(state);
    });
  }

  function buildPanel(mount, state, columns) {
    const panel = mount.querySelector('.ps-panel');
    if (!panel) return;
    let colHtml = '';
    if (columns.length) {
      colHtml = '<div class="ps-field"><label class="ps-label">Columns</label><div class="ps-cols">' +
        columns.map((c) => (
          '<label class="ps-col-check"><input type="checkbox" data-role="col" data-key="' + c.key + '"' +
          (state.hidden_columns.indexOf(c.key) === -1 ? ' checked' : '') + '> ' + c.label + '</label>'
        )).join('') + '</div></div>';
    }
    panel.innerHTML =
      '<div class="ps-field"><label class="ps-label">Paper</label>' +
      '<select data-role="paper" class="form-select form-select-sm">' +
      ['A4', 'Letter', 'Legal'].map((p) => '<option value="' + p + '"' + (state.paper === p ? ' selected' : '') + '>' + p + '</option>').join('') +
      '</select></div>' +
      '<div class="ps-field"><label class="ps-label">Orientation</label>' +
      '<select data-role="orientation" class="form-select form-select-sm">' +
      ['portrait', 'landscape'].map((o) => '<option value="' + o + '"' + (state.orientation === o ? ' selected' : '') + '>' + o.charAt(0).toUpperCase() + o.slice(1) + '</option>').join('') +
      '</select></div>' +
      '<div class="ps-field"><label class="ps-label">Margins</label>' +
      '<select data-role="margin" class="form-select form-select-sm">' +
      ['normal', 'narrow', 'none'].map((m) => '<option value="' + m + '"' + (state.margin === m ? ' selected' : '') + '>' + m.charAt(0).toUpperCase() + m.slice(1) + '</option>').join('') +
      '</select></div>' +
      '<div class="ps-field"><label class="ps-col-check"><input type="checkbox" data-role="fit"' + (state.fit_to_width ? ' checked' : '') + '> Fit to page width</label></div>' +
      colHtml;
  }

  function wireControls(mount, state, columns, onChange) {
    mount.querySelector('[data-role="paper"]').addEventListener('change', (e) => { state.paper = e.target.value; onChange(); });
    mount.querySelector('[data-role="orientation"]').addEventListener('change', (e) => { state.orientation = e.target.value; onChange(); });
    mount.querySelector('[data-role="margin"]').addEventListener('change', (e) => { state.margin = e.target.value; onChange(); });
    mount.querySelector('[data-role="fit"]').addEventListener('change', (e) => { state.fit_to_width = e.target.checked; onChange(); });
    mount.querySelectorAll('[data-role="col"]').forEach((cb) => {
      cb.addEventListener('change', (e) => {
        const key = e.target.getAttribute('data-key');
        const idx = state.hidden_columns.indexOf(key);
        if (e.target.checked && idx !== -1) state.hidden_columns.splice(idx, 1);
        if (!e.target.checked && idx === -1) state.hidden_columns.push(key);
        onChange();
      });
    });
    const toggleBtn = mount.querySelector('.ps-toggle');
    const panel = mount.querySelector('.ps-panel');
    if (toggleBtn && panel) {
      toggleBtn.addEventListener('click', () => panel.classList.toggle('ps-open'));
    }
  }

  function applyStyles(state) {
    let styleTag = document.getElementById('print-settings-dynamic');
    if (!styleTag) {
      styleTag = document.createElement('style');
      styleTag.id = 'print-settings-dynamic';
      document.head.appendChild(styleTag);
    }
    const marginMm = MARGIN_MM[state.margin] ?? 15;
    const hiddenRules = (state.hidden_columns || [])
      .map((k) => '[data-print-col="' + cssEscape(k) + '"] { display: none !important; }')
      .join('\n');

    let fitRule = '';
    if (state.fit_to_width) {
      const dims = (PAGE_MM[state.paper] || PAGE_MM.A4)[state.orientation] || PAGE_MM.A4.portrait;
      const printablePx = (dims[0] - 2 * marginMm) * MM_TO_PX;
      fitRule = '[data-print-fit] { --ps-page-px: ' + printablePx.toFixed(0) + '; }';
    }

    styleTag.textContent =
      '@page { size: ' + state.paper + ' ' + state.orientation + '; margin: ' + marginMm + 'mm; }\n' +
      '@media print {\n' + hiddenRules + '\n' + fitRule + '\n}';

    if (state.fit_to_width) {
      requestAnimationFrame(() => scaleFitElements());
    } else {
      document.querySelectorAll('[data-print-fit]').forEach((el) => { el.style.zoom = ''; });
    }
  }

  function scaleFitElements() {
    document.querySelectorAll('[data-print-fit]').forEach((el) => {
      const pagePx = parseFloat(getComputedStyle(el).getPropertyValue('--ps-page-px'));
      if (!pagePx || !el.scrollWidth) return;
      const ratio = pagePx / el.scrollWidth;
      el.style.zoom = ratio < 1 ? ratio.toFixed(3) : '';
    });
  }

  function cssEscape(s) {
    return String(s).replace(/["\\]/g, '\\$&');
  }

  window.addEventListener('beforeprint', scaleFitElements);
  window.PrintSettings = { init: init };
})();
