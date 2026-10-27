'use strict';

(function () {
  function initChangelistFilters() {
    var changelist = document.getElementById('changelist');
    var toggle = document.getElementById('sygep-filter-toggle');
    var closeBtn = document.getElementById('sygep-filter-close');
    var backdrop = document.getElementById('sygep-filter-backdrop');
    var panel = document.getElementById('changelist-filter');

    if (!changelist || !toggle || !panel) {
      return;
    }

    function setOpen(open) {
      changelist.classList.toggle('sygep-filters-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (backdrop) {
        backdrop.hidden = !open;
      }
      document.body.classList.toggle('sygep-filter-panel-open', open);
    }

    toggle.addEventListener('click', function () {
      setOpen(!changelist.classList.contains('sygep-filters-open'));
    });

    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        setOpen(false);
      });
    }

    if (backdrop) {
      backdrop.addEventListener('click', function () {
        setOpen(false);
      });
    }

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initChangelistFilters);
  } else {
    initChangelistFilters();
  }
})();
