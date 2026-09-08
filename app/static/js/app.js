/**
 * Entry point: auth gate, app shell, sidebar, topbar and the hash router.
 */
import { api, setUnauthorizedHandler, token } from './api.js';
import { store } from './store.js';
import {
  compactNumber, esc, html, icon, on, relTime, toast,
} from './ui.js';

const root = document.getElementById('root');

const NAV = [
  {
    label: 'Overview',
    items: [
      { route: 'dashboard', title: 'Dashboard', icon: 'dashboard' },
    ],
  },
  {
    label: 'Moderation',
    items: [
      { route: 'pending', title: 'Pending queue', icon: 'inbox', badge: 'pending' },
      { route: 'flagged', title: 'Flagged & reported', icon: 'flag', badge: 'flagged' },
      { route: 'posts', title: 'All posts', icon: 'posts' },
      { route: 'trash', title: 'Trash', icon: 'trash', badge: 'trashed' },
    ],
  },
  {
    label: 'Cleanup',
    items: [
      { route: 'cleaner', title: 'Bulk cleaner', icon: 'broom' },
      { route: 'rules', title: 'Cleanup rules', icon: 'rule' },
      { route: 'jobs', title: 'Run history', icon: 'job' },
    ],
  },
  {
    label: 'Workspace',
    items: [
      { route: 'groups', title: 'Groups', icon: 'users' },
      { route: 'members', title: 'Members', icon: 'ban' },
      { route: 'activity', title: 'Activity log', icon: 'history' },
      { route: 'settings', title: 'Settings', icon: 'gear' },
    ],
  },
];

const ROUTES = {
  dashboard: { title: 'Dashboard', sub: 'Your workspace at a glance', page: () => import('./pages/dashboard.js') },
  pending: { title: 'Pending queue', sub: 'Posts waiting for moderator approval', page: () => import('./pages/pending.js') },
  flagged: { title: 'Flagged & reported', sub: 'Content members reported to you', page: () => import('./pages/flagged.js') },
  posts: { title: 'All posts', sub: 'Every live post across your groups', page: () => import('./pages/posts.js') },
  trash: { title: 'Trash', sub: 'Restore or permanently delete removed posts', page: () => import('./pages/trash.js') },
  cleaner: { title: 'Bulk cleaner', sub: 'Delete matching posts across every group at once', page: () => import('./pages/cleaner.js') },
  rules: { title: 'Cleanup rules', sub: 'Automate the boring part of moderation', page: () => import('./pages/rules.js') },
  jobs: { title: 'Run history', sub: 'Every bulk sweep this workspace has run', page: () => import('./pages/jobs.js') },
  groups: { title: 'Groups', sub: 'The Facebook groups you administer', page: () => import('./pages/groups.js') },
  members: { title: 'Members', sub: 'Watch-list, bans and repeat offenders', page: () => import('./pages/members.js') },
  activity: { title: 'Activity log', sub: 'An audit trail of every moderation action', page: () => import('./pages/activity.js') },
  settings: { title: 'Settings', sub: 'Profile, security and workspace preferences', page: () => import('./pages/settings.js') },
};

/* ======================================================================
   Auth screen
   ==================================================================== */
function renderAuth(mode = 'login', prefillError = '') {
  root.innerHTML = `
    <div class="auth">
      <aside class="auth__aside">
        <div class="auth__brand">
          <span class="logo">${icon('shield', 'icon-lg')}</span> Group Post Cleaner
        </div>
        <div class="auth__pitch">
          <h1>Clean every group you run, from one console.</h1>
          <p>Pull the pending queue, bulk-delete posted spam across all of your groups,
             purge reported content and let rules handle the rest while you sleep.</p>
          <div class="auth__points">
            <div class="auth__point">${icon('inbox')}<span>Work the pending queue with one-click approve, decline and delete.</span></div>
            <div class="auth__point">${icon('broom')}<span>Sweep thousands of posted items by keyword, link, age, author or reports.</span></div>
            <div class="auth__point">${icon('undo')}<span>Everything lands in the trash first, so a mistake is one click from undone.</span></div>
            <div class="auth__point">${icon('rule')}<span>Nine pre-built cleanup rules, each previewable before it touches a post.</span></div>
          </div>
        </div>
        <span class="auth__demo">${icon('sparkle', 'icon-sm')} Demo workspace — <b style="margin-left:4px">admin@demo.com / demo1234</b></span>
      </aside>
      <div class="auth__panel">
        <div class="auth__card">
          <div class="auth__tabs" role="tablist">
            <button class="auth__tab" role="tab" data-mode="login" aria-selected="${mode === 'login'}">Sign in</button>
            <button class="auth__tab" role="tab" data-mode="register" aria-selected="${mode === 'register'}">Create workspace</button>
          </div>
          ${mode === 'login' ? loginForm() : registerForm()}
          ${prefillError ? `<div class="callout callout--danger" style="margin-top:16px">${icon('alert', 'icon-sm')}<div class="callout__body">${esc(prefillError)}</div></div>` : ''}
          <p class="auth__fineprint">
            ${mode === 'login'
              ? `Try the seeded workspace: <b>admin@demo.com</b> / <b>demo1234</b>`
              : 'Your new workspace starts empty — connect a group to get going.'}
          </p>
        </div>
      </div>
    </div>`;

  on(root, 'click', '.auth__tab', (event, el) => renderAuth(el.dataset.mode));

  if (mode === 'login') {
    root.querySelector('[data-demo]').addEventListener('click', () => {
      root.querySelector('#email').value = 'admin@demo.com';
      root.querySelector('#password').value = 'demo1234';
      root.querySelector('form').requestSubmit();
    });
    root.querySelector('form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const button = form.querySelector('button[type=submit]');
      button.disabled = true;
      button.innerHTML = `${icon('refresh', 'icon-sm')} Signing in…`;
      try {
        const session = await api.login(form.email.value.trim(), form.password.value);
        token.set(session.token);
        store.setSession(session.user);
        toast({ kind: 'success', title: `Welcome back, ${session.user.name.split(' ')[0]}`, text: 'Demo workspace loaded.' });
        await boot();
      } catch (error) {
        toast({ kind: 'error', title: 'Could not sign in', text: error.message });
        button.disabled = false;
        button.innerHTML = `${icon('logout', 'icon-sm')} Sign in`;
      }
    });
  } else {
    root.querySelector('form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const button = form.querySelector('button[type=submit]');
      button.disabled = true;
      button.innerHTML = `${icon('refresh', 'icon-sm')} Creating…`;
      try {
        const session = await api.register({
          name: form.name.value.trim(),
          email: form.email.value.trim(),
          password: form.password.value,
        });
        token.set(session.token);
        store.setSession(session.user);
        toast({ kind: 'success', title: 'Workspace created', text: 'Connect your first group to start cleaning.' });
        await boot();
      } catch (error) {
        toast({ kind: 'error', title: 'Could not create the workspace', text: error.message });
        button.disabled = false;
        button.innerHTML = `${icon('plus', 'icon-sm')} Create workspace`;
      }
    });
  }
}

function loginForm() {
  return `
    <h2>Sign in</h2>
    <p>Moderate every group from a single queue.</p>
    <form novalidate>
      <div class="field">
        <label for="email">Email</label>
        <input id="email" name="email" type="email" autocomplete="username" placeholder="you@example.com" required>
      </div>
      <div class="field">
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="current-password" placeholder="••••••••" required>
      </div>
      <button class="btn btn--primary btn--lg btn--block" type="submit">${icon('logout', 'icon-sm')} Sign in</button>
      <button class="btn btn--ghost btn--block" type="button" data-demo style="margin-top:8px">
        ${icon('sparkle', 'icon-sm')} Use the demo workspace
      </button>
    </form>`;
}

function registerForm() {
  return `
    <h2>Create your workspace</h2>
    <p>Free while this is a demo — no card, no Facebook app review.</p>
    <form novalidate>
      <div class="field">
        <label for="name">Your name</label>
        <input id="name" name="name" type="text" autocomplete="name" placeholder="Alex Rivera" minlength="2" required>
      </div>
      <div class="field">
        <label for="email">Email</label>
        <input id="email" name="email" type="email" autocomplete="username" placeholder="you@example.com" required>
      </div>
      <div class="field">
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="new-password" placeholder="At least 8 characters" minlength="8" required>
        <span class="hint">Minimum 8 characters.</span>
      </div>
      <button class="btn btn--primary btn--lg btn--block" type="submit">${icon('plus', 'icon-sm')} Create workspace</button>
    </form>`;
}

/* ======================================================================
   App shell
   ==================================================================== */
function renderShell() {
  root.innerHTML = `
    <div class="shell">
      <nav class="sidebar" id="sidebar" aria-label="Main">
        <div class="sidebar__brand">
          <span class="logo">${icon('shield')}</span>
          <span>Post Cleaner</span>
          <span class="spacer"></span>
          <button class="btn btn--ghost btn--sm btn--icon" data-close-sidebar aria-label="Close menu">${icon('x', 'icon-sm')}</button>
        </div>
        <div class="sidebar__scroll">
          ${NAV.map((section) => `
            <div class="nav__label">${esc(section.label)}</div>
            ${section.items.map((item) => `
              <a class="nav__item" href="#/${item.route}" data-route="${item.route}">
                ${icon(item.icon)}<span>${esc(item.title)}</span>
                ${item.badge ? `<span class="nav__count" data-badge="${item.badge}">0</span>` : ''}
              </a>`).join('')}
          `).join('')}
        </div>
        <div class="sidebar__foot">
          <div class="storage">
            <div class="row" style="justify-content:space-between">
              <span class="strong" style="font-size:12.5px">Workspace health</span>
              <span class="tiny muted" data-health-label>—</span>
            </div>
            <div class="storage__bar"><div class="storage__fill" data-health style="width:0%"></div></div>
            <div class="tiny muted"><span data-cleaned>0</span> posts cleaned up</div>
          </div>
        </div>
      </nav>
      <div class="scrim hidden" data-scrim></div>
      <div class="main">
        <header class="topbar">
          <button class="iconbtn" data-open-sidebar aria-label="Open menu">${icon('menu')}</button>
          <div style="min-width:0">
            <div class="topbar__title" data-page-title>Dashboard</div>
            <div class="topbar__sub" data-page-sub></div>
          </div>
          <span class="spacer"></span>
          <div class="searchbox">
            ${icon('search', 'icon-sm')}
            <input type="search" id="global-search" placeholder="Search posts, groups, members…" aria-label="Search">
            <kbd>/</kbd>
          </div>
          <button class="iconbtn" data-sync aria-label="Sync all groups" title="Sync all groups">${icon('refresh')}</button>
          <button class="iconbtn" data-theme aria-label="Toggle colour theme">${icon(store.theme === 'dark' ? 'sun' : 'moon')}</button>
          <div class="menu">
            <button class="menu__trigger" data-menu-trigger aria-haspopup="true">
              <span class="avatar" data-user-avatar>AR</span>
              <span class="menu__name" data-user-name>—</span>
              ${icon('x', 'icon-sm')}
            </button>
          </div>
        </header>
        <main class="content" id="view" tabindex="-1"></main>
      </div>
    </div>`;

  paintUser();
  paintSidebar();

  const sidebar = document.getElementById('sidebar');
  const scrim = root.querySelector('[data-scrim]');
  const toggleSidebar = (open) => {
    sidebar.classList.toggle('is-open', open);
    scrim.classList.toggle('hidden', !open);
  };
  on(root, 'click', '[data-open-sidebar]', () => toggleSidebar(true));
  on(root, 'click', '[data-close-sidebar]', () => toggleSidebar(false));
  scrim.addEventListener('click', () => toggleSidebar(false));
  on(root, 'click', '.nav__item', () => toggleSidebar(false));

  on(root, 'click', '[data-theme]', () => {
    store.toggleTheme();
    root.querySelector('[data-theme]').innerHTML = icon(store.theme === 'dark' ? 'sun' : 'moon');
  });

  on(root, 'click', '[data-sync]', async (event, button) => {
    if (button.classList.contains('is-busy')) return;
    button.classList.add('is-busy');
    const groups = await store.loadGroups();
    let created = 0;
    try {
      for (const group of groups.filter((item) => item.connected)) {
        const result = await api.syncGroup(group.id);
        created += result.created;
      }
      store.invalidateStats();
      store.groupsLoaded = false;
      toast({ kind: 'success', title: `Synced ${groups.filter((g) => g.connected).length} groups`, text: `${created} new post(s) pulled from Facebook.` });
      await route(true);
    } catch (error) {
      toast({ kind: 'error', title: 'Sync failed', text: error.message });
    } finally {
      button.classList.remove('is-busy');
    }
  });

  on(root, 'click', '[data-menu-trigger]', (event) => {
    event.stopPropagation();
    const existing = root.querySelector('.menu__panel');
    if (existing) { existing.remove(); return; }
    const panel = html(`
      <div class="menu__panel">
        <div class="menu__head">
          <div class="strong" style="font-size:13px">${esc(store.user?.name || '')}</div>
          <div class="tiny muted truncate">${esc(store.user?.email || '')}</div>
          <span class="badge badge--primary" style="margin-top:6px">${esc(store.user?.role || 'owner')}</span>
        </div>
        <a class="menu__item" href="#/settings">${icon('gear', 'icon-sm')} Settings</a>
        <a class="menu__item" href="#/activity">${icon('history', 'icon-sm')} Activity log</a>
        <a class="menu__item" href="/api/docs" target="_blank" rel="noopener">${icon('external', 'icon-sm')} API documentation</a>
        <div class="divider" style="margin:6px 0"></div>
        <button class="menu__item is-danger" data-logout>${icon('logout', 'icon-sm')} Sign out</button>
      </div>`);
    root.querySelector('.menu').append(panel);
    panel.querySelector('[data-logout]').addEventListener('click', async () => {
      try { await api.logout(); } catch { /* token may already be gone */ }
      store.clearSession();
      toast({ kind: 'info', title: 'Signed out', text: 'Your workspace data is still on the server.' });
      renderAuth('login');
    });
  });
  document.addEventListener('click', () => root.querySelector('.menu__panel')?.remove());

  const search = root.querySelector('#global-search');
  search.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      const term = search.value.trim();
      window.location.hash = term ? `#/posts?q=${encodeURIComponent(term)}` : '#/posts';
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '')) {
      event.preventDefault();
      search.focus();
    }
  });

  store.subscribe((eventName) => {
    if (eventName === 'stats') paintSidebar();
  });
}

function paintUser() {
  if (!store.user) return;
  const avatarEl = root.querySelector('[data-user-avatar]');
  avatarEl.textContent = store.user.avatar_seed || '??';
  avatarEl.dataset.c = String((store.user.avatar_seed || 'A').charCodeAt(0) % 7);
  root.querySelector('[data-user-name]').textContent = store.user.name;
}

function paintSidebar() {
  const { counts } = store;
  root.querySelectorAll('[data-badge]').forEach((badge) => {
    const value = counts[badge.dataset.badge] || 0;
    badge.textContent = value > 99 ? '99+' : value;
    badge.classList.toggle('hidden', value === 0);
    badge.classList.toggle('is-hot', badge.dataset.badge !== 'trashed' && value > 0);
  });
  const health = store.stats?.cleanup?.health;
  if (typeof health === 'number') {
    root.querySelector('[data-health]').style.width = `${health}%`;
    root.querySelector('[data-health-label]').textContent = health >= 80 ? 'Healthy' : health >= 55 ? 'Needs attention' : 'Noisy';
  }
  const cleaned = (store.stats?.posts?.purged || 0) + (store.stats?.cleanup?.auto_removed || 0);
  const cleanedEl = root.querySelector('[data-cleaned]');
  if (cleanedEl) cleanedEl.textContent = compactNumber(cleaned);
}

/* ======================================================================
   Router
   ==================================================================== */
function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const name = (path || 'dashboard').replace(/\/$/, '');
  return { name: ROUTES[name] ? name : 'dashboard', params: new URLSearchParams(query) };
}

let currentRender = null;
let renderToken = 0;

export async function route(force = false) {
  const { name, params } = parseHash();
  const definition = ROUTES[name];
  if (!definition) return;

  const view = document.getElementById('view');
  if (!view) return;
  if (!force && currentRender === name) {
    // Same page, new query string (e.g. sidebar badge click) — re-render.
  }
  currentRender = name;

  root.querySelectorAll('.nav__item').forEach((item) => {
    item.classList.toggle('is-active', item.dataset.route === name);
    if (item.dataset.route === name) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });
  root.querySelector('[data-page-title]').textContent = definition.title;
  root.querySelector('[data-page-sub]').textContent = definition.sub;

  const ticket = ++renderToken;
  view.innerHTML = `<div class="fade-in">${'<div class="skeleton sk-line" style="height:28px;width:34%;margin-bottom:18px"></div>'}
    <div class="skeleton sk-stat" style="margin-bottom:16px"></div>
    <div class="skeleton sk-stat" style="height:280px"></div></div>`;

  try {
    const module = await definition.page();
    if (ticket !== renderToken) return; // a newer navigation won
    view.innerHTML = '';
    await module.render(view, { params, navigate });
    view.classList.add('fade-in');
    setTimeout(() => view.classList.remove('fade-in'), 240);
  } catch (error) {
    if (ticket !== renderToken) return;
    console.error(error);
    view.innerHTML = `
      <div class="empty">
        <div class="empty__icon" style="background:var(--danger-soft);color:var(--danger)">${icon('alert')}</div>
        <h3>This page failed to load</h3>
        <p>${esc(error.message || String(error))}</p>
        <div class="empty__actions"><button class="btn btn--primary" data-reload>Reload</button></div>
      </div>`;
    view.querySelector('[data-reload]').addEventListener('click', () => route(true));
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

export function navigate(path, params) {
  const search = params ? `?${new URLSearchParams(params).toString()}` : '';
  window.location.hash = `#/${path}${search}`;
}

/* ======================================================================
   Boot
   ==================================================================== */
async function boot() {
  renderShell();
  window.addEventListener('hashchange', () => route());
  try {
    await store.loadGroups();
    await store.loadStats(true);
  } catch (error) {
    toast({ kind: 'warn', title: 'Could not preload workspace data', text: error.message });
  }
  if (!window.location.hash) window.location.hash = '#/dashboard';
  await route(true);
}

setUnauthorizedHandler(() => {
  store.clearSession();
  toast({ kind: 'warn', title: 'Session expired', text: 'Please sign in again.' });
  renderAuth('login');
});

async function start() {
  store.applyTheme();
  const saved = token.get();
  if (!saved) {
    renderAuth('login');
    return;
  }
  try {
    store.setSession(await api.me());
  } catch {
    token.clear();
    renderAuth('login');
    return;
  }
  await boot();
}

start();

export { relTime };
