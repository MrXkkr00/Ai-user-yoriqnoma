"""JavaScript run inside the studied page (read-only, except replacing other people's data)."""

# Visible interactive elements in reading order: role, accessible name, document box.
COLLECT_ELEMENTS = r"""
(maxH) => {
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, summary, ' +
    '[role=button], [role=tab], [role=menuitem], [role=link], [role=checkbox], ' +
    '[role=radio], [role=switch], [onclick]';
  const out = [];
  const seen = new Set();
  const text = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const labelFor = (el) => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return text(l);
    }
    const wrap = el.closest('label');
    if (wrap) return text(wrap);
    return '';
  };
  const roleOf = (el) => {
    const r = el.getAttribute('role');
    if (r) return r;
    const t = el.tagName.toLowerCase();
    if (t === 'a') return 'link';
    if (t === 'button' || t === 'summary') return 'button';
    if (t === 'select') return 'combobox';
    if (t === 'textarea') return 'textbox';
    if (t === 'input') {
      const ty = (el.type || 'text').toLowerCase();
      if (['submit', 'button', 'reset'].includes(ty)) return 'button';
      if (ty === 'checkbox') return 'checkbox';
      if (ty === 'radio') return 'radio';
      if (ty === 'number') return 'spinbutton';
      return 'textbox';
    }
    return 'generic';
  };
  const kindOf = (role, el) => {
    if (role === 'link') return 'link';
    if (role === 'tab') return 'tab';
    if (role === 'menuitem') return 'menu';
    if (role === 'combobox') return 'select';
    if (['textbox', 'checkbox', 'radio', 'spinbutton', 'switch'].includes(role)) return 'input';
    if (role === 'button') return 'button';
    return 'other';
  };
  const cssPath = (el) => {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && parts.length < 4; n = n.parentElement) {
      let p = n.tagName.toLowerCase();
      if (n.getAttribute('name')) { p += `[name="${n.getAttribute('name')}"]`; parts.unshift(p); break; }
      const sib = n.parentElement ? [...n.parentElement.children].filter(c => c.tagName === n.tagName) : [];
      if (sib.length > 1) p += `:nth-of-type(${sib.indexOf(n) + 1})`;
      parts.unshift(p);
    }
    return parts.join(' > ');
  };
  for (const el of document.querySelectorAll(sel)) {
    if (seen.has(el)) continue;
    seen.add(el);
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none') continue;
    const y = r.top + window.scrollY;
    if (y > maxH) continue;
    const role = roleOf(el);
    const label = (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA') ? labelFor(el) : '';
    let name = label || el.getAttribute('aria-label') || text(el) || el.getAttribute('title') ||
      el.getAttribute('placeholder') || el.getAttribute('alt') || el.value || '';
    name = String(name).replace(/\s+/g, ' ').trim().slice(0, 120);
    out.push({
      role, name, kind: kindOf(role, el), label,
      x: r.left + window.scrollX, y, w: r.width, h: r.height,
      enabled: !el.disabled, testid: el.getAttribute('data-testid') || '',
      css: cssPath(el), href: el.getAttribute('href') || '', tag: el.tagName.toLowerCase(),
    });
  }
  out.sort((a, b) => (Math.round(a.y / 8) - Math.round(b.y / 8)) || (a.x - b.x));
  return out;
}
"""

# Text nodes, form values and images with their zone (TZ FR-E10). Nodes get an index
# so Python can send back replacements; nothing leaves the page except this list.
PRIVACY_SCAN = r"""
({nameHeaders, editorialIsUgc}) => {
  window.__yq = window.__yq || {nodes: [], inputs: []};
  const S = window.__yq;
  S.nodes = []; S.inputs = [];
  const hasCls = (n, re) => {
    const c = (typeof n.className === 'string' ? n.className : (n.className && n.className.baseVal) || '');
    return re.test(c + ' ' + (n.id || ''));
  };
  const UC = /(^|[\s_-])(comment|comments|review|reviews|reply|replies|izoh|izohlar|sharh|sharhlar|otzyv|отзыв)([\s_-]|$)/i;
  const ADS = /(^|[\s_-])(ad|ads|advert|advertising|banner|reklama|sponsor)([\s_-]|$)/i;
  const zoneOf = (el) => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const it = (n.getAttribute('itemtype') || '').toLowerCase();
      if (/schema\.org\/(comment|review|usercomments|answer|question)/.test(it) || hasCls(n, UC)) return 'user_content';
    }
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const t = n.tagName.toLowerCase();
      const role = n.getAttribute('role');
      if (['header', 'footer', 'nav'].includes(t) || ['banner', 'contentinfo', 'navigation'].includes(role)) return 'org';
    }
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const t = n.tagName.toLowerCase();
      const it = (n.getAttribute('itemtype') || '').toLowerCase();
      if (t === 'article' || /schema\.org\/(article|newsarticle|blogposting|reportagenewsarticle)/.test(it) ||
          n.getAttribute('rel') === 'author' || n.getAttribute('itemprop') === 'author' ||
          (t === 'a' && /\/author\//.test(n.getAttribute('href') || '')) || hasCls(n, ADS)) {
        return editorialIsUgc ? 'user_content' : 'editorial';
      }
    }
    if (/\/(contact|contacts|about|aloqa|biz-haqimizda|kontakty|o-nas)(\/|$)/i.test(location.pathname)) return 'org';
    return 'other';
  };
  const blockOf = (el) => el.closest('tr, li, [itemscope], article, .card, .review, figure, dl') || null;
  const blocks = new Map();
  const blockId = (el) => {
    const b = blockOf(el);
    if (!b) return -1;
    if (!blocks.has(b)) blocks.set(b, blocks.size);
    return blocks.get(b);
  };
  const structural = (el) => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const ip = n.getAttribute('itemprop');
      if (ip === 'author' || n.getAttribute('rel') === 'author') return 'name';
      if (ip === 'name' && n.closest('[itemtype*="Person"]')) return 'name';
      if (n.tagName === 'A' && /\/author\//.test(n.getAttribute('href') || '')) return 'name';
      if (ip === 'reviewBody' || ip === 'text' || ip === 'commentText') return 'body';
      if (n.tagName === 'TD') {
        const table = n.closest('table');
        const idx = [...n.parentElement.children].indexOf(n);
        const head = table && table.querySelector('thead tr, tr');
        const th = head ? head.children[idx] : null;
        const label = th ? (th.innerText || '').trim().toLowerCase() : '';
        if (label && nameHeaders.includes(label)) return 'name';
      }
      if (n.classList && (n.classList.contains('avatar'))) return 'avatar';
    }
    return null;
  };
  const visible = (el) => {
    const st = getComputedStyle(el);
    return st.display !== 'none' && st.visibility !== 'hidden';
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  for (let t = walker.nextNode(); t; t = walker.nextNode()) {
    const value = t.nodeValue;
    if (!value || !value.trim()) continue;
    const el = t.parentElement;
    if (!el || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(el.tagName) || !visible(el)) continue;
    const r = el.getBoundingClientRect();
    S.nodes.push(t);
    nodes.push({
      i: S.nodes.length - 1, text: value, zone: zoneOf(el), structural: structural(el),
      block: blockId(el), tag: el.tagName.toLowerCase(),
      interactive: !!el.closest('button, [role=button], label, select, option, [role=tab]'),
      x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height,
    });
  }
  const inputs = [];
  for (const el of document.querySelectorAll('input:not([type=hidden]):not([type=password]), textarea')) {
    if (!el.value || !visible(el)) continue;
    const r = el.getBoundingClientRect();
    S.inputs.push(el);
    inputs.push({i: S.inputs.length - 1, text: el.value, zone: zoneOf(el), block: blockId(el),
                 x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height});
  }
  const images = [];
  for (const el of document.querySelectorAll('img, canvas, video, [style*="background-image"]')) {
    const r = el.getBoundingClientRect();
    if (r.width < 48 || r.height < 16 || !visible(el)) continue;
    const avatar = /avatar|userpic|profile-photo|profile_pic/i.test(
      (el.className || '') + ' ' + (el.getAttribute('alt') || '') + ' ' + (el.getAttribute('src') || ''));
    images.push({zone: zoneOf(el), avatar, tag: el.tagName.toLowerCase(),
                 x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height});
  }
  const placeholders = [...document.querySelectorAll('[placeholder]')]
    .map(el => el.getAttribute('placeholder')).filter(Boolean);
  return {nodes, inputs, images, placeholders, path: location.pathname};
}
"""

APPLY_REPLACEMENTS = r"""
({nodes, inputs, neutralAvatar}) => {
  const S = window.__yq || {nodes: [], inputs: []};
  for (const r of nodes) { const t = S.nodes[r.i]; if (t) t.nodeValue = r.text; }
  for (const r of inputs) {
    const el = S.inputs[r.i];
    if (el) { el.value = r.text; el.setAttribute('value', r.text); }
  }
  if (neutralAvatar) {
    for (const img of document.querySelectorAll('img')) {
      if (/avatar|userpic|profile/i.test((img.className || '') + ' ' + (img.alt || '') + ' ' + (img.src || ''))) {
        img.src = neutralAvatar; img.srcset = '';
      }
    }
  }
  return true;
}
"""

# Links that lead to paths the role must not see (admin, other roles): boxes to blur.
FORBIDDEN_LINKS = r"""
(patterns) => {
  const res = patterns.map(p => new RegExp(p));
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    let path;
    try { path = new URL(a.getAttribute('href'), location.href).pathname; } catch (e) { continue; }
    if (!res.some(re => re.test(path))) continue;
    const r = a.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    out.push({x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height, path,
              text: (a.innerText || '').trim().slice(0, 60)});
  }
  return out;
}
"""

# Candidates for the state graph: tabs, expanders, menus, pagination (never submits).
SAFE_CANDIDATES = r"""
() => {
  const sel = '[role=tab], [aria-expanded], [aria-haspopup], summary, [data-bs-toggle], ' +
    '[data-toggle], .accordion-button, a[rel=next], [aria-label*="next" i], [aria-label*="keyingi" i]';
  const out = [];
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (el.getAttribute('aria-selected') === 'true') continue;
    if (el.closest('form') && el.type === 'submit') continue;
    const name = (el.getAttribute('aria-label') || el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    out.push({name, role: el.getAttribute('role') || el.tagName.toLowerCase(),
              x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height});
  }
  return out;
}
"""

ROW_LINKS = r"""
() => {
  const out = [];
  for (const a of document.querySelectorAll('table a[href], li a[href], .card a[href]')) {
    const href = a.getAttribute('href') || '';
    if (!href.startsWith('/') || href.startsWith('/api/')) continue;
    out.push({href, name: (a.innerText || '').trim().slice(0, 60)});
  }
  return out;
}
"""

PAGE_TEXT = "() => document.body ? document.body.innerText : ''"
