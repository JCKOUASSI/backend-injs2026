/**
 * Wizard multi-étapes pour la création guidée d'une formation.
 * Gère l'affichage pas-à-pas des sections du formulaire.
 */
document.addEventListener("DOMContentLoaded", function () {
  const steps = document.querySelectorAll(".wizard-step");
  const nextBtns = document.querySelectorAll(".wizard-next");
  const prevBtns = document.querySelectorAll(".wizard-prev");
  const indicators = document.querySelectorAll(".wizard-indicator");

  if (!steps.length) return;

  let current = 0;

  function showStep(n) {
    steps.forEach((s, i) => s.classList.toggle("d-none", i !== n));
    indicators.forEach((ind, i) => {
      ind.classList.toggle("active", i === n);
      ind.classList.toggle("text-primary", i === n);
      ind.classList.toggle("text-muted", i !== n);
    });
    current = n;
  }

  nextBtns.forEach(btn => btn.addEventListener("click", () => {
    if (current < steps.length - 1) showStep(current + 1);
  }));

  prevBtns.forEach(btn => btn.addEventListener("click", () => {
    if (current > 0) showStep(current - 1);
  }));

  showStep(0);
});
