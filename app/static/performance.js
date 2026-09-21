/* Ephemeral job controls and durable result history; untrusted output uses textContent. */
document.addEventListener('DOMContentLoaded', () => {
  const $ = selector => document.querySelector(selector);
  let activeJob = sessionStorage.getItem('pwaf-job');
  let offset = 0;
  let historySequence = 0;
  let pendingSubmission;
  let polling = false;
  const limit = 10;
  async function history() {
    const sequence = ++historySequence;
    PWAF.status($('#history-status'), 'Loading results…');
    try {
      const data = await PWAF.api(`/api/results?offset=${offset}&limit=${limit}`);
      if (sequence !== historySequence) return;
      $('#saved-count').textContent = data.total;
      const rows = data.items.map(item => {
        const row = document.createElement('tr');
        const values = [new Date(item.recorded_at).toLocaleString(), item.iterations.toLocaleString(),
          `${item.elapsed_ms.toLocaleString()} ms`, item.checksum.slice(0, 12)];
        values.forEach((value, index) => {
          const cell = document.createElement('td'); cell.textContent = value;
          if (index === 3) {cell.className = 'checksum'; cell.title = item.checksum;}
          row.append(cell);
        });
        return row;
      });
      $('#history-rows').replaceChildren(...rows);
      if (offset === 0 && data.items.length) {
        $('#latest-duration').textContent = `${data.items[0].elapsed_ms.toLocaleString()} ms`;
        $('#latest-iterations').textContent = data.items[0].iterations.toLocaleString();
      }
      $('#previous-page').disabled = offset === 0;
      $('#next-page').disabled = offset + limit >= data.total;
      $('#page-label').textContent = `Page ${Math.floor(offset / limit) + 1}`;
      PWAF.status($('#history-status'), data.total ? '' : 'No saved results yet. Run your first benchmark.');
    } catch (error) {if (sequence === historySequence) PWAF.status($('#history-status'), error.message, true);}
  }
  function controls(busy) {$('#run-button').disabled = busy; $('#cancel-job').disabled = !busy;}
  function forget() {activeJob = null; sessionStorage.removeItem('pwaf-job'); controls(false);}
  async function poll() {
    if (polling || !activeJob) return;
    polling = true;
    let retry = false;
    try {
      const job = await PWAF.api(`/api/jobs/${activeJob}`);
      $('#job-heading').textContent = {queued:'Waiting for a slot.', running:'Benchmark in progress.',
        succeeded:'Run complete.', failed:'Run failed.', cancelled:'Run cancelled.'}[job.status];
      $('#job-progress').value = job.progress;
      if (job.status === 'running' && job.progress === 0) $('#job-progress').removeAttribute('value');
      PWAF.status($('#job-status'), job.error?.message || `Status: ${job.status}`, job.status === 'failed');
      retry = ['queued','running'].includes(job.status);
      if (!retry) {
        if (job.result) {$('#job-result').hidden = false; $('#job-result').textContent = `Checksum: ${job.result.checksum}`;}
        forget(); await history();
      }
    } catch (error) {
      if (error.status === 404) {
        $('#job-heading').textContent = 'Run status unavailable.';
        PWAF.status($('#job-status'), 'This run expired or the server restarted. Check saved results below.');
        forget(); await history();
      } else {PWAF.status($('#job-status'), 'Connection interrupted. Retrying status…', true); retry = true;}
    } finally {polling = false; if (retry && activeJob) setTimeout(poll, 500);}
  }
  $('#run-form').addEventListener('submit', async event => {
    event.preventDefault();
    controls(true); $('#cancel-job').disabled = true;
    $('#job-result').hidden = true;
    const body = JSON.stringify({operation:'performance', parameters:{iterations:Number($('#iterations').value)}});
    if (!pendingSubmission || pendingSubmission.body !== body) pendingSubmission = {body, key:Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')};
    PWAF.status($('#job-status'), 'Submitting…');
    try {
      const job = await PWAF.api('/api/jobs', {method:'POST', headers:{'Idempotency-Key':pendingSubmission.key}, body});
      pendingSubmission = null; activeJob = job.id; sessionStorage.setItem('pwaf-job', job.id);
      controls(true); poll();
    } catch (error) {PWAF.status($('#job-status'), error.message, true); controls(false);}
  });
  $('#cancel-job').addEventListener('click', async () => {
    $('#cancel-job').disabled = true;
    try {await PWAF.api(`/api/jobs/${activeJob}/cancel`, {method:'POST'}); PWAF.status($('#job-status'), 'Cancelling…');}
    catch (error) {PWAF.status($('#job-status'), error.message, true);}
  });
  $('#refresh-history').addEventListener('click', history);
  $('#previous-page').addEventListener('click', () => {offset = Math.max(0, offset - limit); history();});
  $('#next-page').addEventListener('click', () => {offset += limit; history();});
  document.addEventListener('settings-saved', event => {$('#iterations').value = event.detail.default_iterations;});
  history();
  if (activeJob) {controls(true); poll();}
});
