/**
 * Thin fetch wrapper around the REST API.
 *
 * - keeps the bearer token in localStorage
 * - normalises FastAPI errors into `ApiError`
 * - fires `auth:expired` so the shell can bounce back to the login screen
 */
const TOKEN_KEY = 'gpc.token';
const BASE = '';

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (value) => localStorage.setItem(TOKEN_KEY, value),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

function extractMessage(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload.detail === 'string') return payload.detail;
  if (Array.isArray(payload.detail) && payload.detail.length) {
    // FastAPI/pydantic validation errors
    return payload.detail
      .map((issue) => {
        const where = (issue.loc || []).filter((p) => p !== 'body').join(' → ');
        return where ? `${where}: ${issue.msg}` : issue.msg;
      })
      .join(' · ');
  }
  if (payload.detail && typeof payload.detail === 'object') return JSON.stringify(payload.detail);
  return fallback;
}

async function request(method, path, body, options = {}) {
  const headers = {};
  const bearer = token.get();
  if (bearer) headers.Authorization = `Bearer ${bearer}`;

  let payload;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(BASE + path, { method, headers, body: payload, ...options });
  } catch (networkError) {
    throw new ApiError('Cannot reach the server — check your connection.', 0, networkError);
  }

  if (response.status === 204 || response.status === 205) return null;

  const isJson = (response.headers.get('content-type') || '').includes('application/json');
  const data = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    if (response.status === 401 && bearer) {
      token.clear();
      onUnauthorized();
    }
    throw new ApiError(extractMessage(data, `${response.status} ${response.statusText}`), response.status, data);
  }
  return data;
}

export const api = {
  get: (path, options) => request('GET', path, undefined, options),
  post: (path, body, options) => request('POST', path, body ?? {}, options),
  patch: (path, body, options) => request('PATCH', path, body ?? {}, options),
  del: (path, options) => request('DELETE', path, undefined, options),

  // ---- auth
  login: (email, password) => request('POST', '/api/auth/login', { email, password }),
  register: (payload) => request('POST', '/api/auth/register', payload),
  me: () => request('GET', '/api/auth/me'),
  logout: () => request('POST', '/api/auth/logout'),
  updateProfile: (payload) => request('PATCH', '/api/auth/me', payload),
  changePassword: (payload) => request('POST', '/api/auth/change-password', payload),

  // ---- groups
  groups: (params) => request('GET', `/api/groups${qs(params)}`),
  createGroup: (payload) => request('POST', '/api/groups', payload),
  updateGroup: (id, payload) => request('PATCH', `/api/groups/${id}`, payload),
  deleteGroup: (id) => request('DELETE', `/api/groups/${id}`),
  syncGroup: (id) => request('POST', `/api/groups/${id}/sync`),
  groupHealth: (id) => request('GET', `/api/groups/${id}/health`),

  // ---- posts
  posts: (params) => request('GET', `/api/posts${qs(params)}`),
  trash: (params) => request('GET', `/api/posts/trash${qs(params)}`),
  post: (id) => request('GET', `/api/posts/${id}`),
  createPost: (payload) => request('POST', '/api/posts', payload),
  updatePost: (id, payload) => request('PATCH', `/api/posts/${id}`, payload),
  deletePost: (id) => request('DELETE', `/api/posts/${id}`),
  restorePost: (id) => request('POST', `/api/posts/${id}/restore`),
  purgePost: (id) => request('POST', `/api/posts/${id}/purge`),
  bulk: (payload) => request('POST', '/api/posts/bulk', payload),
  bulkFilter: (payload) => request('POST', '/api/posts/bulk-filter', payload),
  emptyTrash: (params) => request('DELETE', `/api/posts/trash${qs(params)}`),

  // ---- rules
  rules: (params) => request('GET', `/api/rules${qs(params)}`),
  createRule: (payload) => request('POST', '/api/rules', payload),
  updateRule: (id, payload) => request('PATCH', `/api/rules/${id}`, payload),
  deleteRule: (id) => request('DELETE', `/api/rules/${id}`),
  toggleRule: (id) => request('POST', `/api/rules/${id}/toggle`),
  runRule: (id, dryRun = false) => request('POST', `/api/rules/${id}/run`, { dry_run: dryRun }),
  previewRule: (id) => request('GET', `/api/rules/${id}/preview`),
  dryRunRule: (payload) => request('POST', '/api/rules/dry-run', payload),
  runAllRules: () => request('POST', '/api/rules/run-all'),

  // ---- authors
  authors: (params) => request('GET', `/api/authors${qs(params)}`),
  createAuthor: (payload) => request('POST', '/api/authors', payload),
  updateAuthor: (id, payload) => request('PATCH', `/api/authors/${id}`, payload),
  deleteAuthor: (id) => request('DELETE', `/api/authors/${id}`),
  banAuthor: (id) => request('POST', `/api/authors/${id}/ban`),
  purgeAuthorPosts: (id) => request('POST', `/api/authors/${id}/purge-posts`),

  // ---- jobs / activity / stats
  jobs: (params) => request('GET', `/api/jobs${qs(params)}`),
  deleteJob: (id) => request('DELETE', `/api/jobs/${id}`),
  clearJobs: () => request('DELETE', '/api/jobs'),
  activity: (params) => request('GET', `/api/activity${qs(params)}`),
  clearActivity: () => request('DELETE', '/api/activity'),
  stats: () => request('GET', '/api/stats/overview'),
  timeline: (days = 14) => request('GET', `/api/stats/timeline?days=${days}`),
};

/** Build a query string, skipping empty / null / undefined / [] values. */
export function qs(params = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '' || value === false) continue;
    if (Array.isArray(value)) {
      if (value.length) search.set(key, value.join(','));
      continue;
    }
    search.set(key, String(value));
  }
  const out = search.toString();
  return out ? `?${out}` : '';
}
