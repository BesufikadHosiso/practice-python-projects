/** Trash — soft-deleted posts, restore or purge. */
import { api } from '../api.js';
import { store } from '../store.js';
import { confirmDialog, esc, icon, plural, toast } from '../ui.js';
import { PostList, pageHeader } from './_postList.js';

export async function render(view, { params }) {
  const groups = await store.loadGroups();
  const groupId = params.get('group') || '';

  view.innerHTML = '';
  view.append(pageHeader({
    title: 'Trash',
    description: 'Everything you delete lands here first and keeps its original state, so a mistaken bulk delete is one click from undone. Purging is permanent.',
    actions: `
      <button class="btn" data-restore-all>${icon('undo', 'icon-sm')} Restore everything</button>
      <button class="btn btn--danger" data-empty>${icon('trash-sm', 'icon-sm')} Empty trash</button>`,
  }));

  const container = document.createElement('div');
  view.append(container);

  const list = new PostList(container, {
    fetch: (queryParams) => api.trash(queryParams),
    filters: { group_id: groupId || undefined },
    trashView: true,
    actions: ['view', 'restore', 'purge'],
    bulkActions: [
      { action: 'restore', label: 'Restore', icon: 'undo' },
      { action: 'purge', label: 'Delete forever', icon: 'trash-sm', danger: true },
    ],
    empty: {
      icon: 'check-circle',
      title: 'The trash is empty',
      message: 'Nothing has been deleted, or everything has already been purged.',
      success: true,
      actions: '<a class="btn btn--primary" href="#/posts">Browse live posts</a>',
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

  view.querySelector('[data-restore-all]').addEventListener('click', async () => {
    const ids = list.state.items.map((post) => post.id);
    if (!ids.length) {
      toast({ kind: 'info', title: 'Nothing to restore', text: 'This page of the trash is empty.' });
      return;
    }
    try {
      const result = await api.bulk({ ids, action: 'restore' });
      toast({ kind: 'success', title: `Restored ${plural(result.processed, 'post')}`, text: 'They are back in their original state.' });
      store.invalidateStats();
      store.loadStats(true).catch(() => {});
      await list.load();
    } catch (error) {
      toast({ kind: 'error', title: 'Restore failed', text: error.message });
    }
  });

  view.querySelector('[data-empty]').addEventListener('click', async () => {
    const ok = await confirmDialog({
      title: 'Empty the trash?',
      message: 'Every post in the trash will be permanently deleted from the database. This cannot be undone.',
      confirmLabel: 'Empty trash',
      danger: true,
      details: `<b>${list.state.total}</b> post(s) will be removed forever.`,
    });
    if (!ok) return;
    try {
      const result = await api.emptyTrash({ group_id: groupId || undefined });
      toast({ kind: 'success', title: `Purged ${plural(result.purged, 'post')}`, text: 'Trash is empty.' });
      store.invalidateStats();
      store.loadStats(true).catch(() => {});
      await list.load();
    } catch (error) {
      toast({ kind: 'error', title: 'Could not empty the trash', text: error.message });
    }
  });
}
