/**
 * MyTube API Client
 * Wraps REST calls to /api endpoints
 */
const API_BASE = '/api';
const USER_ID_KEY = 'mytube.userId';
const USER_NAME_KEY = 'mytube.userName';

// Strips the "sYYYY.eMMDDxx - " or "YYYY-MM-DD - " prefix added by the scraper.
function cleanVideoTitle(title) {
  if (!title) return '';
  const cleaned = title.replace(/^(?:s\d{4}\.e?\d+\S*|\d{4}-\d{2}-\d{2})\s*-\s*/i, '').trim();
  return cleaned || title;
}

const api = {
  getUserId() {
    return localStorage.getItem(USER_ID_KEY);
  },

  getUserName() {
    return localStorage.getItem(USER_NAME_KEY);
  },

  setUser(user) {
    localStorage.setItem(USER_ID_KEY, user.user_id);
    localStorage.setItem(USER_NAME_KEY, user.name);
  },

  clearUser() {
    localStorage.removeItem(USER_ID_KEY);
    localStorage.removeItem(USER_NAME_KEY);
  },

  /**
   * Sends X-MyTube-User on every /api request except /api/users*.
   * A 400/404 whose detail mentions the user means the stored user is invalid,
   * so 'mytube:user-invalid' is dispatched to return to user selection.
   */
  async request(path, options = {}) {
    const isUsersRoute = path.startsWith(`${API_BASE}/users`);
    const headers = new Headers(options.headers || {});
    const userId = this.getUserId();
    if (!isUsersRoute && userId) {
      headers.set('X-MyTube-User', userId);
    }

    const res = await fetch(path, { ...options, headers });

    if (!isUsersRoute && (res.status === 400 || res.status === 404)) {
      const body = await res.clone().json().catch(() => null);
      if (body && typeof body.detail === 'string' && /user/i.test(body.detail)) {
        window.dispatchEvent(new CustomEvent('mytube:user-invalid'));
      }
    }
    return res;
  },

  async getUsers() {
    const res = await this.request(`${API_BASE}/users`);
    if (!res.ok) throw new Error(`Failed to fetch users: ${res.statusText}`);
    return await res.json();
  },

  async createUser(name) {
    const res = await this.request(`${API_BASE}/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(typeof body.detail === 'string' ? body.detail : `Failed to create user: ${res.statusText}`);
    }
    return body;
  },

  async deleteUser(userId) {
    const res = await this.request(`${API_BASE}/users/${encodeURIComponent(userId)}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`Failed to delete user: ${res.statusText}`);
  },

  async setChannelSubscription(channelId, subscribed) {
    const res = await this.request(`${API_BASE}/channels/${encodeURIComponent(channelId)}/subscription`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subscribed })
    });
    if (!res.ok) throw new Error(`Failed to update subscription: ${res.statusText}`);
    return await res.json();
  },

  async getScraperChannels() {
    const res = await this.request(`${API_BASE}/scraper/channels`);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Failed to fetch scraper channels: ${res.statusText}`);
    return body.channels;
  },

  /** Adds a channel when originalName is null, otherwise replaces the channel with that name. */
  async saveScraperChannel(channel, originalName = null) {
    const isNew = originalName === null;
    const path = isNew
      ? `${API_BASE}/scraper/channels`
      : `${API_BASE}/scraper/channels/${encodeURIComponent(originalName)}`;
    const res = await this.request(path, {
      method: isNew ? 'POST' : 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(channel)
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Failed to save channel: ${res.statusText}`);
    return body;
  },

  async deleteScraperChannel(name) {
    const res = await this.request(`${API_BASE}/scraper/channels/${encodeURIComponent(name)}`, { method: 'DELETE' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(typeof body.detail === 'string' ? body.detail : `Failed to remove channel: ${res.statusText}`);
    }
  },

  async getHomeFeed(limit = 50, offset = 0, unplayedOnly = true) {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
      unplayed_only: unplayedOnly ? 'true' : 'false'
    });
    const res = await this.request(`${API_BASE}/home?${params}`);
    if (!res.ok) throw new Error(`Failed to fetch home feed: ${res.statusText}`);
    return await res.json();
  },

  async getGoneSoon(limit = 10, offset = 0, unplayedOnly = true) {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
      unplayed_only: unplayedOnly ? 'true' : 'false'
    });
    const res = await this.request(`${API_BASE}/gone-soon?${params}`);
    if (!res.ok) throw new Error(`Failed to fetch gone-soon videos: ${res.statusText}`);
    return await res.json();
  },

  async getContinueWatching(limit = 50, offset = 0) {
    const params = new URLSearchParams({ limit: limit.toString(), offset: offset.toString() });
    const res = await this.request(`${API_BASE}/continue-watching?${params}`);
    if (!res.ok) throw new Error(`Failed to fetch continue watching: ${res.statusText}`);
    return await res.json();
  },

  async getChannels(subscription = 'all') {
    const params = new URLSearchParams({ subscription });
    const res = await this.request(`${API_BASE}/channels?${params}`);
    if (!res.ok) throw new Error(`Failed to fetch channels: ${res.statusText}`);
    return await res.json();
  },

  async getChannelDetail(channelId) {
    const res = await this.request(`${API_BASE}/channels/${encodeURIComponent(channelId)}`);
    if (!res.ok) throw new Error(`Failed to fetch channel details: ${res.statusText}`);
    return await res.json();
  },

  async getChannelVideos(channelId, filterType = 'all', limit = 50, offset = 0) {
    const params = new URLSearchParams({
      filter_type: filterType,
      limit: limit.toString(),
      offset: offset.toString()
    });
    const res = await this.request(`${API_BASE}/channels/${encodeURIComponent(channelId)}/videos?${params}`);
    if (!res.ok) throw new Error(`Failed to fetch channel videos: ${res.statusText}`);
    return await res.json();
  },

  async getPlayback(videoId, audioStreamIndex = null, quality = null) {
    const params = new URLSearchParams();
    if (audioStreamIndex !== null && audioStreamIndex !== undefined) {
      params.set('audio_stream_index', audioStreamIndex);
    }
    if (quality) {
      params.set('quality', quality);
    }
    const qStr = params.toString();
    const url = `${API_BASE}/videos/${encodeURIComponent(videoId)}/playback${qStr ? '?' + qStr : ''}`;
    const res = await this.request(url);
    if (!res.ok) throw new Error(`Failed to fetch playback info: ${res.statusText}`);
    return await res.json();
  },

  async synthesizeSubtitle(videoId, subtitleIndex) {
    const res = await this.request(`${API_BASE}/videos/${encodeURIComponent(videoId)}/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subtitle_index: subtitleIndex }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `AI synthesis failed: ${res.statusText}`);
    return body;
  },

  async reportProgress(videoId, position, duration, syncToJellyfin = false) {
    try {
      const res = await this.request(`${API_BASE}/videos/${encodeURIComponent(videoId)}/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position, duration, sync_to_jellyfin: syncToJellyfin }),
        keepalive: true
      });
      return await res.json();
    } catch (e) {
      console.warn('Progress report failed:', e);
      return null;
    }
  },

  async markWatched(videoId) {
    const res = await this.request(`${API_BASE}/videos/${encodeURIComponent(videoId)}/watched`, {
      method: 'POST'
    });
    return await res.json();
  },

  async markUnwatched(videoId) {
    const res = await this.request(`${API_BASE}/videos/${encodeURIComponent(videoId)}/unwatched`, {
      method: 'POST'
    });
    return await res.json();
  },

  async deletePermanently(videoId) {
    const res = await this.request(`${API_BASE}/videos/${encodeURIComponent(videoId)}`, {
      method: 'DELETE'
    });
    return await res.json();
  },

  async search(query) {
    const res = await this.request(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error(`Search failed: ${res.statusText}`);
    return await res.json();
  },

  async getMoviesHome(filterType = 'all') {
    const params = new URLSearchParams({ filter_type: filterType });
    const res = await this.request(`${API_BASE}/movies/home?${params}`);
    if (!res.ok) throw new Error(`Failed to fetch movies home: ${res.statusText}`);
    return await res.json();
  },

  async getMovieDetail(movieId) {
    const res = await this.request(`${API_BASE}/movies/${encodeURIComponent(movieId)}`);
    if (!res.ok) throw new Error(`Failed to fetch movie detail: ${res.statusText}`);
    return await res.json();
  },

  async getShowsHome() {
    const res = await this.request(`${API_BASE}/shows/home`);
    if (!res.ok) throw new Error(`Failed to fetch shows home: ${res.statusText}`);
    return await res.json();
  },

  async getShowDetail(showId) {
    const res = await this.request(`${API_BASE}/shows/${encodeURIComponent(showId)}`);
    if (!res.ok) throw new Error(`Failed to fetch show detail: ${res.statusText}`);
    return await res.json();
  },

  async getStats() {
    const res = await this.request(`${API_BASE}/stats`);
    if (!res.ok) throw new Error(`Failed to fetch stats: ${res.statusText}`);
    return await res.json();
  },

  async triggerScan() {
    const res = await this.request(`${API_BASE}/admin/scan`, { method: 'POST' });
    return await res.json();
  }
};
