/** Run history — every bulk sweep this workspace has executed. */
import { api } from '../api.js';
import {
  compactNumber, confirmDialog, emptyState, esc, errorState, fullTime, icon,
  plural, relTime, skeletonTable, toast,
} from '../ui.js';

export async function render(view) {
  view.innerHTML = `
    <div class="page__head">
      <div>
        <h1>${icon('job')} Run history</h1>
        <p class="page__desc">Every bulk sweep, rule run and selection delete this workspace has performed, with how many posts each one touched.</p>
      </div>
      <div class="page__actions">
        <button class="btn" data-refresh>${icon('refresh', 'icon-sm')} Refresh</button>
        <button class="btn btn--danger" data-clear>${icon('trash-sm', 'icon-sm')} Clear history</button>
      </div>
    </div>
    <div data-list>${skeletonTable(7)}</div>`;

  const listEl = view.querySelector('[data-list]');

  const paint = async () => {
    listEl.innerHTML = skeletonTable(5);
    try {
      const { items } = await api.jobs();
      if (!items.length) {
        listEl.innerHTML = `<div class="card">${emptyState({
          icon: 'job', title: 'No runs yet',
          message: 'Run a bulk sweep or one of your cleanup rules and it will be recorded here.',
          actions: '<a class="btn btn--primary" href="#/cleaner">Open the bulk cleaner</a>',
        })}</div>`;
        return;
      }
      const totalProcessed = items.reduce((sum, job) => sum + (job.dry_run ? 0 : job.processed), 0);
      listEl.innerHTML = `
        <div class="grid grid--stats" style="margin-bottom:16px">
          <div class="stat" style="--accent:var(--primary)">
            <div class="stat__label">${icon('job', 'icon-sm')} Total runs</div>
            <div class="stat__value">${items.length}</div>
            <div class="stat__meta">${items.filter((job) => job.dry_run).length} were previews</div>
          </div>
          <div class="stat" style="--accent:var(--danger)">
            <div class="stat__label">${icon('trash-sm', 'icon-sm')} Posts processed</div>
            <div class="stat__value">${compactNumber(totalProcessed)}</div>
            <div class="stat__meta">Across every action type</div>
          </div>
          <div class="stat" style="--accent:var(--success)">
            <div class="stat__label">${icon('clock', 'icon-sm')} Avg. duration</div>
            <div class="stat__value">${Math.round(items.reduce((sum, job) => sum + job.duration_ms, 0) / items.length)}<span style="font-size:14px;color:var(--text-3)">ms</span></div>
            <div class="stat__meta">Server-side sweep time</div>
          </div>
        </div>
        <div class="card">
          <table class="table table--responsive">
            <thead><tr>
              <th>Run</th><th>Action</th><th class="num">Matched</th>
              <th class="num">Processed</th><th class="num">Took</th><th>When</th><th></th>
            </tr></thead>
            <tbody>
              ${items.map((job) => `
                <tr data-job="${job.id}">
                  <td data-label="Run">
                    <div class="strong">${esc(job.name)} ${job.dry_run ? '<span class="badge badge--off">preview</span>' : ''}</div>
                    <div class="tiny muted">${job.group_ids.length ? `${job.group_ids.length} group(s)` : 'All groups'}${filterSummary(job.filters)}</div>
                  </td>
                  <td data-label="Action"><span class="badge badge--${job.action === 'delete' || job.action === 'purge' ? 'flagged' : 'primary'}">${esc(job.action)}</span></td>
                  <td data-label="Matched" class="num">${job.matched}</td>
                  <td data-label="Processed" class="num strong">${job.dry_run ? '—' : job.processed}</td>
                  <td data-label="Took" class="num mono">${job.duration_ms}ms</td>
                  <td data-label="When"><span title="${esc(fullTime(job.created_at))}">${esc(relTime(job.created_at))}</span></td>
                  <td data-label="" class="num">
                    <button class="btn btn--sm btn--ghost btn--icon" data-delete aria-label="Delete run">${icon('trash-sm', 'icon-sm')}</button>
                  </td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>`;
    } catch (error) {
      listEl.innerHTML = `<div class="card">${errorState(error.message)}</div>`;
      listEl.querySelector('[data-retry]').addEventListener('click', paint);
    }
  };

  view.querySelector('[data-refresh]').addEventListener('click', paint);

  view.querySelector('[data-clear]').addEventListener('click', async () => {
    const ok = await confirmDialog({
      title: 'Clear the run history?',
      message: 'This removes the audit record of past sweeps. It does not touch any posts.',
      confirmLabel: 'Clear history',
      danger: true,
    });
    if (!ok) return;
    try {
      const result = await api.clearJobs();
      toast({ kind: 'success', title: `Cleared ${plural(result.removed, 'run')}` });
      await paint();
    } catch (error) {
      toast({ kind: 'error', title: 'Could not clear history', text: error.message });
    }
  });

  listEl.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-delete]');
    if (!button) return;
    const id = Number(button.closest('[data-job]').dataset.job);
    try {
      await api.deleteJob(id);
      toast({ kind: 'success', title: 'Run removed' });
      await paint();
    } catch (error) {
      toast({ kind: 'error', title: 'Could not delete the run', text: error.message });
    }
  });

  await paint();
}

function filterSummary(filters) {
  if (!filters || typeof filters !== 'object') return '';
  const bits = [];
  if (filters.q) bits.push(`"${filters.q}"`);
  if (filters.contains_link) bits.push('has link');
  if (filters.older_than_days != null) bits.push(`>${filters.older_than_days}d`);
  if (filters.min_reports != null) bits.push(`≥${filters.min_reports} reports`);
  if (filters.max_likes != null) bits.push(`≤${filters.max_likes} likes`);
  if (filters.states?.length) bits.push(filters.states.join('/'));
  if (filters.ids?.length) bits.push(`${filters.ids.length} selected`);
  return bits.length ? ` · ${bits.join(' · ')}` : '';
}
