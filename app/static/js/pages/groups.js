/** Groups — connect, edit, sync, inspect health, disconnect. */
import { api } from '../api.js';
import { store } from '../store.js';
import {
  compactNumber, confirmDialog, debounce, emptyState, esc, errorState, formData,
  fullTime, icon, openModal, plural, relTime, skeletonCards, toast,
} from '../ui.js';

const CATEGORIES = ['Community', 'Careers', 'Technology', 'Hobby', 'Food & Drink', 'Home & Garden', 'Home Improvement', 'Sports', 'Buy & Sell', 'Support'];
const PRIVACY = [['public', 'Public'], ['private', 'Private'], ['hidden', 'Hidden']];
const MODERATION = [
  ['post_approval', 'Approve every post'],
  ['keyword_filter', 'Keyword filter'],
  ['admin_only', 'Admins only'],
  ['open', 'Open posting'],
];

export async function render(view) {
  view.innerHTML = `
    <div class="page__head">
      <div>
        <h1>${icon('users')} Groups</h1>
        <p class="page__desc">The Facebook groups you administer. Each one syncs its posts into the shared moderation queue; disconnecting a group removes its posts from this workspace.</p>
      </div>
      <div class="page__actions">
        <button class="btn" data-sync-all>${icon('refresh', 'icon-sm')} Sync all</button>
        <button class="btn btn--primary" data-new>${icon('plus', 'icon-sm')} Connect a group</button>
      </div>
    </div>
    <div class="toolbar">
      <div class="toolbar__search">${icon('search', 'icon-sm')}<input type="search" placeholder="Search groups…" aria-label="Search groups"></div>
      <span class="spacer"></span>
      <span class="tiny muted" data-count></span>
    </div>
    <div data-list>${skeletonCards(6)}</div>`;

  const listEl = view.querySelector('[data-list]');
  const countEl = view.querySelector('[data-count]');
  let query = '';

  const paint = async () => {
    listEl.innerHTML = skeletonCards(4);
    try {
      const { items, pagination } = await api.groups({ q: query, per_page: 200 });
      await store.loadGroups(true);
      countEl.textContent = `${plural(pagination.total, 'group')}`;
      if (!items.length) {
        listEl.innerHTML = `<div class="card">${query ? emptyState({
          icon: 'search', title: 'No groups match', message: `Nothing matches "${query}".`,
          actions: '<button class="btn" data-reset>Clear search</button>',
        }) : emptyState({
          icon: 'users', title: 'No groups connected',
          message: 'Connect your first Facebook group to start pulling its posts into the queue.',
          actions: '<button class="btn btn--primary" data-new-empty>Connect a group</button>',
        })}</div>`;
        listEl.querySelector('[data-reset]')?.addEventListener('click', () => {
          view.querySelector('input[type=search]').value = '';
          query = '';
          paint();
        });
        listEl.querySelector('[data-new-empty]')?.addEventListener('click', () => openGroupDialog(null, paint));
        return;
      }
      listEl.innerHTML = `<div class="grid grid--groups">${items.map(card).join('')}</div>`;
    } catch (error) {
      listEl.innerHTML = `<div class="card">${errorState(error.message)}</div>`;
      listEl.querySelector('[data-retry]').addEventListener('click', paint);
    }
  };

  function card(group) {
    const initials = group.name.split(' ').filter(Boolean).slice(0, 2).map((word) => word[0]).join('').toUpperCase();
    const hue = [...group.name].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 360;
    return `
      <div class="card groupcard" data-group="${group.id}">
        <div class="groupcard__top">
          <div class="groupcard__icon" style="--g1:hsl(${hue} 70% 55%);--g2:hsl(${(hue + 42) % 360} 70% 48%)">${esc(initials)}</div>
          <div style="flex:1;min-width:0">
            <div class="row" style="gap:7px">
              <h3 class="truncate">${esc(group.name)}</h3>
              ${group.connected
                ? `<span class="badge badge--published"><span class="dot"></span>Connected</span>`
                : `<span class="badge badge--off"><span class="dot"></span>Paused</span>`}
            </div>
            <div class="tiny muted truncate">@${esc(group.handle)}</div>
            <div class="row wrap tiny muted" style="gap:8px;margin-top:6px">
              <span>${icon(group.privacy === 'public' ? 'globe' : 'lock', 'icon-sm')} ${esc(group.privacy)}</span>
              <span>${icon('users', 'icon-sm')} ${compactNumber(group.members)}</span>
              <span>${icon('posts', 'icon-sm')} ~${group.daily_posts}/day</span>
            </div>
          </div>
        </div>
        ${group.description ? `<div style="padding:0 16px 12px"><p class="small muted" style="line-height:1.6">${esc(group.description)}</p></div>` : ''}
        <div class="groupcard__stats">
          <div class="groupcard__stat"><b>${group.stats.posts}</b><span>Live</span></div>
          <div class="groupcard__stat"><b style="color:var(--warn)">${group.stats.pending}</b><span>Pending</span></div>
          <div class="groupcard__stat"><b style="color:var(--danger)">${group.stats.flagged}</b><span>Flagged</span></div>
          <div class="groupcard__stat"><b style="color:var(--text-3)">${group.stats.trashed}</b><span>Trash</span></div>
        </div>
        <div class="groupcard__foot">
          <a class="btn btn--sm" href="#/posts?group=${group.id}">${icon('posts', 'icon-sm')} Posts</a>
          <a class="btn btn--sm" href="#/pending?group=${group.id}">${icon('inbox', 'icon-sm')} Queue</a>
          <span class="spacer"></span>
          <button class="btn btn--sm btn--ghost btn--icon" data-health aria-label="Group health" title="Health">${icon('trend', 'icon-sm')}</button>
          <button class="btn btn--sm btn--ghost btn--icon" data-sync-one aria-label="Sync group" title="Sync now">${icon('refresh', 'icon-sm')}</button>
          <button class="btn btn--sm btn--ghost btn--icon" data-edit aria-label="Edit group" title="Edit">${icon('edit', 'icon-sm')}</button>
          <button class="btn btn--sm btn--ghost btn--icon" data-disconnect aria-label="Disconnect group" title="Disconnect" style="color:var(--danger)">${icon('x', 'icon-sm')}</button>
        </div>
      </div>`;
  }

  view.querySelector('input[type=search]').addEventListener('input', debounce((event) => {
    query = event.target.value.trim();
    paint();
  }));
  view.querySelector('[data-new]').addEventListener('click', () => openGroupDialog(null, paint));

  view.querySelector('[data-sync-all]').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = `${icon('refresh', 'icon-sm')} Syncing…`;
    try {
      const { items } = await api.groups({ per_page: 200 });
      let created = 0;
      for (const group of items.filter((item) => item.connected)) {
        created += (await api.syncGroup(group.id)).created;
      }
      toast({ kind: 'success', title: 'All groups synced', text: `${plural(created, 'new post')} pulled in.` });
      store.invalidateStats();
      await paint();
    } catch (error) {
      toast({ kind: 'error', title: 'Sync failed', text: error.message });
    } finally {
      button.disabled = false;
      button.innerHTML = `${icon('refresh', 'icon-sm')} Sync all`;
    }
  });

  listEl.addEventListener('click', async (event) => {
    const cardEl = event.target.closest('[data-group]');
    if (!cardEl) return;
    const id = Number(cardEl.dataset.group);

    if (event.target.closest('[data-sync-one]')) {
      const button = event.target.closest('button');
      button.classList.add('is-busy');
      try {
        const result = await api.syncGroup(id);
        toast({ kind: 'success', title: `${plural(result.created, 'new post')}`, text: 'Pulled from Facebook just now.' });
        store.invalidateStats();
        await paint();
      } catch (error) {
        toast({ kind: 'error', title: 'Sync failed', text: error.message });
        button.classList.remove('is-busy');
      }
      return;
    }
    if (event.target.closest('[data-edit]')) {
      const { items } = await api.groups({ per_page: 200 });
      openGroupDialog(items.find((group) => group.id === id), paint);
      return;
    }
    if (event.target.closest('[data-health]')) {
      await showHealth(id);
      return;
    }
    if (event.target.closest('[data-disconnect]')) {
      const ok = await confirmDialog({
        title: 'Disconnect this group?',
        message: 'Its posts, rules and history will be removed from this workspace. You can reconnect later.',
        confirmLabel: 'Disconnect',
        danger: true,
      });
      if (!ok) return;
      try {
        await api.deleteGroup(id);
        toast({ kind: 'success', title: 'Group disconnected' });
        store.invalidateStats();
        store.loadStats(true).catch(() => {});
        await paint();
      } catch (error) {
        toast({ kind: 'error', title: 'Could not disconnect', text: error.message });
      }
    }
  });

  await paint();
}

async function showHealth(id) {
  const { root, close } = openModal({
    title: 'Group health',
    body: '<div class="skeleton" style="height:260px"></div>',
    footer: '<button class="btn btn--primary" data-done>Close</button>',
    size: 'lg',
  });
  root.querySelector('[data-done]').addEventListener('click', close);
  try {
    const data = await api.groupHealth(id);
    const group = data.group;
    root.querySelector('.modal__head h3').textContent = group.name;
    root.querySelector('.modal__body').innerHTML = `
      <div class="split" style="grid-template-columns:150px 1fr;gap:20px;align-items:center">
        <div class="donut">
          ${donut(data.score)}
        </div>
        <div>
          <div class="grid grid--stats" style="grid-template-columns:repeat(auto-fit,minmax(110px,1fr))">
            ${[['Live posts', group.stats.posts, 'var(--primary)'], ['Pending', group.stats.pending, 'var(--warn)'],
              ['Flagged', group.stats.flagged, 'var(--danger)'], ['In trash', group.stats.trashed, 'var(--text-3)'],
              ['Noisy', data.noise, 'var(--info)']]
              .map(([label, value, accent]) => `
                <div class="stat" style="--accent:${accent};padding:11px">
                  <div class="tiny muted">${label}</div>
                  <div style="font-size:19px;font-weight:670">${value}</div>
                </div>`).join('')}
          </div>
          <dl class="kv-list" style="margin-top:14px">
            <div class="kv"><dt>Moderation mode</dt><dd>${esc(group.moderation.replace(/_/g, ' '))}</dd></div>
            <div class="kv"><dt>Last synced</dt><dd>${esc(group.last_synced_at ? relTime(group.last_synced_at) : 'never')}</dd></div>
            <div class="kv"><dt>Connected since</dt><dd>${esc(fullTime(group.created_at))}</dd></div>
          </dl>
        </div>
      </div>
      <div class="grid grid--2" style="margin-top:18px">
        <div>
          <h3 style="margin-bottom:8px">Posts by type</h3>
          ${data.by_type.length ? data.by_type.map((item) => `
            <div class="bar-row">
              <span class="small" style="text-transform:capitalize">${esc(item.type)}</span>
              <span class="small muted">${item.count}</span>
              <div class="bar-row__track"><div class="bar-row__fill" style="width:${Math.round((item.count / Math.max(...data.by_type.map((t) => t.count))) * 100)}%"></div></div>
            </div>`).join('') : '<p class="muted small">No posts yet.</p>'}
        </div>
        <div>
          <h3 style="margin-bottom:8px">Most removed authors</h3>
          ${data.top_removed_authors.length ? data.top_removed_authors.map((item) => `
            <div class="bar-row">
              <span class="small truncate">${esc(item.name)}</span>
              <span class="small muted">${item.count} removed</span>
              <div class="bar-row__track"><div class="bar-row__fill" style="width:${Math.round((item.count / data.top_removed_authors[0].count) * 100)}%;--fill:var(--danger)"></div></div>
            </div>`).join('') : '<p class="muted small">Nobody has had posts removed here.</p>'}
        </div>
      </div>`;
  } catch (error) {
    root.querySelector('.modal__body').innerHTML = errorState(error.message);
  }
}

function donut(score) {
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - score / 100);
  const colour = score >= 80 ? 'var(--success)' : score >= 55 ? 'var(--warn)' : 'var(--danger)';
  return `
    <svg width="132" height="132" viewBox="0 0 132 132">
      <circle cx="66" cy="66" r="${radius}" fill="none" stroke="var(--surface-3)" stroke-width="12"></circle>
      <circle cx="66" cy="66" r="${radius}" fill="none" stroke="${colour}" stroke-width="12"
        stroke-linecap="round" stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"></circle>
    </svg>
    <div class="donut__center">
      <div class="donut__value">${score}</div>
      <div class="donut__label">Health</div>
    </div>`;
}

function openGroupDialog(group, onSaved) {
  const editing = Boolean(group?.id);
  const body = `
    <form id="group-form" novalidate>
      <div class="field">
        <label for="gf-name">Group name</label>
        <input id="gf-name" name="name" type="text" value="${esc(group?.name || '')}" placeholder="Bay Area Foodies" minlength="2" required>
        <span class="err">Give the group a name.</span>
      </div>
      <div class="field">
        <label for="gf-handle">Handle / slug</label>
        <input id="gf-handle" name="handle" type="text" value="${esc(group?.handle || '')}" placeholder="bay-area-foodies">
        <span class="hint">Leave blank to generate one from the name.</span>
      </div>
      <div class="field">
        <label for="gf-desc">Description</label>
        <textarea id="gf-desc" name="description" placeholder="What is this group about?">${esc(group?.description || '')}</textarea>
      </div>
      <div class="field">
        <label for="gf-url">Facebook URL</label>
        <input id="gf-url" name="url" type="text" value="${esc(group?.url || '')}" placeholder="https://facebook.com/groups/…">
      </div>
      <div class="form__grid">
        <div class="field">
          <label for="gf-category">Category</label>
          <select id="gf-category" name="category">
            ${CATEGORIES.map((value) => `<option value="${value}" ${(group?.category || 'Community') === value ? 'selected' : ''}>${value}</option>`).join('')}
          </select>
        </div>
        <div class="field">
          <label for="gf-privacy">Privacy</label>
          <select id="gf-privacy" name="privacy">
            ${PRIVACY.map(([value, label]) => `<option value="${value}" ${(group?.privacy || 'private') === value ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </div>
        <div class="field">
          <label for="gf-members">Members</label>
          <input id="gf-members" name="members" type="number" min="0" value="${group?.members ?? 0}">
        </div>
        <div class="field">
          <label for="gf-daily">Posts per day</label>
          <input id="gf-daily" name="daily_posts" type="number" min="0" value="${group?.daily_posts ?? 0}">
        </div>
      </div>
      <div class="form__row">
        <div class="field">
          <label for="gf-moderation">Moderation mode</label>
          <select id="gf-moderation" name="moderation">
            ${MODERATION.map(([value, label]) => `<option value="${value}" ${(group?.moderation || 'post_approval') === value ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </div>
        <div class="field" style="justify-content:flex-end">
          <label class="check"><input type="checkbox" name="connected" ${group?.connected === false ? '' : 'checked'}><span>Connection is live</span></label>
        </div>
      </div>
    </form>`;

  const { root, close } = openModal({
    title: editing ? 'Edit group' : 'Connect a group',
    subtitle: editing ? group.name : 'Add a Facebook group you administer',
    body,
    footer: `<button class="btn" data-cancel>Cancel</button>
             <button class="btn btn--primary" data-save>${icon('check', 'icon-sm')} ${editing ? 'Save group' : 'Connect group'}</button>`,
  });

  const form = root.querySelector('#group-form');
  root.querySelector('[data-cancel]').addEventListener('click', close);

  root.querySelector('[data-save]').addEventListener('click', async () => {
    const data = formData(form);
    const nameField = form.name.closest('.field');
    nameField.classList.toggle('has-error', data.name.trim().length < 2);
    if (data.name.trim().length < 2) return;

    const payload = {
      name: data.name.trim(),
      handle: data.handle.trim() || null,
      description: data.description || '',
      url: data.url || '',
      category: data.category,
      privacy: data.privacy,
      members: Number(data.members || 0),
      daily_posts: Number(data.daily_posts || 0),
      moderation: data.moderation,
      connected: Boolean(data.connected),
    };

    const button = root.querySelector('[data-save]');
    button.disabled = true;
    try {
      if (editing) await api.updateGroup(group.id, payload);
      else await api.createGroup(payload);
      toast({ kind: 'success', title: editing ? 'Group saved' : 'Group connected', text: payload.name });
      close();
      onSaved?.();
    } catch (error) {
      button.disabled = false;
      toast({ kind: 'error', title: 'Could not save the group', text: error.message });
    }
  });
}
