(() => {
  const sessionToken = document.querySelector('meta[name="goj-token"]')?.content || '';
  const statusBox = document.getElementById('quranReferenceStatus');
  const fileInput = document.getElementById('quranReferenceFile');
  const messageBox = document.getElementById('quranReferenceMessage');
  const group = document.querySelector('.quran-reference-group');

  if (!statusBox || !fileInput || !messageBox || !group) return;

  function renderStatus(data) {
    const available = Boolean(data?.available) && Boolean(data?.verified) && Number(data?.verses) === 6236;
    const invalid = Boolean(data?.installed) && !available;
    statusBox.classList.toggle('ready', available);
    statusBox.classList.toggle('invalid', invalid);
    statusBox.classList.toggle('missing', !available && !invalid);
    statusBox.classList.remove('checking');
    const source = data?.source?.name || 'reviewed local reference';
    const checksum = String(data?.integrity?.canonical_sha256 || '').slice(0, 12);
    if (available) {
      statusBox.innerHTML = `<span></span><div><b>Reference verified</b><small>6,236 ayahs • ${escapeText(source)} v${escapeText(data?.source?.version||'1.1')} • SHA-256 ${escapeText(checksum)}…</small></div>`;
    } else if (invalid) {
      statusBox.innerHTML = '<span></span><div><b>Reference blocked</b><small>The installed file failed integrity validation. Reinstall the exact reviewed Tanzil profile.</small></div>';
    } else {
      statusBox.innerHTML = '<span></span><div><b>Reference not installed</b><small>Surah/Ayah identification remains disabled until the reviewed file passes its checksum.</small></div>';
    }
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
      if (!data.available || !data.verified || Number(data.verses) !== 6236) throw new Error('Reference integrity validation did not complete');
      messageBox.innerHTML = '<strong>Verified.</strong> The reviewed Tanzil 1.1 reference is installed locally.';
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
