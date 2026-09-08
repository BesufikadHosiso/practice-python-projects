/**
 * Shared post-list engine.
 *
 * Used by "All posts", "Pending queue", "Flagged & reported" and "Trash".
 * Owns: filters, pagination, multi-select, the sticky bulk bar, and optimistic
 * mutations with rollback + undo.
 */
import { api } from '../api.js';
import { store } from '../store.js';
import {
  debounce, emptyState, esc, errorState, fullTime, html, icon, linkify, on, pager,
  plural, relTime, skeletonPosts, stateBadge, toast, typeBadge,
} from '../ui.js';
import { openPostDrawer, openPostEditor } from '../components/postDialogs.js';

const DEFAULT_ACTIONS = ['view', 'delete'];

export class PostList {
  /**
   * @param {HTMLElement} view      container to render into
   * @param {object} options
   *   fetch(params)              -> {items, pagination}
   *   toolbar                    extra toolbar HTML appended after the search box
   *   actions                    row action names
   *   selectable                 show checkboxes
   *   bulkActions                bulk bar buttons [{action,label,icon,danger}]
   *   empty                      {icon,title,message,actions}
   *   title                      heading above the list
   *   filters                    initial filter state (merged into every request)
   *   showGroup                  include the group chip on each card
   *   pageSize
   */
  constructor(view, options) {
    this.view = view;
    this.options = {
      selectable: true,
      actions: DEFAULT_ACTIONS,
      bulkActions: [
        { action: 'delete', label: 'Delete', icon: 'trash-sm', danger: true },
        { action: 'flag', label: 'Flag', icon: 'flag' },
        { action: 'approve', label: 'Approve', icon: 'check' },
      ],
      showGroup: true,
      pageSize: 25,
      filters: {},
      ...options,
    };
    this.state = {
      items: [],
      page: 1,
      perPage: this.options.pageSize,
      total: 0,
      loading: true,
      error: null,
      selected: new Set(),
      q: '',
      sort: 'newest',
    };
    this.mount();
  }

  /* ------------------------------------------------------------ lifecycle */
  mount() {
    this.view.innerHTML = `
      <div class="toolbar" data-toolbar>
        <div class="toolbar__search">
          ${icon('search', 'icon-sm')}
          <input type="search" placeholder="Search post text, author or group…" aria-label="Search posts">
        </div>
        ${this.options.toolbar || ''}
        <select data-sort aria-label="Sort posts">
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="engagement">Most engagement</option>
          <option value="reports">Most reported</option>
        </select>
        <span class="tiny muted" data-count></span>
      </div>
      <div data-list></div>
      <div data-bulk></div>`;

    this.listEl = this.view.querySelector('[data-list]');
    this.bulkEl = this.view.querySelector('[data-bulk]');
    this.countEl = this.view.querySelector('[data-count]');

    const searchInput = this.view.querySelector('[data-toolbar] input[type=search]');
    if (searchInput) {
      searchInput.value = this.options.filters.q || '';
      searchInput.addEventListener('input', debounce(() => {
        this.state.q = searchInput.value.trim();
        this.state.page = 1;
        this.load();
      }));
    }
    this.view.querySelector('[data-sort]').addEventListener('change', (event) => {
      this.state.sort = event.target.value;
      this.state.page = 1;
      this.load();
    });

    this.bindListEvents();
    this.load();
  }

  bindListEvents() {
    on(this.listEl, 'change', 'input[type=checkbox][data-id]', (event, checkbox) => {
      const id = Number(checkbox.dataset.id);
      if (checkbox.checked) this.state.selected.add(id);
      else this.state.selected.delete(id);
      this.listEl.querySelector(`[data-card="${id}"]`)?.classList.toggle('is-selected', checkbox.checked);
      this.paintBulk();
    });

    on(this.listEl, 'change', 'input[data-select-all]', (event, checkbox) => {
      this.state.items.forEach((post) => {
        if (checkbox.checked) this.state.selected.add(post.id);
        else this.state.selected.delete(post.id);
      });
      this.listEl.querySelectorAll('input[data-id]').forEach((input) => {
        input.checked = checkbox.checked;
        this.listEl.querySelector(`[data-card="${input.dataset.id}"]`)?.classList.toggle('is-selected', checkbox.checked);
      });
      this.paintBulk();
    });

    on(this.listEl, 'click', '[data-act]', (event, button) => {
      const card = button.closest('[data-card]');
      const id = Number(card?.dataset.card);
      const post = this.state.items.find((item) => item.id === id);
      if (!post) return;
      this.handleAction(button.dataset.act, [post], event);
    });

    on(this.listEl, 'click', '[data-page]', (event, button) => {
      if (button.disabled) return;
      this.state.page = Number(button.dataset.page);
      this.state.selected.clear();
      this.load();
    });

    on(this.listEl, 'click', '[data-retry]', () => this.load());

    on(this.bulkEl, 'click', '[data-bulk-act]', (event, button) => {
      const ids = [...this.state.selected];
      this.handleAction(button.dataset.bulkAct, this.state.items.filter((post) => ids.includes(post.id)), event);
    });
    on(this.bulkEl, 'click', '[data-bulk-clear]', () => {
      this.state.selected.clear();
      this.listEl.querySelectorAll('input[type=checkbox]').forEach((input) => { input.checked = false; });
      this.listEl.querySelectorAll('.is-selected').forEach((card) => card.classList.remove('is-selected'));
      this.paintBulk();
    });
  }

  /* ----------------------------------------------------------------- load */
  buildParams() {
    const { q, sort, page, perPage } = this.state;
    return { ...this.options.filters, q: q || this.options.filters.q || '', sort, page, per_page: perPage };
  }

  async load() {
    this.state.loading = true;
    this.state.error = null;
    this.listEl.innerHTML = skeletonPosts(5);
    this.paintBulk();
    try {
      const data = await this.options.fetch(this.buildParams());
      this.state.items = data.items;
      this.state.total = data.pagination.total;
      this.state.page = data.pagination.page;
      this.state.perPage = data.pagination.per_page;
      this.state.selected.clear();
    } catch (error) {
      this.state.error = error.message;
      this.state.items = [];
    } finally {
      this.state.loading = false;
      this.paint();
    }
  }

  /* ---------------------------------------------------------------- paint */
  paint() {
    if (this.state.error) {
      this.listEl.innerHTML = errorState(this.state.error);
      this.countEl.textContent = '';
      this.paintBulk();
      return;
    }
    if (!this.state.items.length) {
      const empty = this.options.empty || {
        icon: 'inbox', title: 'Nothing here yet',
        message: 'No posts match the current filters.',
        actions: `<button class="btn" data-clear-filters>${icon('refresh', 'icon-sm')} Clear filters</button>`,
      };
      this.listEl.innerHTML = `<div class="card">${emptyState(empty)}</div>`;
      this.listEl.querySelector('[data-clear-filters]')?.addEventListener('click', () => {
        const input = this.view.querySelector('[data-toolbar] input[type=search]');
        if (input) input.value = '';
        this.state.q = '';
        this.options.filters = {};
        this.load();
      });
      this.countEl.textContent = '';
      this.paintBulk();
      return;
    }

    const allSelected = this.state.items.every((post) => this.state.selected.has(post.id));
    const rows = this.state.items.map((post) => this.renderCard(post)).join('');

    this.listEl.innerHTML = `
      ${this.options.selectable ? `
        <div class="row" style="margin-bottom:10px;gap:10px">
          <label class="check"><input type="checkbox" data-select-all ${allSelected ? 'checked' : ''}><span>Select all on this page</span></label>
        </div>` : ''}
      <div class="postlist">${rows}</div>
      ${pager({ page: this.state.page, perPage: this.state.perPage, total: this.state.total })}`;

    const from = (this.state.page - 1) * this.state.perPage + 1;
    const to = Math.min(this.state.total, this.state.page * this.state.perPage);
    this.countEl.textContent = `${from}–${to} of ${this.state.total}`;
    this.paintBulk();
  }

  renderCard(post) {
    const selected = this.state.selected.has(post.id);
    const actions = this.options.actions;
    const isTrash = Boolean(post.deleted_at);

    const actionButtons = actions.map((name) => {
      switch (name) {
        case 'view': return `<button class="btn btn--sm" data-act="view">${icon('eye', 'icon-sm')} View</button>`;
        case 'edit': return `<button class="btn btn--sm" data-act="edit">${icon('edit', 'icon-sm')} Edit</button>`;
        case 'approve': return `<button class="btn btn--sm btn--soft" data-act="approve">${icon('check', 'icon-sm')} Approve</button>`;
        case 'decline': return `<button class="btn btn--sm" data-act="decline">${icon('x', 'icon-sm')} Decline</button>`;
        case 'flag': return `<button class="btn btn--sm" data-act="flag">${icon('flag', 'icon-sm')} Flag</button>`;
        case 'unflag': return `<button class="btn btn--sm" data-act="unflag">${icon('check-circle', 'icon-sm')} Unflag</button>`;
        case 'delete': return `<button class="btn btn--sm" data-act="delete" style="color:var(--danger)">${icon('trash-sm', 'icon-sm')} Delete</button>`;
        case 'restore': return `<button class="btn btn--sm btn--soft" data-act="restore">${icon('undo', 'icon-sm')} Restore</button>`;
        case 'purge': return `<button class="btn btn--sm" data-act="purge" style="color:var(--danger)">${icon('trash-sm', 'icon-sm')} Delete forever</button>`;
        default: return '';
      }
    }).join('');

    const stateClass = isTrash ? 'is-trashed' : `is-${post.state}`;

    return `
      <article class="post ${stateClass} ${selected ? 'is-selected' : ''}" data-card="${post.id}">
        ${this.options.selectable ? `
          <div class="post__select">
            <label class="check"><input type="checkbox" data-id="${post.id}" ${selected ? 'checked' : ''} aria-label="Select post ${post.id}"><span></span></label>
          </div>` : ''}
        <div class="post__body">
          <div class="post__head">
            ${this.avatarHtml(post)}
            <span class="post__author">${esc(post.author_name)}</span>
            ${this.options.showGroup && post.group_name ? `
              <span class="post__sep">·</span>
              <a class="post__group" href="#/posts?group=${post.group_id}" title="${esc(post.group_name)}">${esc(post.group_name)}</a>` : ''}
            <span class="post__sep">·</span>
            <span class="post__time" title="${esc(fullTime(post.created_at))}">${esc(relTime(post.published_at || post.created_at))}</span>
            <div class="post__badges">
              ${typeBadge(post.post_type)}
              ${isTrash ? '<span class="badge badge--trashed"><span class="dot"></span>In trash</span>' : stateBadge(post.state)}
            </div>
          </div>
          <p class="post__msg">${linkify(esc(post.message)) || '<span class="muted">(no text)</span>'}</p>
          ${post.reason ? `<div class="post__reason">${icon('info', 'icon-sm')} ${esc(post.reason)}</div>` : ''}
          <div class="post__meta">
            <span>${icon('heart', 'icon-sm')} ${post.likes}</span>
            <span>${icon('comment', 'icon-sm')} ${post.comments}</span>
            <span>${icon('share', 'icon-sm')} ${post.shares}</span>
            ${post.reports ? `<span class="is-hot">${icon('alert', 'icon-sm')} ${plural(post.reports, 'report')}</span>` : ''}
            ${post.scheduled_for ? `<span>${icon('clock', 'icon-sm')} ${esc(relTime(post.scheduled_for))}</span>` : ''}
          </div>
          ${actionButtons ? `<div class="post__actions">${actionButtons}</div>` : ''}
        </div>
      </article>`;
  }

  avatarHtml(post) {
    const label = (post.author_name || '?').split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase();
    const color = [...(post.author_name || '')].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 7;
    return `<span class="avatar avatar--sm" data-c="${color}" title="${esc(post.author_name)}">${esc(label)}</span>`;
  }

  paintBulk() {
    const count = this.state.selected.size;
    if (!count || !this.options.selectable) { this.bulkEl.innerHTML = ''; return; }
    const buttons = this.options.bulkActions.map((action) => `
      <button class="btn btn--sm ${action.danger ? 'btn--danger' : ''}" data-bulk-act="${action.action}">
        ${icon(action.icon, 'icon-sm')} ${esc(action.label)}
      </button>`).join('');
    this.bulkEl.innerHTML = `
      <div class="bulkbar">
        <span class="bulkbar__count"><b>${count}</b> ${count === 1 ? 'post' : 'posts'} selected</span>
        ${buttons}
        <span class="spacer"></span>
        <button class="btn btn--sm btn--ghost" data-bulk-clear>${icon('x', 'icon-sm')} Clear</button>
      </div>`;
  }

  /* ----------------------------------------------------------- mutations */
  /**
   * Apply an action optimistically: the UI updates immediately, the request
   * runs in the background, and a failure (or Undo) rolls everything back.
   */
  async handleAction(action, posts, event) {
    const ids = posts.map((post) => post.id);
    if (!ids.length) return;

    if (action === 'view') { openPostDrawer(posts[0], () => this.load()); return; }
    if (action === 'edit') { openPostEditor(posts[0], store.groups, () => this.load()); return; }

    const undoable = ['delete', 'decline'].includes(action);
    const snapshot = {
      items: [...this.state.items],
      selected: new Set(this.state.selected),
    };

    const labels = {
      delete: 'Moved to trash', decline: 'Declined', approve: 'Approved', flag: 'Flagged',
      unflag: 'Unflagged', restore: 'Restored', purge: 'Deleted forever',
    };

    if (undoable) {
      ids.forEach((id) => {
        const card = this.listEl.querySelector(`[data-card="${id}"]`);
        card?.classList.add('is-leaving');
      });
      this.state.items = this.state.items.filter((post) => !ids.includes(post.id));
      this.state.total = Math.max(0, this.state.total - ids.length);
      ids.forEach((id) => this.state.selected.delete(id));
      setTimeout(() => this.paint(), 180);
      store.nudge(this.trashDelta(action, ids.length));
    }

    try {
      const result = await api.bulk({ ids, action });
      const message = result.processed === 1
        ? posts[0].message.slice(0, 70)
        : `${result.processed} posts affected`;
      toast({
        kind: undoable ? 'success' : 'info',
        title: `${labels[action] || action} · ${plural(result.processed, 'post')}`,
        text: message,
        action: undoable ? { label: 'Undo', onClick: () => this.undo(ids) } : null,
      });
      if (!undoable) await this.load();
      store.invalidateStats();
      store.loadStats(true).catch(() => {});
    } catch (error) {
      // Roll the optimistic change back and show the truth from the server.
      this.state.items = snapshot.items;
      this.state.selected = snapshot.selected;
      this.paint();
      toast({ kind: 'error', title: `Could not ${action} those posts`, text: error.message });
    }
  }

  trashDelta(action, count) {
    const fromTrash = this.options.trashView;
    if (fromTrash) return { trashed: -count };
    if (action === 'decline') {
      const pending = this.state.items.filter((post) => post.state === 'pending').length;
      return { pending: -pending, trashed: count };
    }
    return { live: -count, trashed: count };
  }

  async undo(ids) {
    try {
      await api.bulk({ ids, action: 'restore' });
      toast({ kind: 'success', title: 'Restored', text: `${plural(ids.length, 'post')} put back.` });
      store.invalidateStats();
      store.loadStats(true).catch(() => {});
      await this.load();
    } catch (error) {
      toast({ kind: 'error', title: 'Undo failed', text: error.message });
    }
  }
}

/** Convenience: a card + heading wrapper used by the simple queue pages. */
export function pageHeader({ title, description, actions = '' }) {
  return html(`
    <div class="page__head">
      <div>
        <h1>${esc(title)}</h1>
        <p class="page__desc">${esc(description)}</p>
      </div>
      ${actions ? `<div class="page__actions">${actions}</div>` : ''}
    </div>`);
}
