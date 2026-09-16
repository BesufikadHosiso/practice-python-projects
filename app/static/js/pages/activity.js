/** Activity log — the audit trail of every moderation action. */
import { api } from '../api.js';
import {
  confirmDialog, debounce, emptyState, esc, errorState, fullTime, icon, pager,
  plural, relTime, toast,
} from '../ui.js';

const FILTERS = [
  ['', 'Everything'],
  ['post.', 'Posts'],
  ['rule.', 'Rules'],
  ['group.', 'Groups'],
  ['author.', 'Members'],
  ['auth.', 'Account'],
  ['clean.', 'Sweeps'],
];

const ICONS = {
  'post.deleted': ['trash-sm', 'var(--danger)'], 'post.purged': ['trash-sm', 'var(--danger)'],
  'post.declined': ['x', 'var(--danger)'], 'post.flagged': ['flag', 'var(--warn)'],
  'post.approved': ['check-circle', 'var(--success)'], 'post.restored': ['undo', 'var(--success)'],
  'post.unflagged': ['check', 'var(--success)'], 'post.created': ['plus', 'var(--primary)'],
  'post.updated': ['edit', 'var(--info)'], 'post.archived': ['stack', 'var(--text-3)'],
  'rule.created': ['rule', 'var(--primary)'], 'rule.updated': ['edit', 'var(--info)'],
  'rule.ran': ['play', 'var(--primary)'], 'rule.deleted': ['trash-sm', 'var(--danger)'],
  'rule.toggled': ['gear', 'var(--text-3)'],
  'group.connected': ['users', 'var(--success)'], 'group.disconnected': ['x', 'var(--danger)'],
  'group.updated': ['edit', 'var(--info)'], 'group.synced': ['refresh', 'var(--info)'],
  'author.added': ['plus', 'var(--primary)'], 'author.updated': ['ban', 'var(--warn)'],
  'author.removed': ['trash-sm', 'var(--danger)'],
  'auth.login': ['logout', 'var(--text-3)'], 'auth.logout': ['logout', 'var(--text-3)'],
  'auth.registered': ['sparkle', 'var(--primary)'], 'auth.profile_updated': ['edit', 'var(--info)'],
  'auth.password_changed': ['lock', 'var(--warn)'],
  'clean.job': ['broom', 'var(--primary)'],
};

export async function render(view) {
  let page = 1;
  let query = '';
  let action = '';

  view.innerHTML = `
    <div class="page__head">
      <div>
        <h1>${icon('history')} Activity log</h1>
        <p class="page__desc">Every approval, deletion, rule run and settings change in this workspace, newest first.</p>
      </div>
      <div class="page__actions">
        <button class="btn btn--danger" data-clear>${icon('trash-sm', 'icon-sm')} Clear log</button>
      </div>
    </div>
    <div class="toolbar">
      <div class="toolbar__search">${icon('search', 'icon-sm')}<input type="search" placeholder="Search the log…" aria-label="Search activity"></div>
      <span class="spacer"></span>
      <span class="tiny muted" data-count></span>
    </div>
    <div class="pill-group" style="margin-bottom:14px">
      ${FILTERS.map(([value, label]) => `<button class="chip" data-filter="${value}" aria-pressed="${value === ''}">${label}</button>`).join('')}
    </div>
    <div class="card"><div class="card__body" data-list></div></div>`;

  const listEl = view.querySelector('[data-list]');
  const countEl = view.querySelector('[data-count]');

  const paint = async () => {
    listEl.innerHTML = `<div style="padding:6px">${Array.from({ length: 8 }, () => '<div class="skeleton sk-line" style="height:34px;margin-bottom:8px"></div>').join('')}</div>`;
    try {
      const { items, pagination } = await api.activity({ q: query, action, page, per_page: 20 });
      countEl.textContent = `${plural(pagination.total, 'event')}`;
      if (!items.length) {
        listEl.innerHTML = emptyState({
          icon: 'history',
          title: query || action ? 'Nothing matches' : 'No activity yet',
          message: query || action
            ? 'Try a different search term or clear the filter.'
            : 'Actions you take across the console will be recorded here.',
        });
        return;
      }
      listEl.innerHTML = `
        <div class="timeline">
          ${items.map((entry) => {
            const [name, colour] = ICONS[entry.action] || ['info', 'var(--text-3)'];
            return `
              <div class="tl-item">
                <span class="tl-item__dot" style="--dot:${colour}"></span>
                <div class="tl-item__head">
                  <span style="color:${colour};display:inline-flex">${icon(name, 'icon-sm')}</span>
                  <span class="strong" style="font-size:13px">${esc(prettyAction(entry.action))}</span>
                  <span class="tiny muted">by ${esc(entry.actor)}</span>
                  ${entry.group_name ? `<span class="badge">${esc(entry.group_name)}</span>` : ''}
                  <span class="tl-item__when" title="${esc(fullTime(entry.created_at))}">${esc(relTime(entry.created_at))}</span>
                </div>
                <div class="tl-item__detail">
                  <span class="strong" style="font-weight:560">${esc(entry.target_label)}</span>
                  ${entry.detail ? ` — ${esc(entry.detail)}` : ''}
                </div>
              </div>`;
          }).join('')}
        </div>
        ${pager({ page: pagination.page, perPage: pagination.per_page, total: pagination.total })}`;
    } catch (error) {
      listEl.innerHTML = errorState(error.message);
      listEl.querySelector('[data-retry]').addEventListener('click', paint);
    }
  };

  view.querySelector('input[type=search]').addEventListener('input', debounce((event) => {
    query = event.target.value.trim();
    page = 1;
    paint();
  }));

  view.addEventListener('click', (event) => {
    const chip = event.target.closest('[data-filter]');
    if (chip) {
      view.querySelectorAll('[data-filter]').forEach((item) => item.setAttribute('aria-pressed', String(item === chip)));
      action = chip.dataset.filter;
      page = 1;
      paint();
      return;
    }
    const pageButton = event.target.closest('[data-page]');
    if (pageButton && !pageButton.disabled) {
      page = Number(pageButton.dataset.page);
      paint();
    }
  });

  view.querySelector('[data-clear]').addEventListener('click', async () => {
    const ok = await confirmDialog({
      title: 'Clear the activity log?',
      message: 'This deletes the audit trail for the workspace. Posts and rules are untouched.',
      confirmLabel: 'Clear log',
      danger: true,
    });
    if (!ok) return;
    try {
      const result = await api.clearActivity();
      toast({ kind: 'success', title: `Cleared ${plural(result.removed, 'event')}` });
      await paint();
    } catch (error) {
      toast({ kind: 'error', title: 'Could not clear the log', text: error.message });
    }
  });

  await paint();
}

function prettyAction(action) {
  const [area, verb] = action.split('.');
  return `${(verb || action).replace(/_/g, ' ')} · ${area}`;
}
