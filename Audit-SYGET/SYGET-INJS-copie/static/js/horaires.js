/**
 * Gestion dynamique des horaires de séances.
 * Masque/affiche les créneaux matin/après-midi selon la case à cocher.
 */
document.addEventListener("DOMContentLoaded", function () {
  function toggleHoraires(checkboxId, fieldsSelector) {
    const checkbox = document.getElementById(checkboxId);
    if (!checkbox) return;
    const fields = document.querySelectorAll(fieldsSelector);
    function update() {
      fields.forEach(f => {
        const row = f.closest(".row, .col-md-6, .mb-3") || f.parentElement;
        if (row) row.style.display = checkbox.checked ? "" : "none";
      });
    }
    checkbox.addEventListener("change", update);
    update();
  }

  toggleHoraires("id_matin_actif", ".matin-fields input");
  toggleHoraires("id_soir_actif", ".soir-fields input");
});
