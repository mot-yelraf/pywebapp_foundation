/* Shared API and independently saved settings panes. */
window.PWAF = (() => {
  let csrf;
  async function api(path, options = {}) {
    const method = options.method || 'GET';
    const headers = {...options.headers};
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      if (!csrf) {
        const response = await fetch('/api/csrf');
        if (!response.ok) throw new Error('Cannot connect to the application.');
        csrf = (await response.json()).csrf_token;
      }
      headers['X-CSRF-Token'] = csrf;
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(path, {...options, headers});
    const body = await response.json();
    if (!response.ok) {
      if (body.error?.code === 'csrf_failed') csrf = null;
      const error = new Error(body.error?.message || 'The request failed.');
      error.status = response.status;
      throw error;
    }
    return body;
  }
  function status(element, message, error = false) {
    element.textContent = message;
    element.classList.toggle('error', error);
  }
  return {api, status};
})();

document.addEventListener('DOMContentLoaded', () => {
  const dialog = document.querySelector('#settings-dialog');
  const opener = document.querySelector('#open-settings');
  const loadStatus = document.querySelector('#settings-load-status');
  const forms = [...dialog.querySelectorAll('form')];
  let savedTheme = document.documentElement.dataset.theme;
  let generation = 0;
  let saving = false;
  const tabs = [...dialog.querySelectorAll('[role=tab]')];
  function selectTab(tab) {
    for (const item of tabs) {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
    }
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(tab));
    tab.addEventListener('keydown', event => {
      let next;
      if (['ArrowDown', 'ArrowRight'].includes(event.key)) next = (index + 1) % tabs.length;
      if (['ArrowUp', 'ArrowLeft'].includes(event.key)) next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) {event.preventDefault(); selectTab(tabs[next]); tabs[next].focus();}
    });
  });
  opener.addEventListener('click', async () => {
    const current = ++generation;
    savedTheme = document.documentElement.dataset.theme;
    forms.forEach(form => {form.reset(); PWAF.status(form.querySelector('.form-status'), '');
      [...form.elements].forEach(input => input.disabled = true);});
    selectTab(tabs[0]);
    PWAF.status(loadStatus, 'Loading settings…');
    dialog.showModal();
    try {
      const settings = await PWAF.api('/api/settings');
      if (current !== generation || !dialog.open) return;
      savedTheme = settings.theme;
      for (const form of forms) {
        for (const input of form.elements) {
          if (input.name) input.value = settings[input.name];
          input.disabled = false;
        }
      }
      PWAF.status(loadStatus, '');
    } catch (error) {if (current === generation) PWAF.status(loadStatus, error.message, true);}
  });
  function close() {if (!saving) dialog.close();}
  document.querySelector('#close-settings').addEventListener('click', close);
  dialog.addEventListener('cancel', event => {if (saving) event.preventDefault();});
  dialog.addEventListener('close', () => {
    generation++; document.documentElement.dataset.theme = savedTheme; opener.focus();
  });
  dialog.querySelector('[name=theme]')?.addEventListener('change', event => {
    document.documentElement.dataset.theme = event.target.value;
  });
  forms.forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault();
    if (saving) return;
    const changes = {};
    for (const input of form.elements) if (input.name) {
      changes[input.name] = input.type === 'number' ? Number(input.value) : input.value;
    }
    const feedback = form.querySelector('.form-status');
    PWAF.status(feedback, 'Saving…');
    saving = true;
    document.querySelector('#close-settings').disabled = true;
    forms.forEach(item => [...item.elements].forEach(input => input.disabled = true));
    try {
      const settings = await PWAF.api(`/api/settings/panes/${form.dataset.settingsPane}`, {
        method: 'PATCH', body: JSON.stringify(changes)
      });
      if ('theme' in changes) savedTheme = settings.theme;
      document.querySelectorAll('[data-app-name]').forEach(item => item.textContent = settings.app_name);
      PWAF.status(feedback, 'Saved.');
      document.dispatchEvent(new CustomEvent('settings-saved', {detail: settings}));
    } catch (error) {PWAF.status(feedback, error.message, true);}
    finally {
      saving = false; document.querySelector('#close-settings').disabled = false;
      forms.forEach(item => [...item.elements].forEach(input => input.disabled = false));
    }
  }));
  const toggle = document.querySelector('#menu-toggle');
  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(expanded));
    document.querySelector('#main-navigation').classList.toggle('open', expanded);
  });
});

// Optional shared dialogs use data-open-dialog/data-close-dialog with a local ID.
document.addEventListener('click', event => {
  const open = event.target.closest('[data-open-dialog]');
  const close = event.target.closest('[data-close-dialog]');
  if (open) {
    const target = document.getElementById(open.dataset.openDialog);
    target.addEventListener('close', () => open.focus(), {once:true});
    target.showModal();
  }
  if (close) document.getElementById(close.dataset.closeDialog).close();
});
