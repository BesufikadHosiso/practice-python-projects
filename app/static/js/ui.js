/**
 * Tiny UI kit: escaping, icons, formatting, toasts, modals, skeletons.
 * No framework — everything is plain DOM so there is no build step.
 */

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

/** Escape untrusted text before it ever touches innerHTML. */
export function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/[&<>"']/g, (char) => ESCAPES[char]);
}

export function icon(name, extraClass = '') {
  return `<svg class="icon ${extraClass}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

/** Turn an HTML string into a DocumentFragment / single node. */
export function html(markup) {
  const template = document.createElement('template');
  template.innerHTML = markup.trim();
  return template.content.children.length === 1 ? template.content.firstElementChild : template.content;
}

/** `on(el, 'click', '.btn', handler)` — event delegation for dynamic lists. */
export function on(root, type, selector, handler, options) {
  root.addEventListener(
    type,
    (event) => {
      const target = event.target.closest(selector);
      if (target && root.contains(target)) handler(event, target);
    },
    options,
  );
}

/* ------------------------------------------------------------------ format */
const UNITS = [
  ['year', 31536000], ['month', 2592000], ['week', 604800],
  ['day', 86400], ['hour', 3600], ['minute', 60],
];

export function parseTime(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "3h ago", "in 2d", "just now" — used everywhere in the post list. */
export function relTime(value) {
  const date = parseTime(value);
  if (!date) return '—';
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return 'just now';
  for (const [unit, size] of UNITS) {
    if (abs >= size) {
      const amount = Math.round(seconds / size);
      const formatted = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(amount, unit);
      return formatted;
    }
  }
  return 'just now';
}

export function fullTime(value) {
  const date = parseTime(value);
  if (!date) return '—';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium', timeStyle: 'short',
  }).format(date);
}

export function dayLabel(value) {
  const date = parseTime(value);
  if (!date) return '';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date);
}

export function compactNumber(value) {
  const num = Number(value) || 0;
  if (Math.abs(num) < 1000) return String(num);
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(num);
}

export function plural(count, singular, pluralForm) {
  return `${count} ${count === 1 ? singular : pluralForm || `${singular}s`}`;
}

/** Linkify URLs inside already-escaped text. */
export function linkify(escaped) {
  return escaped.replace(
    /(https?:\/\/[^\s<]+)/g,
    (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer nofollow">${url.length > 52 ? `${url.slice(0, 52)}…` : url}</a>`,
  );
}

const AVATAR_COLORS = 7;
export function avatarColor(seed) {
  const text = String(seed || '');
  let sum = 0;
  for (let i = 0; i < text.length; i += 1) sum += text.charCodeAt(i);
  return sum % AVATAR_COLORS;
}

export function avatar(seed, size = '') {
  const label = String(seed || '?').slice(0, 2).toUpperCase();
  return `<span class="avatar ${size}" data-c="${avatarColor(seed)}" title="${esc(seed)}">${esc(label)}</span>`;
}

/* ------------------------------------------------------------------ toasts */
const TOAST_ICON = { success: 'check-circle', error: 'alert', info: 'info', warn: 'alert' };

export function toast({ title, text = '', kind = 'info', action = null, timeout = 4600 }) {
  const host = document.getElementById('toasts');
  if (!host) return () => {};
  const node = html(`
    <div class="toast toast--${kind}" style="animation-duration:${timeout}ms">
      <span class="toast__icon">${icon(TOAST_ICON[kind] || 'info', 'icon-sm')}</span>
      <div class="toast__body">
        <div class="toast__title">${esc(title)}</div>
        ${text ? `<div class="toast__text">${esc(text)}</div>` : ''}
        <div class="toast__actions"></div>
      </div>
      <button class="btn btn--ghost btn--sm btn--icon" data-close aria-label="Dismiss">${icon('x', 'icon-sm')}</button>
      <span class="toast__progress" style="animation-duration:${timeout}ms"></span>
    </div>`);

  const actions = node.querySelector('.toast__actions');
  let timer;
  const close = () => {
    if (!node.isConnected) return;
    clearTimeout(timer);
    node.classList.add('is-out');
    setTimeout(() => node.remove(), 200);
  };
  if (action) {
    const button = html(`<button class="btn btn--sm btn--soft">${esc(action.label)}</button>`);
    button.addEventListener('click', () => { action.onClick(); close(); });
    actions.append(button);
  } else {
    actions.remove();
  }
  node.querySelector('[data-close]').addEventListener('click', close);
  host.append(node);
  timer = setTimeout(close, timeout);
  return close;
}

/* ------------------------------------------------------------------ modal */
let openOverlays = [];

export function closeTopOverlay() {
  const last = openOverlays[openOverlays.length - 1];
  if (last) last();
}

function pushOverlay(closeFn) {
  openOverlays.push(closeFn);
}

function popOverlay(closeFn) {
  openOverlays = openOverlays.filter((fn) => fn !== closeFn);
}

/**
 * Render a modal. `body`/`footer` are HTML strings; returns {root, close}
 * where `root` is the `.modal` element for wiring up events.
 */
export function openModal({ title, subtitle = '', body = '', footer = '', size = '', onClose = null }) {
  const root = document.getElementById('modal-root') || document.body;
  const overlay = html(`
    <div class="overlay">
      <div class="modal ${size ? `modal--${size}` : ''}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <div class="modal__head">
          <div style="flex:1;min-width:0">
            <h3>${esc(title)}</h3>
            ${subtitle ? `<p>${esc(subtitle)}</p>` : ''}
          </div>
          <button class="btn btn--ghost btn--sm btn--icon" data-close aria-label="Close">${icon('x', 'icon-sm')}</button>
        </div>
        <div class="modal__body">${body}</div>
        ${footer ? `<div class="modal__foot">${footer}</div>` : ''}
      </div>
    </div>`);

  const close = () => {
    if (!overlay.isConnected) return;
    overlay.remove();
    popOverlay(close);
    document.removeEventListener('keydown', keyHandler);
    if (onClose) onClose();
  };
  const keyHandler = (event) => { if (event.key === 'Escape') close(); };

  overlay.addEventListener('mousedown', (event) => { if (event.target === overlay) close(); });
  overlay.querySelector('[data-close]').addEventListener('click', close);
  document.addEventListener('keydown', keyHandler);
  root.append(overlay);
  pushOverlay(close);

  const focusable = overlay.querySelector('input, textarea, select, button:not([data-close])');
  if (focusable) focusable.focus();
  return { root: overlay.querySelector('.modal'), overlay, close };
}

/** Promise-based confirmation dialog. */
export function confirmDialog({
  title, message = '', confirmLabel = 'Confirm', cancelLabel = 'Cancel', danger = false, details = '',
}) {
  return new Promise((resolve) => {
    const { root, close } = openModal({
      title,
      body: `<p style="font-size:13.5px;color:var(--text-2);line-height:1.65">${esc(message)}</p>
             ${details ? `<div class="callout callout--${danger ? 'danger' : 'warn'}" style="margin-top:14px">
               ${icon(danger ? 'alert' : 'info', 'icon-sm')}<div class="callout__body">${details}</div></div>` : ''}`,
      footer: `<button class="btn" data-cancel>${esc(cancelLabel)}</button>
               <button class="btn ${danger ? 'btn--danger' : 'btn--primary'}" data-confirm>${esc(confirmLabel)}</button>`,
      size: 'sm',
      onClose: () => resolve(false),
    });
    root.querySelector('[data-cancel]').addEventListener('click', () => { resolve(false); close(); });
    root.querySelector('[data-confirm]').addEventListener('click', () => {
      openOverlays = openOverlays.filter((fn) => fn !== close);
      root.closest('.overlay').remove();
      resolve(true);
    });
  });
}

/** Slide-in side panel (post detail view). */
export function openDrawer({ title, subtitle = '', body = '', footer = '' }) {
  const overlay = html(`
    <div class="overlay" style="place-items:stretch;justify-content:flex-end;padding:0">
      <div class="drawer" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <div class="drawer__head">
          <div style="flex:1;min-width:0">
            <h3>${esc(title)}</h3>
            ${subtitle ? `<p class="small muted truncate">${esc(subtitle)}</p>` : ''}
          </div>
          <button class="btn btn--ghost btn--sm btn--icon" data-close aria-label="Close">${icon('x', 'icon-sm')}</button>
        </div>
        <div class="drawer__body">${body}</div>
        ${footer ? `<div class="drawer__foot">${footer}</div>` : ''}
      </div>
    </div>`);
  const close = () => {
    if (!overlay.isConnected) return;
    overlay.remove();
    popOverlay(close);
    document.removeEventListener('keydown', keyHandler);
  };
  const keyHandler = (event) => { if (event.key === 'Escape') close(); };
  overlay.addEventListener('mousedown', (event) => { if (event.target === overlay) close(); });
  overlay.querySelector('[data-close]').addEventListener('click', close);
  document.addEventListener('keydown', keyHandler);
  (document.getElementById('modal-root') || document.body).append(overlay);
  pushOverlay(close);
  return { root: overlay.querySelector('.drawer'), close };
}

/* -------------------------------------------------------------- skeletons */
export function skeletonPosts(count = 5) {
  return `<div class="postlist">${Array.from({ length: count }, () => `
    <div class="sk-post">
      <div class="skeleton sk-circle"></div>
      <div style="flex:1">
        <div class="skeleton sk-line" style="width:38%"></div>
        <div class="skeleton sk-line" style="width:92%"></div>
        <div class="skeleton sk-line" style="width:74%"></div>
        <div class="skeleton sk-line" style="width:44%;margin-bottom:0"></div>
      </div>
    </div>`).join('')}</div>`;
}

export function skeletonStats(count = 4) {
  return `<div class="grid grid--stats">${Array.from({ length: count }, () => '<div class="skeleton sk-stat"></div>').join('')}</div>`;
}

export function skeletonCards(count = 6, className = 'grid--groups') {
  return `<div class="grid ${className}">${Array.from({ length: count }, () => `
    <div class="sk-card">
      <div class="row" style="gap:12px;margin-bottom:14px">
        <div class="skeleton sk-circle" style="width:42px;height:42px;border-radius:12px"></div>
        <div style="flex:1">
          <div class="skeleton sk-line" style="width:70%"></div>
          <div class="skeleton sk-line" style="width:44%;margin-bottom:0"></div>
        </div>
      </div>
      <div class="skeleton sk-line" style="width:100%"></div>
      <div class="skeleton sk-line" style="width:86%;margin-bottom:0"></div>
    </div>`).join('')}</div>`;
}

export function skeletonTable(rows = 6) {
  return `<div class="card"><div style="padding:6px">
    ${Array.from({ length: rows }, () => `<div class="skeleton sk-line" style="height:38px;margin-bottom:6px"></div>`).join('')}
  </div></div>`;
}

/* ------------------------------------------------------------- empty state */
export function emptyState({
  iconName = 'inbox', title, message, actions = '', success = false,
}) {
  return `
    <div class="empty ${success ? 'is-success' : ''}">
      <div class="empty__icon">${icon(iconName)}</div>
      <h3>${esc(title)}</h3>
      <p>${esc(message)}</p>
      ${actions ? `<div class="empty__actions">${actions}</div>` : ''}
    </div>`;
}

export function errorState(message, retryLabel = 'Try again') {
  return `
    <div class="empty">
      <div class="empty__icon" style="background:var(--danger-soft);color:var(--danger)">${icon('alert')}</div>
      <h3>Something went wrong</h3>
      <p>${esc(message)}</p>
      <div class="empty__actions"><button class="btn btn--primary" data-retry>${esc(retryLabel)}</button></div>
    </div>`;
}

/* ------------------------------------------------------------------ pager */
export function pager({ page, perPage, total, onEachSide = 1 }) {
  const pages = Math.max(1, Math.ceil(total / perPage));
  if (pages <= 1) return '';
  const window_ = new Set([1, pages, page]);
  for (let offset = 1; offset <= onEachSide; offset += 1) {
    window_.add(page - offset);
    window_.add(page + offset);
  }
  const visible = [...window_].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);

  let buttons = `<button data-page="${page - 1}" ${page === 1 ? 'disabled' : ''} aria-label="Previous page">‹</button>`;
  let previous = 0;
  for (const number of visible) {
    if (number - previous > 1) buttons += `<span class="muted small" style="padding:0 3px">…</span>`;
    buttons += `<button data-page="${number}" aria-current="${number === page}">${number}</button>`;
    previous = number;
  }
  buttons += `<button data-page="${page + 1}" ${page === pages ? 'disabled' : ''} aria-label="Next page">›</button>`;
  return `<div class="pager" data-pager>${buttons}</div>`;
}

/* --------------------------------------------------------- misc rendering */
export const POST_TYPES = {
  text: { icon: 'text', label: 'Text' },
  photo: { icon: 'image', label: 'Photo' },
  link: { icon: 'link', label: 'Link' },
  video: { icon: 'video', label: 'Video' },
  poll: { icon: 'poll', label: 'Poll' },
  live: { icon: 'live', label: 'Live' },
  event: { icon: 'calendar', label: 'Event' },
};

export const STATE_LABEL = {
  published: 'Published', pending: 'Pending', flagged: 'Flagged',
  scheduled: 'Scheduled', trashed: 'In trash',
};

export function stateBadge(state) {
  return `<span class="badge badge--${state}"><span class="dot"></span>${STATE_LABEL[state] || state}</span>`;
}

export function typeBadge(type) {
  const meta = POST_TYPES[type] || POST_TYPES.text;
  return `<span class="post__type">${icon(meta.icon, 'icon-sm')}${meta.label}</span>`;
}

/** Debounce helper used by the search inputs. */
export function debounce(fn, wait = 260) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

export function setError(field, message) {
  const wrapper = field.closest('.field');
  if (!wrapper) return;
  wrapper.classList.toggle('has-error', Boolean(message));
  const slot = wrapper.querySelector('.err');
  if (slot) slot.textContent = message || '';
}

/** Parse a native form into a plain object, honouring checkboxes. */
export function formData(form) {
  const out = {};
  new FormData(form).forEach((value, key) => {
    if (key in out) {
      out[key] = [].concat(out[key], value);
      return;
    }
    out[key] = value;
  });
  form.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    out[input.name] = input.checked;
  });
  return out;
}
