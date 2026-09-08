/** Cleanup rules — CRUD, enable/disable, dry-run preview and manual runs. */
import { api } from '../api.js';
import { store } from '../store.js';
import {
  confirmDialog, emptyState, esc, errorState, formData, icon, linkify, openModal,
  plural, relTime, skeletonCards, toast,
} from '../ui.js';

const CONDITIONS = [
  ['keyword', 'Message contains keyword', 'comma,separated,terms', false],
  ['domain', 'Links to a domain', 'bit.ly,tinyurl.com', false],
  ['age_days', 'Older than N days', '', true],
  ['low_engagement', 'At most N reactions', '', true],
  ['reported', 'Reported at least N times', '', true],
  ['repeat_poster', 'Author posted N+ times', '', true],
  ['banned_author', 'Author is banned', '', false],
  ['duplicate', 'Duplicate message', '', false],
];
const ACTIONS = [['delete', 'Move to trash'], ['flag', 'Flag for review'], ['approve', 'Approve / publish'], ['decline', 'Decline'], ['archive', 'Archive']];

export async function render(view) {
  const groups = await store.loadGroups();

  view.innerHTML = `
    <div class="page__head">
      <div>
        <h1>${icon('rule')} Cleanup rules</h1>
        <p class="page__desc">Rules describe what should never survive in your groups. Run one on demand, or hit "Run cleanup rules" from the dashboard to fire every enabled rule at once.</p>
      </div>
      <div class="page__actions">
        <button class="btn" data-run-all>${icon('sparkle', 'icon-sm')} Run all enabled</button>
        <button class="btn btn--primary" data-new>${icon('plus', 'icon-sm')} New rule</button>
      </div>
    </div>
    <div data-list>${skeletonCards(6, 'grid--rules')}</div>`;

  const listEl = view.querySelector('[data-list]');

  const paint = async () => {
    listEl.innerHTML = skeletonCards(4, 'grid--rules');
    try {
      const { items } = await api.rules();
      if (!items.length) {
        listEl.innerHTML = `<div class="card">${emptyState({
          icon: 'rule', title: 'No cleanup rules yet',
          message: 'Create a rule to automatically catch spam, duplicates or stale posts across your groups.',
          actions: '<button class="btn btn--primary" data-new-empty>New rule</button>',
        })}</div>`;
        listEl.querySelector('[data-new-empty]').addEventListener('click', () => openRuleDialog(null, groups, paint));
        return;
      }
      listEl.innerHTML = `<div class="grid grid--rules">${items.map((rule) => card(rule)).join('')}</div>`;
    } catch (error) {
      listEl.innerHTML = `<div class="card">${errorState(error.message)}</div>`;
      listEl.querySelector('[data-retry]').addEventListener('click', paint);
    }
  };

  function card(rule) {
    const condition = CONDITIONS.find(([value]) => value === rule.condition_type);
    return `
      <div class="card groupcard" data-rule="${rule.id}">
        <div class="card__head" style="align-items:flex-start">
          <div style="flex:1;min-width:0">
            <div class="row" style="gap:7px">
              <h3 class="truncate">${esc(rule.name)}</h3>
              <span class="badge badge--${rule.severity}">${rule.severity}</span>
            </div>
            <span class="sub">${esc(rule.group_name || 'All groups')}</span>
          </div>
          <label class="switch" title="${rule.enabled ? 'Pause rule' : 'Enable rule'}">
            <input type="checkbox" data-toggle ${rule.enabled ? 'checked' : ''} aria-label="Enable ${esc(rule.name)}">
          </label>
        </div>
        <div class="rulecard__body">
          <p class="small muted" style="line-height:1.6">${esc(rule.description || 'No description.')}</p>
          <div class="rulecard__cond">
            ${icon('filter', 'icon-sm')}
            <span><b>${esc(condition?.[1] || rule.condition_type)}</b></span>
            ${rule.condition_value ? `<code>${esc(rule.condition_value)}</code>` : ''}
            ${rule.threshold ? `<code>${rule.threshold}</code>` : ''}
            <span class="spacer"></span>
            <span class="badge badge--primary">${esc(ACTIONS.find(([value]) => value === rule.action)?.[1] || rule.action)}</span>
          </div>
          <div class="row wrap tiny muted" style="gap:12px">
            <span>${icon('history', 'icon-sm')} ${rule.runs} run${rule.runs === 1 ? '' : 's'}</span>
            <span>${icon('trash-sm', 'icon-sm')} ${plural(rule.affected, 'post')} affected</span>
            <span>${icon('clock', 'icon-sm')} ${rule.last_run_at ? esc(relTime(rule.last_run_at)) : 'never run'}</span>
          </div>
          <div class="row" style="gap:6px;margin-top:13px;flex-wrap:wrap">
            <button class="btn btn--sm" data-preview>${icon('eye', 'icon-sm')} Preview</button>
            <button class="btn btn--sm btn--soft" data-run ${rule.enabled ? '' : 'disabled'}>${icon('play', 'icon-sm')} Run now</button>
            <span class="spacer"></span>
            <button class="btn btn--sm btn--ghost btn--icon" data-edit aria-label="Edit rule">${icon('edit', 'icon-sm')}</button>
            <button class="btn btn--sm btn--ghost btn--icon" data-delete aria-label="Delete rule" style="color:var(--danger)">${icon('trash-sm', 'icon-sm')}</button>
          </div>
        </div>
      </div>`;
  }

  view.addEventListener('click', async (event) => {
    const target = event.target;
    const cardEl = target.closest('[data-rule]');
    if (target.closest('[data-new]')) { openRuleDialog(null, groups, paint); return; }
    if (target.closest('[data-run-all]')) { await runAll(view.querySelector('[data-run-all]'), paint); return; }
    if (!cardEl) return;
    const id = Number(cardEl.dataset.rule);

    if (target.closest('[data-edit]')) {
      const { items } = await api.rules();
      openRuleDialog(items.find((rule) => rule.id === id), groups, paint);
    } else if (target.closest('[data-run]')) {
      await runRule(id, cardEl, paint);
    } else if (target.closest('[data-preview]')) {
      await previewRule(id);
    } else if (target.closest('[data-delete]')) {
      const ok = await confirmDialog({
        title: 'Delete this rule?',
        message: 'Posts it already removed stay in the trash. The rule itself will be gone.',
        confirmLabel: 'Delete rule',
        danger: true,
      });
      if (!ok) return;
      try {
        await api.deleteRule(id);
        toast({ kind: 'success', title: 'Rule deleted' });
        await paint();
      } catch (error) {
        toast({ kind: 'error', title: 'Could not delete the rule', text: error.message });
      }
    }
  });

  view.addEventListener('change', async (event) => {
    const toggle = event.target.closest('[data-toggle]');
    if (!toggle) return;
    const id = Number(toggle.closest('[data-rule]').dataset.rule);
    toggle.disabled = true;
    try {
      const rule = await api.toggleRule(id);
      toast({ kind: rule.enabled ? 'success' : 'info', title: rule.enabled ? 'Rule enabled' : 'Rule paused', text: rule.name });
      await paint();
    } catch (error) {
      toast({ kind: 'error', title: 'Could not update the rule', text: error.message });
      toggle.disabled = false;
    }
  });

  await paint();
}

async function runAll(button, paint) {
  button.disabled = true;
  button.innerHTML = `${icon('refresh', 'icon-sm')} Running…`;
  try {
    const result = await api.runAllRules();
    toast({
      kind: result.affected ? 'success' : 'info',
      title: result.affected ? `${plural(result.affected, 'post')} handled` : 'Nothing matched',
      text: `${result.rules} enabled rule(s) ran.`,
    });
    store.invalidateStats();
    store.loadStats(true).catch(() => {});
    await paint();
  } catch (error) {
    toast({ kind: 'error', title: 'Run failed', text: error.message });
  } finally {
    button.disabled = false;
    button.innerHTML = `${icon('sparkle', 'icon-sm')} Run all enabled`;
  }
}

async function runRule(id, cardEl, paint) {
  const button = cardEl.querySelector('[data-run]');
  button.disabled = true;
  button.innerHTML = `${icon('refresh', 'icon-sm')} Running…`;
  try {
    const result = await api.runRule(id, false);
    toast({
      kind: result.processed ? 'success' : 'info',
      title: result.processed ? `${plural(result.processed, 'post')} ${result.action}d` : 'Nothing matched',
      text: 'Check the run history for details.',
    });
    store.invalidateStats();
    store.loadStats(true).catch(() => {});
    await paint();
  } catch (error) {
    toast({ kind: 'error', title: 'Run failed', text: error.message });
    button.disabled = false;
    button.innerHTML = `${icon('play', 'icon-sm')} Run now`;
  }
}

async function previewRule(id) {
  const { root, close } = openModal({
    title: 'Rule preview',
    subtitle: 'What this rule would act on right now',
    body: '<div class="skeleton" style="height:220px"></div>',
    footer: '<button class="btn btn--primary" data-close-preview>Close</button>',
    size: 'lg',
  });
  root.querySelector('[data-close-preview]').addEventListener('click', close);
  try {
    const { rule, matched, items } = await api.previewRule(id);
    root.querySelector('.modal__body').innerHTML = `
      <div class="callout callout--${matched ? 'warn' : 'info'}" style="margin-bottom:16px">
        ${icon(matched ? 'alert' : 'check-circle', 'icon-sm')}
        <div class="callout__body"><b>${plural(matched, 'post')}</b> match <b>${esc(rule.name)}</b> right now.
        ${matched ? 'They will be ' + rule.action + 'd when the rule runs.' : 'Nothing to do.'}</div>
      </div>
      ${items.length ? `<div class="postlist">${items.map((post) => `
        <div class="post is-${post.state}" style="padding:11px 13px">
          <div class="post__body">
            <div class="post__head">
              <span class="post__author">${esc(post.author_name)}</span>
              <span class="post__sep">·</span><span class="post__group">${esc(post.group_name)}</span>
              <span class="post__sep">·</span><span class="post__time">${esc(relTime(post.created_at))}</span>
            </div>
            <p class="post__msg" style="font-size:12.5px;margin-top:6px">${linkify(esc(post.message)).slice(0, 240)}</p>
          </div>
        </div>`).join('')}</div>`
        : '<p class="muted small">No posts currently match this rule.</p>'}`;
  } catch (error) {
    root.querySelector('.modal__body').innerHTML = errorState(error.message);
  }
}

function openRuleDialog(rule, groups, onSaved) {
  const editing = Boolean(rule?.id);
  const body = `
    <form id="rule-form" novalidate>
      <div class="field">
        <label for="rf-name">Rule name</label>
        <input id="rf-name" name="name" type="text" value="${esc(rule?.name || '')}" placeholder="Remove crypto spam" minlength="2" required>
        <span class="err">Give the rule a name.</span>
      </div>
      <div class="field">
        <label for="rf-desc">What it does</label>
        <textarea id="rf-desc" name="description" placeholder="Shown on the rule card and in the run history.">${esc(rule?.description || '')}</textarea>
      </div>
      <div class="form__row">
        <div class="field">
          <label for="rf-group">Applies to</label>
          <select id="rf-group" name="group_id">
            <option value="">All groups</option>
            ${groups.map((group) => `<option value="${group.id}" ${rule?.group_id === group.id ? 'selected' : ''}>${esc(group.name)}</option>`).join('')}
          </select>
        </div>
        <div class="field">
          <label for="rf-severity">Severity</label>
          <select id="rf-severity" name="severity">
            ${['low', 'medium', 'high'].map((value) => `<option value="${value}" ${(rule?.severity || 'medium') === value ? 'selected' : ''}>${value[0].toUpperCase() + value.slice(1)}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="field">
        <label for="rf-condition">Condition</label>
        <select id="rf-condition" name="condition_type">
          ${CONDITIONS.map(([value, label]) => `<option value="${value}" ${rule?.condition_type === value ? 'selected' : ''}>${label}</option>`).join('')}
        </select>
      </div>
      <div class="form__row">
        <div class="field">
          <label for="rf-value">Value</label>
          <input id="rf-value" name="condition_value" type="text" value="${esc(rule?.condition_value || '')}" placeholder="comma,separated,terms">
          <span class="hint" data-value-hint>Comma-separate multiple terms.</span>
          <span class="err">This condition needs a value.</span>
        </div>
        <div class="field">
          <label for="rf-threshold">Threshold</label>
          <input id="rf-threshold" name="threshold" type="number" min="0" value="${rule?.threshold ?? 0}">
        </div>
      </div>
      <div class="form__row">
        <div class="field">
          <label for="rf-action">Then</label>
          <select id="rf-action" name="action">
            ${ACTIONS.map(([value, label]) => `<option value="${value}" ${(rule?.action || 'delete') === value ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </div>
        <div class="field" style="justify-content:flex-end">
          <label class="check"><input type="checkbox" name="enabled" ${rule?.enabled === false ? '' : 'checked'}><span>Rule is active</span></label>
        </div>
      </div>
    </form>`;

  const { root, close } = openModal({
    title: editing ? 'Edit rule' : 'New cleanup rule',
    subtitle: editing ? rule.name : 'Describe what should never survive in your groups',
    body,
    footer: `<button class="btn" data-cancel>Cancel</button>
             <button class="btn" data-test>${icon('eye', 'icon-sm')} Test match</button>
             <button class="btn btn--primary" data-save>${icon('check', 'icon-sm')} ${editing ? 'Save rule' : 'Create rule'}</button>`,
  });

  const form = root.querySelector('#rule-form');
  const conditionSelect = form.condition_type;
  const valueInput = form.condition_value;
  const thresholdInput = form.threshold;

  const syncCondition = () => {
    const [, label, placeholder, usesThreshold] = CONDITIONS.find(([value]) => value === conditionSelect.value);
    valueInput.placeholder = placeholder || 'Not needed for this condition';
    valueInput.disabled = !placeholder;
    valueInput.closest('.field').querySelector('[data-value-hint]').textContent = placeholder
      ? 'Comma-separate multiple terms.'
      : 'This condition does not need a value.';
    thresholdInput.disabled = !usesThreshold;
  };
  conditionSelect.addEventListener('change', syncCondition);
  syncCondition();

  root.querySelector('[data-cancel]').addEventListener('click', close);

  const collect = () => {
    const data = formData(form);
    return {
      name: data.name.trim(),
      description: data.description || '',
      group_id: data.group_id ? Number(data.group_id) : null,
      condition_type: data.condition_type,
      condition_value: data.condition_value || '',
      threshold: Number(data.threshold || 0),
      action: data.action,
      severity: data.severity,
      enabled: Boolean(data.enabled),
    };
  };

  root.querySelector('[data-test]').addEventListener('click', async () => {
    const payload = collect();
    const button = root.querySelector('[data-test]');
    button.disabled = true;
    try {
      const result = await api.dryRunRule(payload);
      toast({
        kind: result.matched ? 'warn' : 'success',
        title: `${plural(result.matched, 'post')} would match`,
        text: result.matched ? 'Save the rule and run it when you are ready.' : 'Nothing matches this rule right now.',
      });
    } catch (error) {
      toast({ kind: 'error', title: 'Test failed', text: error.message });
    } finally {
      button.disabled = false;
    }
  });

  root.querySelector('[data-save]').addEventListener('click', async () => {
    const payload = collect();
    const nameField = form.name.closest('.field');
    const valueField = valueInput.closest('.field');
    nameField.classList.toggle('has-error', payload.name.length < 2);
    const needsValue = ['keyword', 'domain'].includes(payload.condition_type);
    valueField.classList.toggle('has-error', needsValue && !payload.condition_value.trim());
    if (payload.name.length < 2 || (needsValue && !payload.condition_value.trim())) return;

    const button = root.querySelector('[data-save]');
    button.disabled = true;
    try {
      if (editing) await api.updateRule(rule.id, payload);
      else await api.createRule(payload);
      toast({ kind: 'success', title: editing ? 'Rule saved' : 'Rule created', text: payload.name });
      close();
      onSaved?.();
    } catch (error) {
      button.disabled = false;
      toast({ kind: 'error', title: 'Could not save the rule', text: error.message });
    }
  });
}
