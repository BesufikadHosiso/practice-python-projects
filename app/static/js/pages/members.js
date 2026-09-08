/** Members — the spam watch-list, bans and per-author sweeps. */
import { api } from '../api.js';
import { store } from '../store.js';
import {
  confirmDialog, debounce, emptyState, esc, errorState, formData, icon, openModal,
  plural, relTime, toast,
} from '../ui.js';

export async function render(view) {
  const groups = await store.loadGroups();

  view.innerHTML = `
    <div class="page__head">
      <div>
        <h1>${icon('ban')} Members</h1>
        <p class="page__desc">Everyone who has posted in your groups, ranked by how much of their content you've had to remove. Ban a member to sweep every live post they made.</p>
      </div>
      <div class="page__actions">
        <button class="btn btn--primary" data-new>${icon('plus', 'icon-sm')} Add to watch-list</button>
      </div>
    </div>
    <div class="toolbar">
      <div class="toolbar__search">${icon('search', 'icon-sm')}<input type="search" placeholder="Search members…" aria-label="Search members"></div>
      <select data-group-filter aria-label="Filter by group">
        <option value="">All groups</option>
        ${groups.map((group) => `<option value="${group.id}">${esc(group.name)}</option>`).join('')}
      </select>
      <span class="spacer"></span>
      <span class="tiny muted" data-count></span>
    </div>
    <div class="card"><div data-list></div></div>`;

  const listEl = view.querySelector('[data-list]');
  const countEl = view.querySelector('[data-count]');
  let query = '';
  let groupId = '';

  const paint = async () => {
    listEl.innerHTML = `<div style="padding:10px">${Array.from({ length: 7 }, () => '<div class="skeleton sk-line" style="height:44px;margin-bottom:8px"></div>').join('')}</div>`;
    try {
      const { items } = await api.authors({ q: query, group_id: groupId || undefined });
      countEl.textContent = plural(items.length, 'member');
      if (!items.length) {
        listEl.innerHTML = emptyState({
          icon: 'users', title: query || groupId ? 'No members match' : 'Nobody has posted yet',
          message: query || groupId
            ? 'Try a different search or clear the group filter.'
            : 'Members appear here as soon as their posts are synced in.',
          actions: '<a class="btn btn--primary" href="#/groups">Sync your groups</a>',
        });
        return;
      }
      listEl.innerHTML = items.map(row).join('');
    } catch (error) {
      listEl.innerHTML = errorState(error.message);
      listEl.querySelector('[data-retry]').addEventListener('click', paint);
    }
  };

  function row(member) {
    const riskColour = member.risk_score >= 66 ? 'var(--danger)' : member.risk_score >= 33 ? 'var(--warn)' : 'var(--success)';
    return `
      <div class="member" data-member="${member.id}">
        <span class="avatar" data-c="${[...(member.name || '')].reduce((sum, c) => sum + c.charCodeAt(0), 0) % 7}">${esc(member.avatar_seed)}</span>
        <div style="flex:1;min-width:0">
          <div class="row" style="gap:7px">
            <span class="strong truncate">${esc(member.name)}</span>
            ${member.is_banned ? '<span class="badge badge--flagged"><span class="dot"></span>Banned</span>' : ''}
          </div>
          <div class="tiny muted truncate">${esc(member.handle)}${member.group_name ? ` · ${esc(member.group_name)}` : ''} · joined ${esc(relTime(member.joined_at))}</div>
        </div>
        <div class="num" style="min-width:64px">
          <div class="strong">${member.posts}</div>
          <div class="tiny muted">posts</div>
        </div>
        <div class="num" style="min-width:74px">
          <div class="strong" style="color:${member.removed ? 'var(--danger)' : 'var(--text-3)'}">${member.removed}</div>
          <div class="tiny muted">removed</div>
        </div>
        <div style="min-width:56px">
          <div class="member__risk"><i style="width:${member.risk_score}%;background:${riskColour}"></i></div>
          <div class="tiny muted" style="margin-top:3px">${member.risk_score} risk</div>
        </div>
        <div class="row" style="gap:5px">
          <a class="btn btn--sm btn--ghost btn--icon" href="#/posts?q=${encodeURIComponent(member.name)}" title="See their posts">${icon('eye', 'icon-sm')}</a>
          <button class="btn btn--sm btn--ghost btn--icon" data-edit title="Edit">${icon('edit', 'icon-sm')}</button>
          <button class="btn btn--sm ${member.is_banned ? '' : 'btn--soft'}" data-ban title="${member.is_banned ? 'Unban' : 'Ban and remove posts'}">${icon('ban', 'icon-sm')}</button>
        </div>
      </div>`;
  }

  view.querySelector('input[type=search]').addEventListener('input', debounce((event) => {
    query = event.target.value.trim();
    paint();
  }));
  view.querySelector('[data-group-filter]').addEventListener('change', (event) => {
    groupId = event.target.value;
    paint();
  });
  view.querySelector('[data-new]').addEventListener('click', () => openMemberDialog(null, groups, paint));

  listEl.addEventListener('click', async (event) => {
    const rowEl = event.target.closest('[data-member]');
    if (!rowEl) return;
    const id = Number(rowEl.dataset.member);

    if (event.target.closest('[data-edit]')) {
      const { items } = await api.authors();
      openMemberDialog(items.find((member) => member.id === id), groups, paint);
      return;
    }
    if (event.target.closest('[data-ban]')) {
      const { items } = await api.authors();
      const member = items.find((item) => item.id === id);
      if (!member) return;
      if (!member.is_banned) {
        const ok = await confirmDialog({
          title: `Ban ${member.name}?`,
          message: 'Every live post they made across all your groups will be moved to the trash, and future posts will be caught by your banned-member rule.',
          confirmLabel: 'Ban and remove posts',
          danger: true,
          details: `They currently have <b>${member.posts}</b> post(s).`,
        });
        if (!ok) return;
      }
      try {
        const result = await api.banAuthor(id);
        toast({
          kind: result.is_banned ? 'success' : 'info',
          title: result.is_banned ? `Banned ${member.name}` : `Unbanned ${member.name}`,
          text: result.swept ? `${plural(result.swept, 'post')} moved to the trash.` : 'No posts were affected.',
        });
        store.invalidateStats();
        store.loadStats(true).catch(() => {});
        await paint();
      } catch (error) {
        toast({ kind: 'error', title: 'Could not update the member', text: error.message });
      }
    }
  });

  await paint();
}

function openMemberDialog(member, groups, onSaved) {
  const editing = Boolean(member?.id);
  const body = `
    <form id="member-form" novalidate>
      <div class="field">
        <label for="mf-name">Name</label>
        <input id="mf-name" name="name" type="text" value="${esc(member?.name || '')}" placeholder="Spam Bot 3000" minlength="2" required>
        <span class="err">At least 2 characters.</span>
      </div>
      <div class="field">
        <label for="mf-handle">Handle</label>
        <input id="mf-handle" name="handle" type="text" value="${esc(member?.handle || '')}" placeholder="@spam-bot-3000">
      </div>
      <div class="form__row">
        <div class="field">
          <label for="mf-group">Primary group</label>
          <select id="mf-group" name="group_id">
            <option value="">Not set</option>
            ${groups.map((group) => `<option value="${group.id}" ${member?.group_id === group.id ? 'selected' : ''}>${esc(group.name)}</option>`).join('')}
          </select>
        </div>
        <div class="field">
          <label for="mf-risk">Risk score (0–100)</label>
          <input id="mf-risk" name="risk_score" type="number" min="0" max="100" value="${member?.risk_score ?? 0}">
        </div>
      </div>
      <label class="check"><input type="checkbox" name="is_banned" ${member?.is_banned ? 'checked' : ''}><span>Banned from all groups</span></label>
    </form>`;

  const { root, close } = openModal({
    title: editing ? 'Edit member' : 'Add to watch-list',
    body,
    size: 'sm',
    footer: `<button class="btn" data-cancel>Cancel</button>
             <button class="btn btn--primary" data-save>${icon('check', 'icon-sm')} ${editing ? 'Save' : 'Add member'}</button>`,
  });

  const form = root.querySelector('#member-form');
  root.querySelector('[data-cancel]').addEventListener('click', close);
  root.querySelector('[data-save]').addEventListener('click', async () => {
    const data = formData(form);
    const nameField = form.name.closest('.field');
    nameField.classList.toggle('has-error', data.name.trim().length < 2);
    if (data.name.trim().length < 2) return;

    const payload = {
      name: data.name.trim(),
      handle: data.handle.trim() || null,
      group_id: data.group_id ? Number(data.group_id) : null,
      risk_score: Number(data.risk_score || 0),
      is_banned: Boolean(data.is_banned),
    };
    const button = root.querySelector('[data-save]');
    button.disabled = true;
    try {
      if (editing) await api.updateAuthor(member.id, payload);
      else await api.createAuthor(payload);
      toast({ kind: 'success', title: editing ? 'Member saved' : 'Member added' });
      close();
      onSaved?.();
    } catch (error) {
      button.disabled = false;
      toast({ kind: 'error', title: 'Could not save the member', text: error.message });
    }
  });
}
