(() => {
  const statusBox = document.getElementById('quranReferenceStatus');
  const group = document.querySelector('.quran-reference-group');

  if (!statusBox || !group) return;

  function renderStatus(data) {
    const available = Boolean(data?.available) && Boolean(data?.verified) && Number(data?.verses) === 6236;
    const invalid = Boolean(data?.installed) && !available;
    statusBox.classList.toggle('ready', available);
    statusBox.classList.toggle('invalid', invalid);
    statusBox.classList.toggle('missing', !available && !invalid);
    statusBox.classList.remove('checking');
    if (available) {
      statusBox.innerHTML = '<span></span><div><b>Trusted Qur’an guide ready</b><small>All 6,236 Ayahs are included and verified. Careful Surah and Ayah review is available.</small></div>';
    } else if (invalid) {
      statusBox.innerHTML = '<span></span><div><b>Qur’an guide needs repair</b><small>Surah and Ayah will stay hidden. Reinstall Garden of Jihan to restore the reviewed guide.</small></div>';
    } else {
      statusBox.innerHTML = '<span></span><div><b>Qur’an guide needs repair</b><small>Surah and Ayah will stay hidden. Reinstall Garden of Jihan to restore the reviewed guide.</small></div>';
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

  document.querySelectorAll('input[name="mode"]').forEach(input => {
    input.addEventListener('change', () => {
      group.classList.toggle('active-reference', input.value === 'quran' && input.checked);
    });
  });

  refreshStatus();
})();
