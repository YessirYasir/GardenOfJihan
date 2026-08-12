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
    if (available) {
      statusBox.innerHTML = '<span></span><div><b>Trusted Qur’an guide ready</b><small>All 6,236 Ayahs were accepted. Careful Surah and Ayah review is available.</small></div>';
    } else if (invalid) {
      statusBox.innerHTML = '<span></span><div><b>Qur’an guide not accepted</b><small>This is not the complete reviewed text. Choose the trusted Tanzil text again.</small></div>';
    } else {
      statusBox.innerHTML = '<span></span><div><b>Qur’an guide needed</b><small>Surah and Ayah stay hidden until the complete reviewed text is accepted.</small></div>';
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
      statusBox.innerHTML = '<span></span><div><b>Qur’an guide unavailable</b><small>Surah and Ayah will remain hidden. Try again in a moment.</small></div>';
    }
  }

  fileInput.addEventListener('change', async () => {
    if (!fileInput.files.length) return;
    messageBox.classList.remove('hidden', 'error');
    messageBox.textContent = 'Checking the complete reviewed Qur’an text…';
    const form = new FormData();
    form.append('file', fileInput.files[0]);
    try {
      const response = await fetch('/api/quran/reference', {
        method: 'POST',
        headers: {'X-GOJ-Token': sessionToken},
        body: form,
      });
      const data = await response.json();
      if (!response.ok) throw new Error('The text was not accepted. Choose the complete Tanzil Simple text with Ayah numbers.');
      if (!data.available || !data.verified || Number(data.verses) !== 6236) throw new Error('The text was not accepted. Surah and Ayah will stay hidden.');
      messageBox.innerHTML = '<strong>Ready.</strong> The complete reviewed Qur’an guide was accepted.';
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

  refreshStatus();
})();
