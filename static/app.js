(() => {
  const list = document.querySelector('#component-list');
  const addButton = document.querySelector('#add-component');

  function makeRow() {
    const row = document.createElement('div');
    row.className = 'component-row';
    row.innerHTML = `
      <input name="components" maxlength="100" placeholder="Fx Tamagoyaki">
      <button type="button" class="icon-btn" data-remove-component aria-label="Fjern komponent">×</button>`;
    return row;
  }

  if (list && addButton) {
    addButton.addEventListener('click', () => {
      const row = makeRow();
      list.appendChild(row);
      row.querySelector('input').focus();
    });

    list.addEventListener('click', (event) => {
      const remove = event.target.closest('[data-remove-component]');
      if (!remove) return;
      const rows = list.querySelectorAll('.component-row');
      if (rows.length === 1) {
        rows[0].querySelector('input').value = '';
        rows[0].querySelector('input').focus();
        return;
      }
      remove.closest('.component-row').remove();
    });
  }

  const imageInput = document.querySelector('#image');
  const preview = document.querySelector('#image-preview');
  if (imageInput && preview) {
    imageInput.addEventListener('change', () => {
      const file = imageInput.files?.[0];
      if (!file) {
        preview.hidden = true;
        preview.removeAttribute('src');
        return;
      }
      preview.src = URL.createObjectURL(file);
      preview.hidden = false;
    });
  }
})();
