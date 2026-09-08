/**
 * Bulk cleaner — the centrepiece.
 * Build a filter, preview exactly what it matches, then sweep every group at once.
 */
import { api } from '../api.js';
import { store } from '../store.js';
import {
  confirmDialog, debounce, esc, icon, linkify, plural, relTime, toast, typeBadge,
} from '../ui.js';

const PRESETS = [
  {
    id: 'links', name: 'Anything with an external link', icon: 'link',
    filters: { contains_link: true },
    blurb: 'The single biggest source of drive-by advertising.',
  },
  {
    id: 'reported', name: 'Reported by 1+ members', icon: 'flag',
    filters: { min_reports: 1 },
    blurb: 'Your members already told you these are junk.',
  },
  {
    id: 'old', name: 'Older than 90 days', icon: 'clock',
    filters: { older_than_days: 90 },
    blurb: 'Archive history without nuking the search index.',
  },
  {
    id: 'zero', name: 'Zero reactions', icon: 'heart',
    filters: { max_likes: 0 },
    blurb: 'Posts nobody engaged with are usually bots.',
  },
  {
    id: 'pending-week', name: 'Pending for over 7 days', icon: 'inbox',
    filters: { states: ['pending'], older_than_days: 7 },
    blurb: 'Stale moderation queue items nobody will ever see.',
  },
  {
    id: 'keyword', name: 'Keyword: "DM me"', icon: 'search',
    filters: { q: 'dm me' },
    blurb: 'Funnel-out solicitation, comma-separate for more terms.',
  },
];

let state = {
  filters: { group_ids: [], states: [], post_types: [], q: '', contains_link: null, older_than_days: null, min_reports: null, max_likes: null },
  preview: null,
  loading: false,
  action: 'delete',
};

export async function render(view, { params }) {
  const groups = await store.loadGroups();
  const preState = params.get('state');
  if (preState) state = { ...state, filters: { ...state.filters, states: [preState] } };

  view.innerHTML = `
    <div class="page__head">
      <div>
        <h1>${icon('broom')} Bulk cleaner</h1>
        <p class="page__desc">Combine filters to describe exactly what should go, preview the matches, then run the sweep across every selected group. Deletions go to the trash first.</p>
      </div>
    </div>

    <div class="callout callout--info" style="margin-bottom:18px">
      ${icon('info', 'icon-sm')}
      <div class="callout__body">
        <b>Safe by default.</b> Every sweep is previewed before it runs, and every deletion is reversible from
        <a href="#/trash">the trash</a>. Use <b>Delete forever</b> only when you mean it.
      </div>
    </div>

    <div class="grid grid--2" style="align-items:start">
      <div class="card">
        <div class="card__head"><div><h3>${icon('filter', 'icon-sm')} Build your filter</h3></div></div>
        <div class="card__body">
          <div class="field">
            <label>Groups</label>
            ${groups.length ? `<div class="pill-group" data-groups>
              <button type="button" class="chip" data-group="" aria-pressed="true">All groups</button>
              ${groups.map((group) => `<button type="button" class="chip" data-group="${group.id}" aria-pressed="false">${esc(group.name)}</button>`).join('')}
            </div>` : '<p class="muted small">No groups connected yet.</p>'}
          </div>

          <div class="field">
            <label>Post states</label>
            <div class="pill-group" data-states>
              ${['published', 'pending', 'flagged', 'scheduled'].map((value) => `
                <button type="button" class="chip" data-state="${value}" aria-pressed="${state.filters.states.includes(value)}">${value[0].toUpperCase() + value.slice(1)}</button>`).join('')}
            </div>
          </div>

          <div class="field">
            <label>Post types</label>
            <div class="pill-group" data-types>
              ${['text', 'photo', 'link', 'video', 'poll', 'live', 'event'].map((value) => `
                <button type="button" class="chip" data-type="${value}" aria-pressed="false">${value[0].toUpperCase() + value.slice(1)}</button>`).join('')}
            </div>
          </div>

          <div class="field">
            <label for="cl-q">Text contains</label>
            <input id="cl-q" type="search" placeholder="crypto, dm me, whatsapp…" value="${esc(state.filters.q)}">
            <span class="hint">Matched against the post text, author name and group name.</span>
          </div>

          <div class="form__row">
            <label class="check" style="margin-top:6px">
              <input type="checkbox" data-has-link>
              <span>Only posts containing a link</span>
            </label>
            <div class="field" style="margin-bottom:0">
              <label for="cl-age">Older than (days)</label>
              <input id="cl-age" type="number" min="0" max="3650" placeholder="e.g. 90" value="${state.filters.older_than_days ?? ''}">
            </div>
          </div>

          <div class="form__row" style="margin-top:14px">
            <div class="field" style="margin-bottom:0">
              <label for="cl-reports">At least N reports</label>
              <input id="cl-reports" type="number" min="0" placeholder="e.g. 3" value="${state.filters.min_reports ?? ''}">
            </div>
            <div class="field" style="margin-bottom:0">
              <label for="cl-likes">At most N reactions</label>
              <input id="cl-likes" type="number" min="0" placeholder="e.g. 0" value="${state.filters.max_likes ?? ''}">
            </div>
          </div>

          <div class="divider"></div>

          <div class="field">
            <label>Quick presets</label>
            <div class="grid" style="gap:8px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">
              ${PRESETS.map((preset) => `
                <button type="button" class="quickaction" data-preset="${preset.id}" title="${esc(preset.blurb)}">
                  <span class="quickaction__icon">${icon(preset.icon)}</span>
                  <span><b>${esc(preset.name)}</b><span>${esc(preset.blurb)}</span></span>
                </button>`).join('')}
            </div>
          </div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card__head"><div><h3>${icon('eye', 'icon-sm')} Live preview</h3><span class="sub">Updates as you change the filter</span></div></div>
          <div class="card__body" data-preview></div>
        </div>

        <div class="card">
          <div class="card__head"><div><h3>${icon('play', 'icon-sm')} Run the sweep</h3></div></div>
          <div class="card__body">
            <div class="field">
              <label for="cl-name">Name this run</label>
              <input id="cl-name" type="text" value="Manual sweep" placeholder="Shows up in the run history">
            </div>
            <div class="field">
              <label for="cl-action">Action</label>
              <select id="cl-action">
                <option value="delete">Move to trash (recoverable)</option>
                <option value="flag">Flag for review</option>
                <option value="approve">Approve / publish</option>
                <option value="decline">Decline (trash it)</option>
                <option value="purge">Delete forever</option>
              </select>
            </div>
            <button class="btn btn--danger btn--lg btn--block" data-run>${icon('broom', 'icon-sm')} Run sweep</button>
            <p class="tiny muted" style="text-align:center;margin-top:9px">A dry run always happens first — you'll confirm before anything changes.</p>
          </div>
        </div>
      </div>
    </div>`;

  const previewEl = view.querySelector('[data-preview]');
  const runPreview = debounce(() => loadPreview(previewEl), 320);

  /* ---- filter wiring ---- */
  const paintChips = () => {
    view.querySelectorAll('[data-group]').forEach((chip) => {
      const value = chip.dataset.group;
      const all = state.filters.group_ids.length === 0;
      chip.setAttribute('aria-pressed', String(value === '' ? all : state.filters.group_ids.includes(Number(value))));
    });
    view.querySelectorAll('[data-state]').forEach((chip) => {
      chip.setAttribute('aria-pressed', String(state.filters.states.includes(chip.dataset.state)));
    });
    view.querySelectorAll('[data-type]').forEach((chip) => {
      chip.setAttribute('aria-pressed', String(state.filters.post_types.includes(chip.dataset.type)));
    });
  };

  view.addEventListener('click', (event) => {
    const groupChip = event.target.closest('[data-group]');
    if (groupChip) {
      const value = groupChip.dataset.group;
      if (value === '') state.filters.group_ids = [];
      else {
        const id = Number(value);
        state.filters.group_ids = state.filters.group_ids.includes(id)
          ? state.filters.group_ids.filter((item) => item !== id)
          : [...state.filters.group_ids, id];
      }
      paintChips();
      runPreview();
      return;
    }
    const stateChip = event.target.closest('[data-state]');
    if (stateChip) {
      const value = stateChip.dataset.state;
      state.filters.states = state.filters.states.includes(value)
        ? state.filters.states.filter((item) => item !== value)
        : [...state.filters.states, value];
      paintChips();
      runPreview();
      return;
    }
    const typeChip = event.target.closest('[data-type]');
    if (typeChip) {
      const value = typeChip.dataset.type;
      state.filters.post_types = state.filters.post_types.includes(value)
        ? state.filters.post_types.filter((item) => item !== value)
        : [...state.filters.post_types, value];
      paintChips();
      runPreview();
    }
    const preset = event.target.closest('[data-preset]');
    if (preset) applyPreset(preset.dataset.preset, view, paintChips, runPreview);
  });

  view.querySelector('[data-has-link]').addEventListener('change', (event) => {
    state.filters.contains_link = event.target.checked ? true : null;
    runPreview();
  });
  view.querySelector('#cl-q').addEventListener('input', debounce((event) => {
    state.filters.q = event.target.value.trim();
    runPreview();
  }, 320));
  const numeric = (selector, key) => {
    view.querySelector(selector).addEventListener('input', debounce((event) => {
      const raw = event.target.value;
      state.filters[key] = raw === '' ? null : Number(raw);
      runPreview();
    }, 320));
  };
  numeric('#cl-age', 'older_than_days');
  numeric('#cl-reports', 'min_reports');
  numeric('#cl-likes', 'max_likes');

  paintChips();
  await loadPreview(previewEl);

  /* ---- run ---- */
  view.querySelector('[data-run]').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const action = view.querySelector('#cl-action').value;
    const name = view.querySelector('#cl-name').value.trim() || 'Manual sweep';

    button.disabled = true;
    button.innerHTML = `${icon('refresh', 'icon-sm')} Counting matches…`;
    let dry;
    try {
      dry = await api.bulkFilter({ filters: cleanFilters(), action, name, dry_run: true });
    } catch (error) {
      toast({ kind: 'error', title: 'Preview failed', text: error.message });
      reset(button);
      return;
    }

    if (!dry.matched) {
      toast({ kind: 'info', title: 'Nothing matches', text: 'Loosen the filter and try again.' });
      reset(button);
      return;
    }

    const ok = await confirmDialog({
      title: `${action === 'purge' ? 'Permanently delete' : action === 'delete' || action === 'decline' ? 'Move to trash' : action} ${plural(dry.matched, 'post')}?`,
      message: `This will run across ${state.filters.group_ids.length || 'all'} group(s).`,
      confirmLabel: dry.matched === 1 ? 'Yes, do it' : `Yes, ${action} ${dry.matched}`,
      danger: ['delete', 'purge', 'decline'].includes(action),
      details: `${describeFilters()}<br><br>${action === 'purge'
        ? '<b>These posts will be gone for good.</b>'
        : 'You can undo this from the trash.'}`,
    });
    if (!ok) { reset(button); return; }

    button.innerHTML = `${icon('refresh', 'icon-sm')} Running…`;
    try {
      const result = await api.bulkFilter({ filters: cleanFilters(), action, name });
      toast({
        kind: 'success',
        title: `${action === 'purge' ? 'Deleted' : 'Processed'} ${plural(result.processed, 'post')}`,
        text: `Run "${name}" finished in ${result.job_id ? 'the background' : 'time'}.`,
      });
      store.invalidateStats();
      store.loadStats(true).catch(() => {});
      await loadPreview(previewEl);
    } catch (error) {
      toast({ kind: 'error', title: 'Sweep failed', text: error.message });
    } finally {
      reset(button);
    }
  });

  function reset(button) {
    button.disabled = false;
    button.innerHTML = `${icon('broom', 'icon-sm')} Run sweep`;
  }
}

function cleanFilters() {
  const out = { ...state.filters };
  Object.keys(out).forEach((key) => {
    if (out[key] === null || out[key] === '' || (Array.isArray(out[key]) && out[key].length === 0)) delete out[key];
  });
  return out;
}

function describeFilters() {
  const parts = [];
  const f = state.filters;
  if (f.group_ids?.length) parts.push(`${f.group_ids.length} group(s)`);
  if (f.states?.length) parts.push(`state: ${f.states.join(', ')}`);
  if (f.post_types?.length) parts.push(`type: ${f.post_types.join(', ')}`);
  if (f.q) parts.push(`contains "<b>${esc(f.q)}</b>"`);
  if (f.contains_link) parts.push('has a link');
  if (f.older_than_days != null) parts.push(`older than ${f.older_than_days}d`);
  if (f.min_reports != null) parts.push(`≥ ${f.min_reports} reports`);
  if (f.max_likes != null) parts.push(`≤ ${f.max_likes} reactions`);
  return parts.length ? parts.join(' · ') : 'Every live post in your workspace';
}

function applyPreset(id, view, paintChips, runPreview) {
  const preset = PRESETS.find((item) => item.id === id);
  if (!preset) return;
  state.filters = { group_ids: [], states: [], post_types: [], q: '', contains_link: null, older_than_days: null, min_reports: null, max_likes: null, ...preset.filters };
  view.querySelector('#cl-q').value = state.filters.q || '';
  view.querySelector('#cl-age').value = state.filters.older_than_days ?? '';
  view.querySelector('#cl-reports').value = state.filters.min_reports ?? '';
  view.querySelector('#cl-likes').value = state.filters.max_likes ?? '';
  view.querySelector('[data-has-link]').checked = Boolean(state.filters.contains_link);
  paintChips();
  runPreview();
  toast({ kind: 'info', title: 'Preset applied', text: preset.blurb, timeout: 3000 });
}

async function loadPreview(host) {
  host.innerHTML = `<div class="skeleton" style="height:200px"></div>`;
  try {
    const result = await api.bulkFilter({ filters: cleanFilters(), action: 'delete', dry_run: true });
    state.preview = result;
    if (!result.matched) {
      host.innerHTML = `
        <div class="empty" style="padding:30px 10px">
          <div class="empty__icon is-success" style="background:var(--success-soft);color:var(--success)">${icon('check-circle')}</div>
          <h3>No matches</h3>
          <p>Nothing in your workspace matches this filter. Loosen it, or pick a preset.</p>
        </div>`;
      return;
    }
    host.innerHTML = `
      <div class="stat" style="--accent:var(--danger);margin-bottom:14px">
        <div class="stat__label">${icon('filter', 'icon-sm')} Matching posts</div>
        <div class="stat__value">${result.matched}</div>
        <div class="stat__meta">${esc(describeFilters())}</div>
      </div>
      <div class="tiny muted" style="margin-bottom:8px">Sample of what would be affected</div>
      <div class="postlist" data-samples></div>`;

    const samples = result.ids.slice(0, 4);
    const posts = (await Promise.all(samples.map((id) => api.post(id).catch(() => null)))).filter(Boolean);
    host.querySelector('[data-samples]').innerHTML = posts.map((post) => `
      <div class="post is-${post.state}" style="padding:11px 13px">
        <div class="post__body">
          <div class="post__head">
            <span class="post__author">${esc(post.author_name)}</span>
            <span class="post__sep">·</span>
            <span class="post__group">${esc(post.group_name)}</span>
            <span class="post__sep">·</span>
            <span class="post__time">${esc(relTime(post.created_at))}</span>
            <div class="post__badges">${typeBadge(post.post_type)}</div>
          </div>
          <p class="post__msg" style="font-size:12.5px;margin-top:6px">${linkify(esc(post.message)).slice(0, 260)}</p>
        </div>
      </div>`).join('');
  } catch (error) {
    host.innerHTML = `<div class="callout callout--danger">${icon('alert', 'icon-sm')}<div class="callout__body">${esc(error.message)}</div></div>`;
  }
}
