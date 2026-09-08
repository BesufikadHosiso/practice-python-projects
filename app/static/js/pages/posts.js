/** All posts — the full firehose with every filter exposed. */
import { api } from '../api.js';
import { store } from '../store.js';
import { esc, icon, toast } from '../ui.js';
import { PostList, pageHeader } from './_postList.js';
import { openPostEditor } from '../components/postDialogs.js';

const TYPES = ['text', 'photo', 'link', 'video', 'poll', 'live', 'event'];

export async function render(view, { params }) {
  const groups = await store.loadGroups();
  const initial = {
    group: params.get('group') || '',
    state: params.get('state') || '',
    type: params.get('type') || '',
    q: params.get('q') || '',
    link: params.get('link') || '',
  };

  view.innerHTML = '';
  view.append(pageHeader({
    title: 'All posts',
    description: 'Every live post across your connected groups. Filter it down, then bulk-delete whatever shouldn\'t be there.',
    actions: `<button class="btn btn--primary" data-add-post>${icon('plus', 'icon-sm')} Add post</button>`,
  }));

  const container = document.createElement('div');
  view.append(container);

  const list = new PostList(container, {
    fetch: (queryParams) => api.posts(queryParams),
    filters: {
      group_id: initial.group || undefined,
      state: initial.state || undefined,
      post_type: initial.type || undefined,
      q: initial.q || undefined,
      contains_link: initial.link || undefined,
    },
    actions: ['view', 'edit', 'flag', 'delete'],
    bulkActions: [
      { action: 'delete', label: 'Delete', icon: 'trash-sm', danger: true },
      { action: 'flag', label: 'Flag', icon: 'flag' },
      { action: 'approve', label: 'Approve', icon: 'check' },
    ],
    empty: {
      icon: 'posts',
      title: 'No posts match those filters',
      message: 'Try widening the search, or sync your groups to pull in the latest content.',
    },
    toolbar: `
      <select data-group-filter aria-label="Filter by group">
        <option value="">All groups</option>
        ${groups.map((group) => `<option value="${group.id}" ${String(group.id) === initial.group ? 'selected' : ''}>${esc(group.name)}</option>`).join('')}
      </select>
      <select data-state-filter aria-label="Filter by state">
        <option value="">Any state</option>
        <option value="published" ${initial.state === 'published' ? 'selected' : ''}>Published</option>
        <option value="pending" ${initial.state === 'pending' ? 'selected' : ''}>Pending</option>
        <option value="flagged" ${initial.state === 'flagged' ? 'selected' : ''}>Flagged</option>
        <option value="scheduled" ${initial.state === 'scheduled' ? 'selected' : ''}>Scheduled</option>
      </select>
      <select data-type-filter aria-label="Filter by post type">
        <option value="">Any type</option>
        ${TYPES.map((type) => `<option value="${type}" ${initial.type === type ? 'selected' : ''}>${type[0].toUpperCase() + type.slice(1)}</option>`).join('')}
      </select>
      <select data-link-filter aria-label="Filter by links">
        <option value="">Links: any</option>
        <option value="true" ${initial.link === 'true' ? 'selected' : ''}>With a link</option>
        <option value="false" ${initial.link === 'false' ? 'selected' : ''}>No link</option>
      </select>`,
  });

  const syncFilter = (selector, key) => {
    container.querySelector(selector)?.addEventListener('change', (event) => {
      list.options.filters[key] = event.target.value || undefined;
      list.state.page = 1;
      list.load();
    });
  };
  syncFilter('[data-group-filter]', 'group_id');
  syncFilter('[data-state-filter]', 'state');
  syncFilter('[data-type-filter]', 'post_type');
  syncFilter('[data-link-filter]', 'contains_link');

  view.querySelector('[data-add-post]').addEventListener('click', async () => {
    openPostEditor(null, groups, () => {
      store.invalidateStats();
      list.load();
    });
  });
}
