/**
 * MyTube API Client
 * Wraps REST calls to /api endpoints
 */
const API_BASE = '/api';

const api = {
  async getHomeFeed(limit = 50, offset = 0, unplayedOnly = true) {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
      unplayed_only: unplayedOnly ? 'true' : 'false'
    });
    const res = await fetch(`${API_BASE}/home?${params}`);
    if (!res.ok) throw new Error(`Failed to fetch home feed: ${res.statusText}`);
    return await res.json();
  },

  async getChannels() {
    const res = await fetch(`${API_BASE}/channels`);
    if (!res.ok) throw new Error(`Failed to fetch channels: ${res.statusText}`);
    return await res.json();
  },

  async getChannelDetail(channelId) {
    const res = await fetch(`${API_BASE}/channels/${encodeURIComponent(channelId)}`);
    if (!res.ok) throw new Error(`Failed to fetch channel details: ${res.statusText}`);
    return await res.json();
  },

  async getChannelVideos(channelId, filterType = 'all', limit = 50, offset = 0) {
    const params = new URLSearchParams({
      filter_type: filterType,
      limit: limit.toString(),
      offset: offset.toString()
    });
    const res = await fetch(`${API_BASE}/channels/${encodeURIComponent(channelId)}/videos?${params}`);
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
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to fetch playback info: ${res.statusText}`);
    return await res.json();
  },

  async reportProgress(videoId, position, duration, syncToJellyfin = false) {
    try {
      const res = await fetch(`${API_BASE}/videos/${encodeURIComponent(videoId)}/progress`, {
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
    const res = await fetch(`${API_BASE}/videos/${encodeURIComponent(videoId)}/watched`, {
      method: 'POST'
    });
    return await res.json();
  },

  async markUnwatched(videoId) {
    const res = await fetch(`${API_BASE}/videos/${encodeURIComponent(videoId)}/unwatched`, {
      method: 'POST'
    });
    return await res.json();
  },

  async moveToTrash(videoId) {
    const res = await fetch(`${API_BASE}/videos/${encodeURIComponent(videoId)}/trash`, {
      method: 'POST'
    });
    return await res.json();
  },

  async restoreFromTrash(videoId) {
    const res = await fetch(`${API_BASE}/videos/${encodeURIComponent(videoId)}/restore`, {
      method: 'POST'
    });
    return await res.json();
  },

  async deletePermanently(videoId) {
    const res = await fetch(`${API_BASE}/videos/${encodeURIComponent(videoId)}`, {
      method: 'DELETE'
    });
    return await res.json();
  },

  async getTrash() {
    const res = await fetch(`${API_BASE}/trash`);
    if (!res.ok) throw new Error(`Failed to fetch trash: ${res.statusText}`);
    return await res.json();
  },

  async search(query) {
    const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error(`Search failed: ${res.statusText}`);
    return await res.json();
  },

  async getMoviesHome() {
    const res = await fetch(`${API_BASE}/movies/home`);
    if (!res.ok) throw new Error(`Failed to fetch movies home: ${res.statusText}`);
    return await res.json();
  },

  async getMovieDetail(movieId) {
    const res = await fetch(`${API_BASE}/movies/${encodeURIComponent(movieId)}`);
    if (!res.ok) throw new Error(`Failed to fetch movie detail: ${res.statusText}`);
    return await res.json();
  },

  async getShowsHome() {
    const res = await fetch(`${API_BASE}/shows/home`);
    if (!res.ok) throw new Error(`Failed to fetch shows home: ${res.statusText}`);
    return await res.json();
  },

  async getShowDetail(showId) {
    const res = await fetch(`${API_BASE}/shows/${encodeURIComponent(showId)}`);
    if (!res.ok) throw new Error(`Failed to fetch show detail: ${res.statusText}`);
    return await res.json();
  },

  async getStats() {
    const res = await fetch(`${API_BASE}/stats`);
    if (!res.ok) throw new Error(`Failed to fetch stats: ${res.statusText}`);
    return await res.json();
  },

  async triggerScan() {
    const res = await fetch(`${API_BASE}/admin/scan`, { method: 'POST' });
    return await res.json();
  },

  async triggerCleanup() {
    const res = await fetch(`${API_BASE}/admin/cleanup`, { method: 'POST' });
    return await res.json();
  }
};
