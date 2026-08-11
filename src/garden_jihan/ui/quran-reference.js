(() => {
  const sessionToken = document.querySelector('meta[name="goj-token"]')?.content || '';
  const statusBox = document.getElementById('quranReferenceStatus');
  const fileInput = document.getElementById('quranReferenceFile');
  const messageBox = document.getElementById('quranReferenceMessage');
  const group = document.querySelector('.quran-reference-group');

  if (!statusBox || !fileInput || !messageBox || !group) return;

  function renderStatus(data) {
    const available = Boolean(data?.available) && Number(data?.verses) === 6236;
    statusBox.classList.toggle('ready', available);
    statusBox.classList.toggle('missing', !available);
    statusBox.classList.remove('checking');
    const source = data?.source?.name || 'verified local reference';
    statusBox.innerHTML = available
      ? `<span></span><div><b>Reference ready</b><small>6,236 ayahs • ${escapeText(source)} • stored locally</small></div>`
      : '<span></span><div><b>Reference not installed</b><small>Surah/Ayah identification remains fail-safe until a complete reference is installed.</small></div>';
  }

  async function refreshStatus() {
    try {
      const response = await fetch('/api/quran/reference', {cache: 'no-store'});
      if (!response.ok) throw new Error('Could not read Quran reference status');
      renderStatus(await response.json());
    } catch (error) {
      statusBox.classList.remove('checking', 'ready');
      statusBox.classList.add('missing');
      statusBox.innerHTML = `<span></span><div><b>Status unavailable</b><small>${escapeText(error.message)}</small></div>`;
    }
  }

  fileInput.addEventListener('change', async () => {
    if (!fileInput.files.length) return;
    messageBox.classList.remove('hidden', 'error');
    messageBox.textContent = 'Validating the complete Quran reference locally…';
    const form = new FormData();
    form.append('file', fileInput.files[0]);
    try {
      const response = await fetch('/api/quran/reference', {
        method: 'POST',
        headers: {'X-GOJ-Token': sessionToken},
        body: form,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Reference installation failed');
      if (!data.available || Number(data.verses) !== 6236) throw new Error('Reference validation did not complete');
      messageBox.innerHTML = '<strong>Ready.</strong> Complete local Qur’an reference installed.';
      renderStatus(data);
    } catch (error) {
      messageBox.classList.add('error');
      messageBox.textContent = error.message;
    } finally {
      fileInput.value = '';
    }
  });

  document.querySelectorAll('input[name="mode"]').forEach(input => {
    input.addEventListener('change', () => {
      group.classList.toggle('active-reference', input.value === 'quran' && input.checked);
    });
  });

  function escapeText(value) {
    return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  }

  refreshStatus();
})();
