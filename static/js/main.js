function formatPLN(value) {
  try {
    return new Intl.NumberFormat('pl-PL', { style: 'currency', currency: 'PLN' }).format(value);
  } catch (e) {
    return value.toFixed(2) + " zł";
  }
}

function toast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('is-on');
  window.clearTimeout(window.__toastTimer);
  window.__toastTimer = window.setTimeout(() => t.classList.remove('is-on'), 1500);
}

async function postJSON(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data || {})
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.error || 'Request failed');
  return payload;
}

function updateMiniCart(count, total) {
  const elCount = document.getElementById('cartCount');
  const elTotal = document.getElementById('cartTotal');

  // mobile: badge only (total element may not exist by design)
  const elCountM = document.getElementById('cartCountMobile');
  const elTotalM = document.getElementById('cartTotalMobile');

  if (elCount) elCount.textContent = String(count);
  if (elTotal) elTotal.textContent = formatPLN(total);

  if (elCountM) elCountM.textContent = String(count);
  if (elTotalM) elTotalM.textContent = formatPLN(total);
}

/* Add to cart */
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-add-to-cart]');
  if (!btn) return;

  const id = btn.getAttribute('data-add-to-cart');
  if (!id) return;

  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = "Dodaję…";

  try {
    const r = await postJSON('/api/cart/add', { id, qty: 1 });
    updateMiniCart(r.count, r.total);
    toast("Dodano do koszyka");
  } catch (err) {
    toast("Błąd: " + (err.message || ''));
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
});

/* Qty change */
document.addEventListener('change', async (e) => {
  const input = e.target.closest('[data-qty]');
  if (!input) return;

  const id = input.getAttribute('data-qty');
  const qty = parseInt(input.value, 10);
  if (!id) return;

  try {
    const r = await postJSON('/api/cart/update', { id, qty });
    updateMiniCart(r.count, r.total);
    toast("Zaktualizowano koszyk");
    window.location.reload();
  } catch (err) {
    toast("Błąd: " + (err.message || ''));
  }
});

/* Remove */
document.addEventListener('click', async (e) => {
  const rm = e.target.closest('[data-remove]');
  if (!rm) return;

  const id = String(rm.getAttribute('data-remove') || '').trim();
  if (!id) return;

  try {
    const r = await postJSON('/api/cart/update', { id, qty: 0 });
    updateMiniCart(r.count, r.total);
    toast("Usunięto z koszyka");
    window.location.reload();
  } catch (err) {
    toast("Błąd: " + (err.message || ''));
  }
});

/* Clear cart */
document.addEventListener('click', async (e) => {
  const clear = e.target.closest('#clearCart');
  if (!clear) return;

  try {
    const r = await postJSON('/api/cart/clear', {});
    updateMiniCart(r.count, r.total);
    toast("Koszyk wyczyszczony");
    window.location.reload();
  } catch (err) {
    toast("Błąd: " + (err.message || ''));
  }
});

/* Mobile menu */
(function initMobileMenu(){
  const openBtn = document.getElementById('menuOpen');
  const closeBtn = document.getElementById('menuClose');
  const overlay = document.getElementById('mobileMenuOverlay');

  if (!openBtn || !closeBtn || !overlay) return;

  const open = () => {
    document.body.classList.add('menu-open');
    overlay.setAttribute('aria-hidden', 'false');
  };
  const close = () => {
    document.body.classList.remove('menu-open');
    overlay.setAttribute('aria-hidden', 'true');
  };

  openBtn.addEventListener('click', () => {
    if (document.body.classList.contains('menu-open')) close();
    else open();
  });

  closeBtn.addEventListener('click', close);

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });
})();

/* Sort select auto-submit */
(function initSortSelect(){
  const select = document.getElementById('sortSelect');
  const form = document.getElementById('sortForm');
  if (!select || !form) return;
  select.addEventListener('change', () => form.submit());
})();

/* Search suggest dropdown (desktop + mobile) */
(function initSearchSuggest(){
  function escapeHtml(str){
    return String(str || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function fetchSuggest(q) {
    const res = await fetch(`/api/search_suggest?q=${encodeURIComponent(q)}`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    return await res.json();
  }

  function bind(input, dd){
    if (!input || !dd) return;

    let t = null;
    let lastQ = "";

    // ===== FIX: keep scroll inside dropdown on mobile =====
    let touchStartY = 0;

    // stop wheel from bubbling to window
    dd.addEventListener('wheel', (e) => {
      // do not preventDefault here, just stop bubbling to window
      e.stopPropagation();
    }, { passive: true });

    // stop touch overscroll from scrolling the page
    dd.addEventListener('touchstart', (e) => {
      if (!e.touches || !e.touches.length) return;
      touchStartY = e.touches[0].clientY;
    }, { passive: true });

    dd.addEventListener('touchmove', (e) => {
      if (!e.touches || !e.touches.length) return;

      const y = e.touches[0].clientY;
      const dy = y - touchStartY;

      const atTop = dd.scrollTop <= 0;
      const atBottom = dd.scrollTop + dd.clientHeight >= dd.scrollHeight - 1;

      // If user tries to scroll beyond bounds -> prevent page scroll
      if ((atTop && dy > 0) || (atBottom && dy < 0)) {
        e.preventDefault();
      }

      // and always stop bubbling so window scroll handler doesn't fire
      e.stopPropagation();
    }, { passive: false });

    const close = () => {
      dd.hidden = true;
      dd.innerHTML = "";
    };

    const open = () => {
      dd.hidden = false;
    };

    const render = (data) => {
      const prods = (data && data.products) || [];
      const cats = (data && data.categories) || [];

      function group(label, items) {
        if (!items || !items.length) return "";
        return `
          <div class="edit-suggest__group">
            <div class="edit-suggest__label">${label}</div>
            <div class="edit-suggest__items">${items.join("")}</div>
          </div>`;
      }

      const catItems = cats.map((c) => {
        const url = `/shop?category=${encodeURIComponent(c.slug)}`;
        return `
          <a class="edit-suggest__item" href="${url}">
            <span class="edit-suggest__main">${escapeHtml(c.name)}</span>
            <span class="edit-suggest__meta">${escapeHtml(String(c.count || 0))} produktów</span>
          </a>`;
      });

      const prodItems = prods.map((p) => {
        const url = `/product/${encodeURIComponent(p.id)}`;
        const meta = [p.category, p.price].filter(Boolean).join(" · ");
        return `
          <a class="edit-suggest__item" href="${url}">
            <span class="edit-suggest__main">${escapeHtml(p.title)}</span>
            <span class="edit-suggest__meta">${escapeHtml(meta)}</span>
          </a>`;
      });

      let html = "";
      html += group("Kategorie:", catItems);
      html += group("Produkty:", prodItems);

      if (!html.trim()) html = `<div class="dd-empty">Brak podpowiedzi</div>`;

      dd.innerHTML = html;
      open();
    };

    input.addEventListener('input', () => {
      const q = (input.value || "").trim();
      lastQ = q;

      if (t) clearTimeout(t);
      if (q.length < 1) { close(); return; }

      t = setTimeout(async () => {
        try {
          const data = await fetchSuggest(q);
          if (lastQ !== q) return;
          render(data);
        } catch (e) {
          close();
        }
      }, 180);
    });

    input.addEventListener('focus', () => {
      const q = (input.value || "").trim();
      if (q.length >= 1 && dd.innerHTML.trim()) open();
    });

    document.addEventListener('click', (e) => {
      if (e.target === input) return;
      if (dd.contains(e.target)) return;
      close();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === "Escape") close();
    });
  }

  bind(document.getElementById('searchInput'), document.getElementById('searchDD'));
  bind(document.getElementById('mobileSearchInput'), document.getElementById('mobileSearchDD'));
})();

/* Mobile header: hide search on scroll + set correct main offset under fixed header */
(function initMobileHeaderFixed(){
  const header = document.getElementById('siteHeader');
  if (!header) return;

  const mq = window.matchMedia('(max-width: 720px)');

  const setOffset = () => {
    if (!mq.matches) {
      document.documentElement.style.setProperty('--mobile-header-offset', '0px');
      return;
    }
    const h = Math.round(header.getBoundingClientRect().height);
    document.documentElement.style.setProperty('--mobile-header-offset', h + 'px');
  };

  const onScroll = () => {
    if (!mq.matches) {
      document.body.classList.remove('m-scrolled');
      return;
    }
    if (window.scrollY > 20) document.body.classList.add('m-scrolled');
    else document.body.classList.remove('m-scrolled');
    setOffset();
  };

  setOffset();
  onScroll();

  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', () => { setOffset(); onScroll(); });

  if (mq.addEventListener) {
    mq.addEventListener('change', () => { setOffset(); onScroll(); });
  }
})();

/* Footer legal modals */
(function initLegalModals(){
  const overlay = document.getElementById('legalOverlay');
  if (!overlay) return;

  const modals = {
    regulamin: document.getElementById('legal-regulamin'),
    privacy: document.getElementById('legal-privacy'),
    cookies: document.getElementById('legal-cookies'),
    delivery: document.getElementById('legal-delivery'),
    returns: document.getElementById('legal-returns'),
    account: document.getElementById('legal-account'),
  };

  let openedKey = null;

  const closeAll = () => {
    Object.values(modals).forEach(m => { if (m) m.hidden = true; });
    overlay.classList.remove('is-on');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('legal-open');
    openedKey = null;
  };

  const open = (key) => {
    const modal = modals[key];
    if (!modal) return;
    closeAll();
    modal.hidden = false;
    overlay.classList.add('is-on');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('legal-open');
    openedKey = key;

    const btn = modal.querySelector('[data-legal-close]');
    if (btn) btn.focus();
  };

  document.addEventListener('click', (e) => {
    const openEl = e.target.closest('[data-legal-open]');
    if (openEl) {
      e.preventDefault();
      const key = openEl.getAttribute('data-legal-open');
      open(key);
      return;
    }

    const closeEl = e.target.closest('[data-legal-close]');
    if (closeEl) {
      e.preventDefault();
      closeAll();
      return;
    }

    if (e.target === overlay) {
      closeAll();
      return;
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && openedKey) closeAll();
  });
})();
