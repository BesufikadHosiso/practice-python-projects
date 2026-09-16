/** Flagged & reported posts. */
import { api } from '../api.js';
import { store } from '../store.js';
import { esc, icon, plural, toast } from '../ui.js';
import { PostList, pageHeader } from './_postList.js';

export async function render(view, { params }) {
  const groups = await store.loadGroups();
  const groupId = params.get('group') || '';

  view.innerHTML = '';
  view.append(pageHeader({
    title: 'Flagged & reported',
    description: 'Posts members reported, or that one of your cleanup rules flagged for review. Sorted by report count so the worst offenders come first.',
    actions: `<a class="btn btn--danger" href="#/cleaner?state=flagged">${icon('broom', 'icon-sm')} Delete all flagged</a>`,
  }));

  const container = document.createElement('div');
  view.append(container);

  const list = new PostList(container, {
    fetch: (queryParams) => api.posts({ ...queryParams, state: 'flagged', sort: queryParams.sort === 'newest' ? 'reports' : queryParams.sort }),
    filters: { group_id: groupId || undefined },
    actions: ['view', 'edit', 'approve', 'unflag', 'delete'],
    bulkActions: [
      { action: 'delete', label: 'Delete', icon: 'trash-sm', danger: true },
      { action: 'approve', label: 'Dismiss report', icon: 'check' },
      { action: 'flag', label: 'Keep flagged', icon: 'flag' },
    ],
    empty: {
      icon: 'shield',
      title: 'No reported content',
      message: 'Nothing has been reported or flagged. Your groups are behaving — for now.',
      success: true,
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

  view.querySelector('[data-bulk-flagged]')?.addEventListener('click', async () => {
    try {
      const result = await api.bulkFilter({
        filters: { states: ['flagged'] }, action: 'delete', name: 'Delete all flagged',
      });
      toast({ kind: 'success', title: `Deleted ${plural(result.processed, 'post')}`, text: 'Everything is recoverable from the trash.' });
      store.invalidateStats();
      list.load();
    } catch (error) {
      toast({ kind: 'error', title: 'Bulk delete failed', text: error.message });
    }
  });
}
