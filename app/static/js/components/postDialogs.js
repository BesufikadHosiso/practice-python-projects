/** Post detail drawer + the create/edit modal (shared CRUD form). */
import { api } from '../api.js';
import {
  confirmDialog, esc, fullTime, icon, linkify, openDrawer, openModal, relTime,
  stateBadge, toast, typeBadge,
} from '../ui.js';

const TYPES = ['text', 'photo', 'link', 'video', 'poll', 'live', 'event'];
const STATES = ['published', 'pending', 'flagged', 'scheduled'];

export function openPostDrawer(post, onChanged) {
  const body = `
    <div class="row" style="gap:11px;margin-bottom:16px">
      <span class="avatar avatar--lg" data-c="3">${esc((post.author_name || '?').slice(0, 2).toUpperCase())}</span>
      <div style="flex:1;min-width:0">
        <div class="strong" style="font-size:14px">${esc(post.author_name)}</div>
        <div class="tiny muted">${esc(post.group_name)} · ${esc(relTime(post.published_at || post.created_at))}</div>
      </div>
      ${post.deleted_at ? '<span class="badge badge--trashed"><span class="dot"></span>In trash</span>' : stateBadge(post.state)}
    </div>

    <div class="card" style="box-shadow:none">
      <div class="card__body">
        <div class="row wrap" style="margin-bottom:10px;gap:6px">
          ${typeBadge(post.post_type)}
          <span class="tiny muted">Post #${post.id}</span>
        </div>
        <p class="post__msg" style="margin:0">${linkify(esc(post.message)) || '<span class="muted">(no text)</span>'}</p>
      </div>
    </div>

    ${post.reason ? `<div class="callout callout--warn" style="margin-top:14px">${icon('info', 'icon-sm')}
      <div class="callout__body"><b>Why it's here:</b> ${esc(post.reason)}</div></div>` : ''}

    <div class="grid grid--stats" style="margin-top:16px">
      ${[['heart', 'Reactions', post.likes], ['comment', 'Comments', post.comments],
        ['share', 'Shares', post.shares], ['alert', 'Reports', post.reports]]
        .map(([name, label, value]) => `
          <div class="card" style="box-shadow:none;padding:12px">
            <div class="tiny muted">${esc(label)}</div>
            <div style="font-size:20px;font-weight:670;margin-top:2px">${value}</div>
            <div style="color:var(--text-3);margin-top:2px">${icon(name, 'icon-sm')}</div>
          </div>`).join('')}
    </div>

    <dl class="kv-list" style="margin-top:18px">
      <div class="kv"><dt>Group</dt><dd>${esc(post.group_name)}</dd></div>
      <div class="kv"><dt>Created</dt><dd>${esc(fullTime(post.created_at))}</dd></div>
      <div class="kv"><dt>Published</dt><dd>${esc(post.published_at ? fullTime(post.published_at) : 'Not published')}</dd></div>
      <div class="kv"><dt>Last updated</dt><dd>${esc(fullTime(post.updated_at))}</dd></div>
      ${post.scheduled_for ? `<div class="kv"><dt>Scheduled for</dt><dd>${esc(fullTime(post.scheduled_for))}</dd></div>` : ''}
      ${post.deleted_at ? `<div class="kv"><dt>Deleted</dt><dd>${esc(fullTime(post.deleted_at))}</dd></div>` : ''}
    </dl>`;

  const footer = `
    <button class="btn" data-edit>${icon('edit', 'icon-sm')} Edit</button>
    <span class="spacer"></span>
    ${post.deleted_at
      ? `<button class="btn btn--soft" data-restore>${icon('undo', 'icon-sm')} Restore</button>
         <button class="btn btn--danger" data-purge>${icon('trash-sm', 'icon-sm')} Delete forever</button>`
      : `<button class="btn" data-flag>${icon('flag', 'icon-sm')} Flag</button>
         <button class="btn btn--danger" data-delete>${icon('trash-sm', 'icon-sm')} Delete</button>`}`;

  const { close } = openDrawer({ title: 'Post details', subtitle: post.message.slice(0, 80), body, footer });
  const drawer = document.querySelector('.drawer');

  drawer.querySelector('[data-edit]').addEventListener('click', () => {
    close();
    openPostEditor(post, [], () => { close(); onChanged?.(); });
  });

  const run = async (action, label) => {
    try {
      await api.bulk({ ids: [post.id], action });
      toast({ kind: 'success', title: label, text: `Post #${post.id} updated.` });
      close();
      onChanged?.();
    } catch (error) {
      toast({ kind: 'error', title: `${label} failed`, text: error.message });
    }
  };

  drawer.querySelector('[data-flag]')?.addEventListener('click', () => run('flag', 'Flagged for review'));
  drawer.querySelector('[data-restore]')?.addEventListener('click', () => run('restore', 'Restored'));
  drawer.querySelector('[data-delete]')?.addEventListener('click', () => run('delete', 'Moved to trash'));
  drawer.querySelector('[data-purge]')?.addEventListener('click', async () => {
    const ok = await confirmDialog({
      title: 'Delete forever?',
      message: 'This removes the post from the database permanently. It cannot be restored.',
      confirmLabel: 'Delete forever',
      danger: true,
    });
    if (ok) run('purge', 'Deleted permanently');
  });
}

/** Create (post = null) or edit an existing post. */
export function openPostEditor(post, groups, onSaved) {
  const editing = Boolean(post?.id);
  const options = (groups && groups.length ? groups : [])
    .map((group) => `<option value="${group.id}" ${editing && post.group_id === group.id ? 'selected' : ''}>${esc(group.name)}</option>`)
    .join('');

  const body = `
    <form id="post-form" novalidate>
      <div class="field">
        <label for="pf-group">Group</label>
        <select id="pf-group" name="group_id" required>
          <option value="">Choose a group…</option>${options}
        </select>
        <span class="err">Pick the group this post belongs to.</span>
      </div>
      <div class="form__row">
        <div class="field">
          <label for="pf-author">Author</label>
          <input id="pf-author" name="author_name" type="text" value="${esc(post?.author_name || '')}" placeholder="Member name" minlength="2" required>
          <span class="err">At least 2 characters.</span>
        </div>
        <div class="field">
          <label for="pf-type">Post type</label>
          <select id="pf-type" name="post_type">
            ${TYPES.map((type) => `<option value="${type}" ${post?.post_type === type ? 'selected' : ''}>${type[0].toUpperCase() + type.slice(1)}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="field">
        <label for="pf-message">Post text</label>
        <textarea id="pf-message" name="message" placeholder="What did the member post?">${esc(post?.message || '')}</textarea>
        <span class="hint">Links are detected automatically and count toward the spam rules.</span>
      </div>
      <div class="form__row">
        <div class="field">
          <label for="pf-state">State</label>
          <select id="pf-state" name="state">
            ${STATES.map((state) => `<option value="${state}" ${(post?.state || 'published') === state ? 'selected' : ''}>${state[0].toUpperCase() + state.slice(1)}</option>`).join('')}
          </select>
        </div>
        <div class="field">
          <label for="pf-reason">Moderator note</label>
          <input id="pf-reason" name="reason" type="text" value="${esc(post?.reason || '')}" placeholder="Optional">
        </div>
      </div>
    </form>`;

  const { root, close } = openModal({
    title: editing ? 'Edit post' : 'Add a post',
    subtitle: editing ? `Post #${post.id}` : 'Manually log a post into the moderation queue',
    body,
    size: 'lg',
    footer: `<button class="btn" data-cancel>Cancel</button>
             <button class="btn btn--primary" data-save>${icon('check', 'icon-sm')} ${editing ? 'Save changes' : 'Add post'}</button>`,
  });

  const form = root.querySelector('#post-form');
  root.querySelector('[data-cancel]').addEventListener('click', close);

  const markError = (input, message) => {
    const field = input.closest('.field');
    field?.classList.toggle('has-error', Boolean(message));
    const slot = field?.querySelector('.err');
    if (slot && message) slot.textContent = message;
  };

  root.querySelector('[data-save]').addEventListener('click', async () => {
    const data = Object.fromEntries(new FormData(form).entries());
    let valid = true;
    if (!data.group_id) { markError(form.group_id, 'Pick a group.'); valid = false; }
    if ((data.author_name || '').trim().length < 2) { markError(form.author_name, 'At least 2 characters.'); valid = false; }
    if (!valid) return;

    const payload = {
      group_id: Number(data.group_id),
      author_name: data.author_name.trim(),
      message: data.message || '',
      post_type: data.post_type,
      state: data.state,
      reason: data.reason || '',
    };

    const button = root.querySelector('[data-save]');
    button.disabled = true;
    try {
      if (editing) await api.updatePost(post.id, payload);
      else await api.createPost(payload);
      toast({ kind: 'success', title: editing ? 'Post updated' : 'Post added', text: editing ? `Post #${post.id} saved.` : 'It now shows up in the queue.' });
      close();
      onSaved?.();
    } catch (error) {
      button.disabled = false;
      toast({ kind: 'error', title: 'Could not save the post', text: error.message });
    }
  });
}
