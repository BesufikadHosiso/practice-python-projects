/** Settings — profile, security, appearance and workspace danger zone. */
import { api } from '../api.js';
import { store } from '../store.js';
import {
  confirmDialog, esc, formData, fullTime, icon, toast,
} from '../ui.js';

export async function render(view) {
  const user = store.user;

  view.innerHTML = `
    <div class="page__head">
      <div>
        <h1>${icon('gear')} Settings</h1>
        <p class="page__desc">Your account, how the console looks, and the tools for resetting the demo workspace.</p>
      </div>
    </div>

    <div class="split">
      <div class="stack">
        <div class="card">
          <div class="card__head"><div><h3>${icon('users', 'icon-sm')} Profile</h3><span class="sub">Shown in the activity log as the actor</span></div></div>
          <div class="card__body">
            <form id="profile-form" novalidate>
              <div class="form__row">
                <div class="field">
                  <label for="pf-name">Display name</label>
                  <input id="pf-name" name="name" type="text" value="${esc(user?.name || '')}" minlength="2" required>
                  <span class="err">At least 2 characters.</span>
                </div>
                <div class="field">
                  <label for="pf-email">Email</label>
                  <input id="pf-email" name="email" type="email" value="${esc(user?.email || '')}" required>
                  <span class="err">Enter a valid email.</span>
                </div>
              </div>
              <div class="row" style="gap:12px;align-items:center;margin-bottom:16px">
                <span class="avatar avatar--lg">${esc(user?.avatar_seed || '??')}</span>
                <div class="small muted">Your avatar is generated from your initials — no upload needed.</div>
              </div>
              <button class="btn btn--primary" type="submit">${icon('check', 'icon-sm')} Save profile</button>
            </form>
          </div>
        </div>

        <div class="card">
          <div class="card__head"><div><h3>${icon('lock', 'icon-sm')} Security</h3><span class="sub">Passwords are stored as PBKDF2-SHA256 hashes</span></div></div>
          <div class="card__body">
            <form id="password-form" novalidate>
              <div class="field">
                <label for="pw-current">Current password</label>
                <input id="pw-current" name="current_password" type="password" autocomplete="current-password" required>
              </div>
              <div class="form__row">
                <div class="field">
                  <label for="pw-new">New password</label>
                  <input id="pw-new" name="new_password" type="password" autocomplete="new-password" minlength="8" required>
                  <span class="hint">Minimum 8 characters.</span>
                </div>
                <div class="field">
                  <label for="pw-confirm">Confirm new password</label>
                  <input id="pw-confirm" type="password" autocomplete="new-password" minlength="8" required>
                  <span class="err">The passwords do not match.</span>
                </div>
              </div>
              <button class="btn" type="submit">${icon('lock', 'icon-sm')} Change password</button>
            </form>
          </div>
        </div>

        <div class="card">
          <div class="card__head"><div><h3>${icon('sun', 'icon-sm')} Appearance</h3></div></div>
          <div class="card__body">
            <div class="row wrap" style="gap:10px">
              <button class="btn" data-theme-set="light" aria-pressed="${store.theme === 'light'}">${icon('sun', 'icon-sm')} Light</button>
              <button class="btn" data-theme-set="dark" aria-pressed="${store.theme === 'dark'}">${icon('moon', 'icon-sm')} Dark</button>
            </div>
            <p class="small muted" style="margin-top:10px">The default follows your system preference on first visit.</p>
          </div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card__head"><div><h3>${icon('info', 'icon-sm')} Workspace</h3></div></div>
          <div class="card__body">
            <dl class="kv-list" data-summary>
              <div class="kv"><dt>Loading…</dt><dd>—</dd></div>
            </dl>
          </div>
        </div>

        <div class="card">
          <div class="card__head"><div><h3>${icon('external', 'icon-sm')} Developer</h3></div></div>
          <div class="card__body stack" style="gap:9px">
            <a class="quickaction" href="/api/docs" target="_blank" rel="noopener">
              <span class="quickaction__icon">${icon('external')}</span>
              <span><b>Interactive API docs</b><span>Swagger UI at /api/docs</span></span>
            </a>
            <a class="quickaction" href="/api/openapi.json" target="_blank" rel="noopener">
              <span class="quickaction__icon">${icon('stack')}</span>
              <span><b>OpenAPI schema</b><span>The raw contract for the REST API</span></span>
            </a>
          </div>
        </div>

        <div class="card" style="border-color:color-mix(in srgb, var(--danger) 32%, var(--border))">
          <div class="card__head"><div><h3 style="color:var(--danger)">${icon('alert', 'icon-sm')} Danger zone</h3></div></div>
          <div class="card__body stack" style="gap:10px">
            <div>
              <div class="strong" style="font-size:13px">Permanently delete everything in the trash</div>
              <p class="small muted" style="margin-top:2px">Removes every soft-deleted post from the database.</p>
            </div>
            <button class="btn btn--danger btn--block" data-empty-trash>${icon('trash-sm', 'icon-sm')} Empty the trash</button>
            <div class="divider"></div>
            <div>
              <div class="strong" style="font-size:13px">Sign out</div>
              <p class="small muted" style="margin-top:2px">Your token is dropped from this browser. Data stays on the server.</p>
            </div>
            <button class="btn btn--block" data-logout>${icon('logout', 'icon-sm')} Sign out</button>
          </div>
        </div>
      </div>
    </div>`;

  /* ------------------------------------------------------------- profile */
  view.querySelector('#profile-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = formData(form);
    let valid = true;
    if (data.name.trim().length < 2) { form.name.closest('.field').classList.add('has-error'); valid = false; }
    else form.name.closest('.field').classList.remove('has-error');
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email.trim())) { form.email.closest('.field').classList.add('has-error'); valid = false; }
    else form.email.closest('.field').classList.remove('has-error');
    if (!valid) return;

    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    try {
      const updated = await api.updateProfile({ name: data.name.trim(), email: data.email.trim() });
      store.setSession(updated);
      toast({ kind: 'success', title: 'Profile saved', text: `You are now "${updated.name}".` });
      render(view, { params: new URLSearchParams() });
    } catch (error) {
      toast({ kind: 'error', title: 'Could not save your profile', text: error.message });
      button.disabled = false;
    }
  });

  /* ------------------------------------------------------------ password */
  view.querySelector('#password-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = formData(form);
    const confirmField = form.querySelector('#pw-confirm').closest('.field');
    if (data.new_password !== form.querySelector('#pw-confirm').value) {
      confirmField.classList.add('has-error');
      return;
    }
    confirmField.classList.remove('has-error');

    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    try {
      await api.changePassword({ current_password: data.current_password, new_password: data.new_password });
      toast({ kind: 'success', title: 'Password changed', text: 'Use it the next time you sign in.' });
      form.reset();
    } catch (error) {
      toast({ kind: 'error', title: 'Could not change the password', text: error.message });
    } finally {
      button.disabled = false;
    }
  });

  /* --------------------------------------------------------------- theme */
  view.addEventListener('click', (event) => {
    const button = event.target.closest('[data-theme-set]');
    if (!button) return;
    store.theme = button.dataset.themeSet;
    store.applyTheme();
    view.querySelectorAll('[data-theme-set]').forEach((item) => {
      item.setAttribute('aria-pressed', String(item.dataset.themeSet === store.theme));
    });
  });

  /* --------------------------------------------------------------- stats */
  try {
    const stats = await store.loadStats(true);
    const groups = await store.loadGroups(true);
    view.querySelector('[data-summary]').innerHTML = `
      <div class="kv"><dt>Account created</dt><dd>${esc(fullTime(user?.created_at))}</dd></div>
      <div class="kv"><dt>Role</dt><dd>${esc(user?.role || 'owner')}</dd></div>
      <div class="kv"><dt>Groups connected</dt><dd>${groups.filter((group) => group.connected).length} of ${groups.length}</dd></div>
      <div class="kv"><dt>Live posts</dt><dd>${stats.posts.live}</dd></div>
      <div class="kv"><dt>In trash</dt><dd>${stats.posts.trashed}</dd></div>
      <div class="kv"><dt>Posts auto-removed by rules</dt><dd>${stats.cleanup.auto_removed}</dd></div>
      <div class="kv"><dt>Members reached</dt><dd>${stats.groups.members.toLocaleString()}</dd></div>`;
  } catch (error) {
    view.querySelector('[data-summary]').innerHTML = `<div class="kv"><dt>Could not load</dt><dd>${esc(error.message)}</dd></div>`;
  }

  /* --------------------------------------------------------- danger zone */
  view.querySelector('[data-empty-trash]').addEventListener('click', async () => {
    const ok = await confirmDialog({
      title: 'Empty the trash?',
      message: 'Every soft-deleted post will be permanently removed from the database.',
      confirmLabel: 'Empty trash',
      danger: true,
    });
    if (!ok) return;
    try {
      const result = await api.emptyTrash();
      toast({ kind: 'success', title: `Purged ${result.purged} post(s)` });
      store.invalidateStats();
      store.loadStats(true).catch(() => {});
      render(view, { params: new URLSearchParams() });
    } catch (error) {
      toast({ kind: 'error', title: 'Could not empty the trash', text: error.message });
    }
  });

  view.querySelector('[data-logout]').addEventListener('click', async () => {
    try { await api.logout(); } catch { /* token may already be gone */ }
    store.clearSession();
    toast({ kind: 'info', title: 'Signed out' });
    window.location.hash = '';
    window.location.reload();
  });
}
