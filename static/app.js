'use strict';
const form = document.querySelector('#verify-form');
const input = document.querySelector('#announcement-url');
const button = document.querySelector('#verify-button');
const label = document.querySelector('#button-label');
const processing = document.querySelector('#processing');
const errorBox = document.querySelector('#error');
const result = document.querySelector('#result');

// Preselect the latest *published* announcement without claiming it is verified.
// Never overwrite a number/URL the operator has started typing.
let userEdited = false;
input.addEventListener('input', () => { userEdited = true; });
(async () => {
  try {
    const response = await fetch('/api/latest', { cache: 'no-store' });
    if (!response.ok) throw new Error('Latest unavailable');
    const data = await response.json();
    if (Number.isSafeInteger(data.number) && data.number >= 0 && !userEdited && !input.value.trim()) {
      input.value = `mf-${data.number}`;
    }
  } catch (_) {
    // Offline/GitHub unavailable: operator can enter a number or URL manually.
  } finally {
    input.placeholder = 'mf-N or official GitHub URL';
  }
})();

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  result.hidden = true;
  errorBox.hidden = true;
  processing.hidden = false;
  button.disabled = true;
  label.textContent = 'Checking';
  try {
    const response = await fetch('/api/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: input.value.trim() }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Verification failed.');
    }
    showResult(data);
  } catch (err) {
    errorBox.textContent = err instanceof Error ? err.message : 'Verification failed.';
    errorBox.hidden = false;
  } finally {
    processing.hidden = true;
    button.disabled = false;
    label.textContent = 'Verify';
  }
});

function showResult(data) {
  document.querySelector('#result-title').textContent = `MF #${data.number} · Verified`;
  document.querySelector('#result-meta').textContent = `${data.signers.length} authorized signatures · ${data.created}`;
  const severity = document.querySelector('#result-severity');
  severity.textContent = data.severity === 'UNCLASSIFIED' ? 'UNCLASSIFIED' : data.severity;
  severity.className = 'severity ' + (data.severity === 'ORANGE' ? 'orange' : data.severity === 'RED' ? 'red' : data.severity !== 'GREEN' ? 'unknown' : '');
  const signers = document.querySelector('#signers');
  signers.replaceChildren();
  for (const fingerprint of data.signers) {
    const item = document.createElement('li');
    const check = document.createElement('span');
    check.className = 'signer-check';
    check.textContent = '✓';
    const code = document.createElement('code');
    code.textContent = fingerprint;
    item.append(check, code);
    signers.append(item);
  }
  document.querySelector('#result-message').textContent = data.message;
  document.querySelector('#result-source').href = data.github_url;
  for (const disclosure of result.querySelectorAll('details')) disclosure.open = false;
  result.hidden = false;
}
