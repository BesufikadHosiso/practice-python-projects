/** Dashboard: KPI cards, 14-day cleanup trend, top groups, spam signals. */
import { api } from '../api.js';
import { store } from '../store.js';
import {
  compactNumber, dayLabel, emptyState, esc, icon, plural, relTime, skeletonStats, toast,
} from '../ui.js';

export async function render(view, { params }) {
  view.innerHTML = `
    <div class="page__head">
      <div>
        <h1>${icon('dashboard')} Good ${greeting()}, ${esc((store.user?.name || 'there').split(' ')[0])}</h1>
        <p class="page__desc">Here's what needs moderating across your <span data-group-count>—</span> connected groups.</p>
      </div>
      <div class="page__actions">
        <a class="btn" href="#/cleaner">${icon('broom', 'icon-sm')} Bulk cleaner</a>
        <button class="btn btn--primary" data-run-auto>${icon('sparkle', 'icon-sm')} Run cleanup rules</button>
      </div>
    </div>
    <div data-stats>${skeletonStats(4)}</div>
    <div class="split" style="margin-top:16px">
      <div class="stack">
        <div class="card" data-chart-card>
          <div class="card__head">
            <div><h3>Cleanup activity</h3><span class="sub">Posts handled over the last 14 days</span></div>
            <span class="spacer"></span>
            <div class="chart__legend">
              <span><i style="background:var(--primary)"></i>Deleted</span>
              <span><i style="background:var(--warn)"></i>Pending</span>
              <span><i style="background:var(--danger)"></i>Flagged</span>
            </div>
          </div>
          <div class="card__body"><div class="skeleton" style="height:148px"></div></div>
        </div>
        <div class="card" data-groups-card>
          <div class="card__head"><div><h3>Groups by queue size</h3><span class="sub">Where the noise is coming from</span></div></div>
          <div class="card__body"><div class="skeleton" style="height:180px"></div></div>
        </div>
      </div>
      <div class="stack">
        <div class="card">
          <div class="card__head"><div><h3>Quick actions</h3></div></div>
          <div class="card__body stack" style="gap:9px">
            <a class="quickaction" href="#/pending">
              <span class="quickaction__icon">${icon('inbox')}</span>
              <span><b>Clear the pending queue</b><span>Approve or decline posts waiting on you</span></span>
            </a>
            <a class="quickaction" href="#/flagged">
              <span class="quickaction__icon" style="background:var(--danger-soft);color:var(--danger)">${icon('flag')}</span>
              <span><b>Review reported posts</b><span>Content members flagged for you</span></span>
            </a>
            <a class="quickaction" href="#/cleaner">
              <span class="quickaction__icon">${icon('broom')}</span>
              <span><b>Bulk delete by filter</b><span>Keyword, link, age, author or reports</span></span>
            </a>
            <a class="quickaction" href="#/rules">
              <span class="quickaction__icon">${icon('rule')}</span>
              <span><b>Tune your cleanup rules</b><span>Preview before anything is removed</span></span>
            </a>
          </div>
        </div>
        <div class="card" data-spam-card>
          <div class="card__head"><div><h3>Top spam signals</h3><span class="sub">Patterns in your live posts</span></div></div>
          <div class="card__body"><div class="skeleton" style="height:140px"></div></div>
        </div>
        <div class="card" data-feed-card>
          <div class="card__head">
            <div><h3>Recent activity</h3></div>
            <span class="spacer"></span>
            <a class="btn btn--sm btn--ghost" href="#/activity">View all</a>
          </div>
          <div class="card__body"><div class="skeleton" style="height:150px"></div></div>
        </div>
      </div>
    </div>`;

  view.querySelector('[data-run-auto]').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = `${icon('refresh', 'icon-sm')} Running…`;
    try {
      const result = await api.runAllRules();
      toast({
        kind: result.affected ? 'success' : 'info',
        title: result.affected ? `Removed ${plural(result.affected, 'post')}` : 'Nothing to clean',
        text: `Ran ${result.rules} enabled rule(s).`,
      });
      await render(view, { params });
    } catch (error) {
      toast({ kind: 'error', title: 'Cleanup failed', text: error.message });
      button.disabled = false;
      button.innerHTML = `${icon('sparkle', 'icon-sm')} Run cleanup rules`;
    }
  });

  try {
    const [stats, timeline, groups, activity] = await Promise.all([
      store.loadStats(true),
      api.timeline(14),
      store.loadGroups(true),
      api.activity({ per_page: 7 }),
    ]);

    view.querySelector('[data-group-count]').textContent = groups.length;
    paintStats(view, stats);
    paintChart(view, timeline.items);
    paintGroups(view, stats.top_groups);
    paintSpam(view, stats.spam_patterns, stats.posts.live);
    paintFeed(view, activity.items);
  } catch (error) {
    view.innerHTML = `
      <div class="card">${emptyState({
        icon: 'alert', title: 'Could not load the dashboard',
        message: error.message,
        actions: '<button class="btn btn--primary" onclick="location.reload()">Reload</button>',
      })}</div>`;
  }
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'morning';
  if (hour < 18) return 'afternoon';
  return 'evening';
}

function paintStats(view, stats) {
  const cards = [
    {
      label: 'Live posts', icon: 'posts', value: stats.posts.live, accent: 'var(--primary)',
      meta: `<b>${stats.posts.published}</b> published · <b>${stats.posts.scheduled}</b> scheduled`,
    },
    {
      label: 'Pending queue', icon: 'inbox', value: stats.posts.pending, accent: 'var(--warn)',
      meta: stats.posts.pending ? 'Waiting on your approval' : 'Queue is clear 🎉',
    },
    {
      label: 'Flagged & reported', icon: 'flag', value: stats.posts.flagged, accent: 'var(--danger)',
      meta: `<b>${compactNumber(stats.engagement.reports)}</b> member reports total`,
    },
    {
      label: 'In trash', icon: 'trash', value: stats.posts.trashed, accent: 'var(--text-3)',
      meta: `Restorable · <b>${compactNumber(stats.posts.purged)}</b> jobs run`,
    },
  ];

  view.querySelector('[data-stats]').innerHTML = `
    <div class="grid grid--stats">
      ${cards.map((card) => `
        <div class="stat" style="--accent:${card.accent}">
          <div class="stat__label">${icon(card.icon, 'icon-sm')} ${card.label}</div>
          <div class="stat__value">${compactNumber(card.value)}</div>
          <div class="stat__meta">${card.meta}</div>
        </div>`).join('')}
    </div>
    <div class="grid grid--stats" style="margin-top:16px">
      <div class="stat" style="--accent:var(--success)">
        <div class="stat__label">${icon('shield', 'icon-sm')} Workspace health</div>
        <div class="stat__value">${stats.cleanup.health}<span style="font-size:15px;color:var(--text-3)">/100</span></div>
        <div class="progress" style="margin-top:6px"><div class="progress__fill" style="width:${stats.cleanup.health}%;background:var(--success)"></div></div>
      </div>
      <div class="stat" style="--accent:var(--info)">
        <div class="stat__label">${icon('rule', 'icon-sm')} Active rules</div>
        <div class="stat__value">${stats.cleanup.rules_enabled}<span style="font-size:15px;color:var(--text-3)">/${stats.cleanup.rules_total}</span></div>
        <div class="stat__meta"><b>${compactNumber(stats.cleanup.auto_removed)}</b> posts auto-removed</div>
      </div>
      <div class="stat" style="--accent:#8b5cf6">
        <div class="stat__label">${icon('users', 'icon-sm')} Members reached</div>
        <div class="stat__value">${compactNumber(stats.groups.members)}</div>
        <div class="stat__meta"><b>${stats.groups.connected}</b> of ${stats.groups.total} groups connected</div>
      </div>
      <div class="stat" style="--accent:var(--warn)">
        <div class="stat__label">${icon('comment', 'icon-sm')} Engagement</div>
        <div class="stat__value">${compactNumber(stats.engagement.likes + stats.engagement.comments)}</div>
        <div class="stat__meta"><b>${compactNumber(stats.engagement.shares)}</b> shares · ${compactNumber(stats.engagement.reports)} reports</div>
      </div>
    </div>`;
}

function paintChart(view, items) {
  const peak = Math.max(1, ...items.map((day) => day.deleted + day.pending + day.flagged));
  const host = view.querySelector('[data-chart-card] .card__body');
  host.innerHTML = `
    <div class="chart">
      ${items.map((day) => {
        const scale = (value) => Math.round((value / peak) * 108);
        return `
          <div class="chart__col" title="${esc(dayLabel(day.date))}: ${day.deleted} deleted, ${day.pending} pending, ${day.flagged} flagged">
            <div class="chart__bar chart__bar--flagged" style="height:${scale(day.flagged)}px"></div>
            <div class="chart__bar chart__bar--pending" style="height:${scale(day.pending)}px"></div>
            <div class="chart__bar chart__bar--deleted" style="height:${Math.max(day.deleted ? 2 : 0, scale(day.deleted))}px"></div>
            <div class="chart__label">${esc(dayLabel(day.date).split(' ')[1])}</div>
          </div>`;
      }).join('')}
    </div>`;
}

function paintGroups(view, topGroups) {
  const host = view.querySelector('[data-groups-card] .card__body');
  if (!topGroups.length) {
    host.innerHTML = emptyState({
      icon: 'users', title: 'No groups connected yet',
      message: 'Connect a Facebook group to start pulling its posts into the queue.',
      actions: '<a class="btn btn--primary" href="#/groups">Connect a group</a>',
    });
    return;
  }
  const max = Math.max(...topGroups.map((group) => group.posts || 1));
  host.innerHTML = `
    <table class="table table--tight">
      <thead><tr><th>Group</th><th class="num">Posts</th><th class="num">Pending</th><th class="num">Flagged</th></tr></thead>
      <tbody>
        ${topGroups.map((group) => `
          <tr>
            <td>
              <a href="#/posts?group=${group.id}" class="strong" style="color:var(--text)">${esc(group.name)}</a>
              <div class="bar-row__track" style="margin-top:5px">
                <div class="bar-row__fill" style="width:${Math.round((group.posts / max) * 100)}%"></div>
              </div>
            </td>
            <td class="num">${group.posts}</td>
            <td class="num">${group.pending ? `<span class="badge badge--pending">${group.pending}</span>` : '<span class="muted">0</span>'}</td>
            <td class="num">${group.flagged ? `<span class="badge badge--flagged">${group.flagged}</span>` : '<span class="muted">0</span>'}</td>
          </tr>`).join('')}
      </tbody>
    </table>`;
}

function paintSpam(view, patterns, live) {
  const host = view.querySelector('[data-spam-card] .card__body');
  if (!patterns?.length) {
    host.innerHTML = emptyState({ icon: 'shield', title: 'No spam signals', message: 'Nothing suspicious in the live feed.', success: true });
    return;
  }
  const max = Math.max(...patterns.map((item) => item.count), 1);
  host.innerHTML = patterns.map((item) => `
    <div class="bar-row">
      <span class="small">${esc(item.label)}</span>
      <span class="small muted">${item.count} · ${live ? Math.round((item.count / live) * 100) : 0}%</span>
      <div class="bar-row__track">
        <div class="bar-row__fill" style="width:${Math.round((item.count / max) * 100)}%;--fill:${item.count > 8 ? 'var(--danger)' : 'var(--warn)'}"></div>
      </div>
    </div>`).join('');
}

function paintFeed(view, items) {
  const host = view.querySelector('[data-feed-card] .card__body');
  if (!items.length) {
    host.innerHTML = emptyState({ icon: 'history', title: 'No activity yet', message: 'Actions you take will show up here.' });
    return;
  }
  const colors = {
    'post.deleted': 'var(--danger)', 'post.purged': 'var(--danger)', 'post.declined': 'var(--danger)',
    'post.approved': 'var(--success)', 'post.restored': 'var(--success)',
    'rule.ran': 'var(--primary)', 'rule.created': 'var(--primary)',
    'group.connected': 'var(--info)', 'group.synced': 'var(--info)',
  };
  host.innerHTML = `<div class="timeline">
    ${items.map((entry) => `
      <div class="tl-item">
        <span class="tl-item__dot" style="--dot:${colors[entry.action] || 'var(--text-3)'}"></span>
        <div class="tl-item__head">
          <span class="strong" style="font-size:12.5px">${esc(entry.action.replace(/\./g, ' · '))}</span>
          <span class="tl-item__when">${esc(relTime(entry.created_at))}</span>
        </div>
        <div class="tl-item__detail">${esc(entry.target_label)}${entry.group_name ? ` <span class="muted">in ${esc(entry.group_name)}</span>` : ''}</div>
      </div>`).join('')}
  </div>`;
}
