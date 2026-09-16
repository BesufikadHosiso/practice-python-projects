/**
 * In-memory app state + tiny pub/sub.
 *
 * Pages read through `store` so a delete on one screen can invalidate the
 * caches the other screens depend on, and the sidebar counters stay honest.
 */
import { api, token } from './api.js';

const listeners = new Set();
const THEME_KEY = 'gpc.theme';

export const store = {
  user: null,
  groups: [],
  groupsLoaded: false,
  stats: null,
  counts: { pending: 0, flagged: 0, trashed: 0, live: 0 },
  theme: localStorage.getItem(THEME_KEY)
    || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
  lastSync: null,

  subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },

  emit(event) {
    listeners.forEach((fn) => {
      try { fn(event); } catch (error) { console.error(error); }
    });
  },

  setSession(user) {
    this.user = user;
    this.emit('session');
  },

  clearSession() {
    token.clear();
    this.user = null;
    this.groups = [];
    this.groupsLoaded = false;
    this.stats = null;
    this.counts = { pending: 0, flagged: 0, trashed: 0, live: 0 };
    this.emit('session');
  },

  applyTheme() {
    document.documentElement.dataset.theme = this.theme;
    localStorage.setItem(THEME_KEY, this.theme);
    this.emit('theme');
  },

  toggleTheme() {
    this.theme = this.theme === 'dark' ? 'light' : 'dark';
    this.applyTheme();
  },

  /** Groups are used by nearly every page; load once, reuse everywhere. */
  async loadGroups(force = false) {
    if (this.groupsLoaded && !force) return this.groups;
    const data = await api.groups({ per_page: 200 });
    this.groups = data.items;
    this.groupsLoaded = true;
    this.emit('groups');
    return this.groups;
  },

  groupById(id) {
    return this.groups.find((group) => group.id === Number(id)) || null;
  },

  async loadStats(force = false) {
    if (this.stats && !force) return this.stats;
    this.stats = await api.stats();
    this.counts = {
      pending: this.stats.posts.pending,
      flagged: this.stats.posts.flagged,
      trashed: this.stats.posts.trashed,
      live: this.stats.posts.live,
    };
    this.emit('stats');
    return this.stats;
  },

  /**
   * Locally adjust the dashboard counters after a mutation so the sidebar
   * badge moves instantly; the next `loadStats(true)` reconciles with truth.
   */
  nudge(delta) {
    Object.entries(delta).forEach(([key, value]) => {
      if (typeof this.counts[key] === 'number') {
        this.counts[key] = Math.max(0, this.counts[key] + value);
      }
    });
    if (this.stats) {
      Object.entries(delta).forEach(([key, value]) => {
        if (typeof this.stats.posts[key] === 'number') {
          this.stats.posts[key] = Math.max(0, this.stats.posts[key] + value);
        }
      });
    }
    this.emit('stats');
  },

  invalidateStats() {
    this.stats = null;
  },
};
