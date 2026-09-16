/** Pending queue — posts waiting for moderator approval. */
import { api } from '../api.js';
import { store } from '../store.js';
import { esc, icon, plural, toast } from '../ui.js';
import { PostList, pageHeader } from './_postList.js';

export async function render(view, { params }) {
  const groups = await store.loadGroups();
  const groupId = params.get('group') || '';

  view.innerHTML = '';
  view.append(pageHeader({
    title: 'Pending queue',
    description: 'Every post held for approval across your groups. Approve, decline or delete in bulk — deletions land in the trash so nothing is ever lost by accident.',
    actions: `
      <button class="btn" data-approve-all>${icon('check', 'icon-sm')} Approve everything here</button>
      <a class="btn btn--danger" href="#/cleaner?state=pending">${icon('broom', 'icon-sm')} Bulk clean</a>`,
  }));

  const container = document.createElement('div');
  view.append(container);

  const list = new PostList(container, {
    fetch: (queryParams) => api.posts({ ...queryParams, state: 'pending' }),
    filters: { group_id: groupId || undefined },
    actions: ['view', 'edit', 'approve', 'decline', 'delete'],
    bulkActions: [
      { action: 'approve', label: 'Approve', icon: 'check' },
      { action: 'decline', label: 'Decline', icon: 'x', danger: true },
      { action: 'delete', label: 'Delete', icon: 'trash-sm', danger: true },
      { action: 'flag', label: 'Flag', icon: 'flag' },
    ],
    empty: {
      icon: 'check-circle',
      title: 'The queue is empty',
      message: 'Nothing is waiting on you right now. New posts from Facebook will land here as soon as you sync.',
      success: true,
      actions: '<button class="btn btn--primary" data-sync-now>Sync groups now</button>',
    },
    toolbar: groups.length ? `
      <select data-group-filter aria-label="Filter by group">
        <option value="">All groups</option>
        ${groups.map((group) => `<option value="${group.id}" ${String(group.id) === groupId ? 'selected' : ''}>${esc(group.name)}</option>`).join('')}
      </select>` : '',
  });

  container.querySelector('[data-group-filter]')?.addEventListener('change', (event) => {
    list.options.filters.group_id = event.target.value || undefined;
    list.state.page = 1;
    list.load();
  });

  container.querySelector('[data-sync-now]')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      let created = 0;
      for (const group of groups.filter((item) => item.connected)) {
        created += (await api.syncGroup(group.id)).created;
      }
      toast({ kind: 'success', title: 'Sync complete', text: `${plural(created, 'new post')} pulled in.` });
      store.invalidateStats();
      list.load();
    } catch (error) {
      toast({ kind: 'error', title: 'Sync failed', text: error.message });
    } finally {
      button.disabled = false;
    }
  });

  view.querySelector('[data-approve-all]').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const ids = list.state.items.map((post) => post.id);
    if (!ids.length) {
      toast({ kind: 'info', title: 'Nothing to approve', text: 'This page of the queue is already empty.' });
      return;
    }
    button.disabled = true;
    try {
      const result = await api.bulk({ ids, action: 'approve' });
      toast({ kind: 'success', title: `Approved ${plural(result.processed, 'post')}`, text: 'They are live in their groups now.' });
      store.invalidateStats();
      store.loadStats(true).catch(() => {});
      await list.load();
    } catch (error) {
      toast({ kind: 'error', title: 'Could not approve', text: error.message });
    } finally {
      button.disabled = false;
    }
  });
}
