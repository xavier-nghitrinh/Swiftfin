/**
 * Music playback engine: queue, shuffle, repeat, play counts, Media Session,
 * and the mini player, now-playing screen and add-to-playlist picker.
 * Uses its own <audio> element, separate from the video Player.
 */

const MusicPlayer = {
  audio: null,
  queue: [],
  sourceOrder: [], // Order the current list was started in; restored when shuffle is turned off
  index: -1,
  shuffleOn: false,
  repeatMode: 'off', // 'off', 'all', 'one'
  countedPlay: false,
  isSeeking: false,
  queueVisible: false,
  pickerTrack: null,
  pickerToken: 0,

  init() {
    this.audio = new Audio();
    this.audio.preload = 'auto';

    this.audio.addEventListener('play', () => this.updatePlayUi());
    this.audio.addEventListener('pause', () => this.updatePlayUi());
    this.audio.addEventListener('ended', () => this.onEnded());
    this.audio.addEventListener('timeupdate', () => this.onTimeUpdate());
    this.audio.addEventListener('loadedmetadata', () => this.refreshProgress());
    this.audio.addEventListener('error', () => {
      if (!this.audio.getAttribute('src')) return;
      App.showToast('Could not play this track');
      this.updatePlayUi();
    });

    document.getElementById('music-mini-open').addEventListener('click', () => this.openNow());
    document.getElementById('music-mini-prev').addEventListener('click', () => this.previous());
    document.getElementById('music-mini-toggle').addEventListener('click', () => this.togglePlay());
    document.getElementById('music-mini-next').addEventListener('click', () => this.next());

    const miniProgress = document.getElementById('music-mini-progress');
    miniProgress.addEventListener('pointerdown', (event) => this.startProgressDrag(event));
    miniProgress.addEventListener('pointermove', (event) => this.moveProgressDrag(event));
    miniProgress.addEventListener('pointerup', (event) => this.endProgressDrag(event, true));
    miniProgress.addEventListener('pointercancel', (event) => this.endProgressDrag(event, false));
    document.getElementById('music-now-close').addEventListener('click', () => this.closeNow());
    document.getElementById('music-now-queue-toggle').addEventListener('click', () => this.toggleQueue());
    document.getElementById('music-now-toggle').addEventListener('click', () => this.togglePlay());
    document.getElementById('music-now-prev').addEventListener('click', () => this.previous());
    document.getElementById('music-now-next').addEventListener('click', () => this.next());
    document.getElementById('music-shuffle').addEventListener('click', () => this.toggleShuffle());
    document.getElementById('music-repeat').addEventListener('click', () => this.cycleRepeat());
    document.getElementById('music-now-favorite').addEventListener('click', () => this.toggleFavorite(this.current()));
    document.getElementById('music-now-add').addEventListener('click', () => this.openPicker(this.current()));
    document.getElementById('music-now-artist').addEventListener('click', () => this.openArtist());

    const seek = document.getElementById('music-seek');
    seek.addEventListener('input', () => {
      this.isSeeking = true;
      const duration = this.duration();
      document.getElementById('music-time-cur').textContent = this.formatTime((seek.value / 1000) * duration);
    });
    seek.addEventListener('change', () => {
      const duration = this.duration();
      if (duration > 0) this.audio.currentTime = (seek.value / 1000) * duration;
      this.isSeeking = false;
    });

    document.getElementById('music-picker-close').addEventListener('click', () => this.closePicker());
    document.getElementById('music-picker').addEventListener('click', (event) => {
      if (event.target.id === 'music-picker') this.closePicker();
    });
    document.getElementById('music-picker-new').addEventListener('submit', (event) => this.submitNewPlaylist(event));

    this.updateShuffleUi();
    this.updateRepeatUi();
  },

  // =========================================================
  // Public API
  // =========================================================
  // startIndex null picks a random track when shuffling; the chosen track
  // plays first and the rest of the list follows in random order.
  playList(tracks, startIndex = null, { shuffle = false } = {}) {
    if (!tracks || !tracks.length) return;
    if (Player.isActive) Player.stop();

    this.sourceOrder = tracks.slice();
    this.shuffleOn = shuffle;
    const requested = startIndex ?? (shuffle ? Math.floor(Math.random() * tracks.length) : 0);
    let start = Math.min(Math.max(requested, 0), tracks.length - 1);
    if (shuffle) {
      const rest = tracks.filter((_, i) => i !== start);
      this.queue = [tracks[start], ...this.shuffleArray(rest)];
      start = 0;
    } else {
      this.queue = tracks.slice();
    }
    this.index = start;
    this.updateShuffleUi();
    this.loadCurrent(true);
  },

  pause() {
    if (this.audio) this.audio.pause();
  },

  stop() {
    if (!this.audio) return;
    this.audio.pause();
    this.audio.removeAttribute('src');
    this.audio.load();
    this.queue = [];
    this.sourceOrder = [];
    this.index = -1;
    this.countedPlay = false;
    this.closePicker();
    this.closeNow();
    document.getElementById('music-mini').style.display = 'none';
    document.body.classList.remove('music-active');
    if ('mediaSession' in navigator) navigator.mediaSession.metadata = null;
    this.renderQueue();
  },

  enqueue(track, playNext = false) {
    if (!track) return;
    if (!this.queue.length) {
      this.playList([track], 0);
      return;
    }
    if (playNext) this.queue.splice(this.index + 1, 0, track);
    else this.queue.push(track);
    this.renderQueue();
    App.showToast(playNext ? 'Will play next' : 'Added to queue');
  },

  async toggleFavorite(track) {
    if (!track) return;
    try {
      const res = await api.setMusicFavorite(track.track_id, !track.favorite);
      track.favorite = !!res.favorite;
      this.updateFavoriteUi();
      window.dispatchEvent(new CustomEvent('mytube:music-changed', {
        detail: { trackId: track.track_id, favorite: track.favorite }
      }));
    } catch (err) {
      App.showToast('Could not update favorites');
    }
  },

  openPicker(track) {
    if (!track) return;
    this.pickerTrack = track;
    const token = ++this.pickerToken;
    const list = document.getElementById('music-picker-list');
    list.replaceChildren(
      this.pickerItem('Play next', () => {
        this.enqueue(track, true);
        this.closePicker();
      }),
      this.pickerItem('Add to queue', () => {
        this.enqueue(track, false);
        this.closePicker();
      })
    );
    document.getElementById('music-picker').style.display = 'flex';
    this.loadPickerPlaylists(token);
  },

  // =========================================================
  // Queue and playback
  // =========================================================
  current() {
    return this.queue[this.index] || null;
  },

  duration(track = this.current()) {
    if (Number.isFinite(this.audio.duration) && this.audio.duration > 0) return this.audio.duration;
    return (track && track.duration) || 0;
  },

  loadCurrent(autoplay) {
    const track = this.current();
    if (!track) return;
    this.countedPlay = false;
    this.audio.src = track.stream_url;
    this.audio.currentTime = 0;

    document.getElementById('music-mini').style.display = 'flex';
    document.body.classList.add('music-active');
    this.updateMeta(track);
    this.refreshProgress();
    this.renderQueue();

    if (autoplay) {
      this.audio.play().catch((err) => this.onPlayError(err));
    } else {
      this.updatePlayUi();
    }
  },

  onPlayError(err) {
    if (err && err.name === 'AbortError') return;
    App.showToast('Could not play this track');
    this.updatePlayUi();
  },

  togglePlay() {
    if (!this.current()) return;
    if (this.audio.paused) {
      this.audio.play().catch((err) => this.onPlayError(err));
    } else {
      this.audio.pause();
    }
  },

  next() {
    if (!this.queue.length) return;
    if (this.index + 1 < this.queue.length) {
      this.index++;
      this.loadCurrent(true);
    } else if (this.repeatMode === 'all') {
      this.index = 0;
      this.loadCurrent(true);
    } else {
      this.audio.pause();
      this.audio.currentTime = 0;
      this.refreshProgress();
    }
  },

  previous() {
    if (!this.queue.length) return;
    if (this.audio.currentTime > 3 || this.index === 0) {
      this.audio.currentTime = 0;
      return;
    }
    this.index--;
    this.loadCurrent(true);
  },

  onEnded() {
    if (this.repeatMode === 'one') {
      this.loadCurrent(true);
      return;
    }
    if (this.index + 1 < this.queue.length || this.repeatMode === 'all') {
      this.next();
      return;
    }
    this.updatePlayUi();
  },

  onTimeUpdate() {
    const track = this.current();
    if (!track) return;
    const duration = this.duration(track);
    // Count a play once the listener has heard half the track, or 30 seconds, whichever is less
    const threshold = duration > 0 ? Math.min(30, duration * 0.5) : 30;
    if (!this.countedPlay && this.audio.currentTime >= threshold) {
      this.countedPlay = true;
      this.recordPlay(track);
    }
    if (!this.isSeeking) this.refreshProgress();
  },

  recordPlay(track) {
    api.recordMusicPlay(track.track_id)
      .then(() => {
        track.play_count = (track.play_count || 0) + 1;
        track.last_played_at = new Date().toISOString();
      })
      .catch((err) => console.warn('Failed to record play:', err));
  },

  // =========================================================
  // Shuffle and repeat
  // =========================================================
  toggleShuffle() {
    if (!this.queue.length) return;
    this.shuffleOn = !this.shuffleOn;
    const head = this.queue.slice(0, this.index + 1);
    let upcoming = this.queue.slice(this.index + 1);
    if (this.shuffleOn) {
      upcoming = this.shuffleArray(upcoming);
    } else {
      const rank = (track) => {
        const i = this.sourceOrder.findIndex((s) => s.track_id === track.track_id);
        return i < 0 ? Infinity : i;
      };
      upcoming = upcoming
        .map((track, i) => ({ track, i }))
        .sort((a, b) => (rank(a.track) - rank(b.track)) || (a.i - b.i))
        .map((entry) => entry.track);
    }
    this.queue = [...head, ...upcoming];
    this.updateShuffleUi();
    this.renderQueue();
  },

  cycleRepeat() {
    const order = ['off', 'all', 'one'];
    this.repeatMode = order[(order.indexOf(this.repeatMode) + 1) % order.length];
    this.updateRepeatUi();
  },

  shuffleArray(items) {
    const copy = items.slice();
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
  },

  // =========================================================
  // UI: mini player, now-playing screen, queue
  // =========================================================
  updateMeta(track) {
    const art = track.image_url || '';
    document.getElementById('music-mini-title').textContent = track.title;
    document.getElementById('music-mini-artist').textContent = track.artist || '';
    document.getElementById('music-mini-art').src = art;
    document.getElementById('music-now-title').textContent = track.title;
    const nowArtist = document.getElementById('music-now-artist');
    nowArtist.textContent = track.artist || '';
    nowArtist.disabled = !track.artist;
    document.getElementById('music-now-art').src = art;
    this.updateFavoriteUi();

    if ('mediaSession' in navigator && typeof MediaMetadata !== 'undefined') {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: track.title,
        artist: track.artist || '',
        album: track.source_group || '',
        artwork: art ? [{ src: art, sizes: '512x512', type: 'image/jpeg' }] : []
      });
    }
  },

  updateFavoriteUi() {
    const track = this.current();
    const favorite = !!(track && track.favorite);
    const btn = document.getElementById('music-now-favorite');
    btn.classList.toggle('active', favorite);
    btn.setAttribute('aria-pressed', String(favorite));
  },

  updatePlayUi() {
    const playing = !this.audio.paused && !this.audio.ended;
    const label = playing ? 'Pause' : 'Play';
    ['music-mini-toggle', 'music-now-toggle'].forEach((id) => {
      const btn = document.getElementById(id);
      btn.setAttribute('aria-label', label);
      btn.querySelector('.music-icon-play').style.display = playing ? 'none' : '';
      btn.querySelector('.music-icon-pause').style.display = playing ? '' : 'none';
    });
    if ('mediaSession' in navigator) {
      navigator.mediaSession.playbackState = playing ? 'playing' : 'paused';
      this.bindMediaSession();
    }
  },

  refreshProgress() {
    const duration = this.duration();
    const current = this.audio.currentTime || 0;
    this.renderProgress(current, duration);

    if ('mediaSession' in navigator && typeof navigator.mediaSession.setPositionState === 'function' && duration > 0) {
      try {
        navigator.mediaSession.setPositionState({
          duration,
          playbackRate: this.audio.playbackRate || 1,
          position: Math.min(current, duration)
        });
      } catch (err) {
        console.warn('Failed to update media position:', err);
      }
    }
  },

  renderProgress(current, duration) {
    const percent = duration > 0 ? Math.min(current, duration) / duration * 100 : 0;
    const seek = document.getElementById('music-seek');
    seek.value = Math.round(percent * 10);
    document.getElementById('music-time-cur').textContent = this.formatTime(current);
    document.getElementById('music-time-dur').textContent = this.formatTime(duration);

    const bar = document.getElementById('music-mini-progress');
    bar.setAttribute('aria-valuenow', Math.round(percent));
    document.getElementById('music-mini-progress-fill').style.width = `${percent}%`;
  },

  progressTimeFromPointer(event) {
    const rect = document.getElementById('music-mini-progress').getBoundingClientRect();
    const ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
    return ratio * this.duration();
  },

  startProgressDrag(event) {
    if (event.button !== 0 || !(this.duration() > 0)) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    this.isSeeking = true;
    this.renderProgress(this.progressTimeFromPointer(event), this.duration());
  },

  moveProgressDrag(event) {
    if (!this.isSeeking) return;
    this.renderProgress(this.progressTimeFromPointer(event), this.duration());
  },

  endProgressDrag(event, commit) {
    if (!this.isSeeking) return;
    if (commit) this.audio.currentTime = this.progressTimeFromPointer(event);
    this.isSeeking = false;
    this.refreshProgress();
  },

  updateShuffleUi() {
    const btn = document.getElementById('music-shuffle');
    btn.classList.toggle('active', this.shuffleOn);
    btn.setAttribute('aria-pressed', String(this.shuffleOn));
  },

  updateRepeatUi() {
    const btn = document.getElementById('music-repeat');
    btn.classList.toggle('active', this.repeatMode !== 'off');
    btn.setAttribute('aria-label', `Repeat: ${this.repeatMode}`);
    document.getElementById('music-repeat-one').style.display = this.repeatMode === 'one' ? '' : 'none';
  },

  openNow() {
    if (!this.current()) return;
    document.getElementById('music-now').style.display = 'flex';
    this.updateFavoriteUi();
    this.renderQueue();
  },

  openArtist() {
    const track = this.current();
    if (!track || !track.artist) return;
    this.closeNow();
    window.location.hash = `#music/artist/${encodeURIComponent(track.artist)}`;
  },

  closeNow() {
    this.queueVisible = false;
    document.getElementById('music-now').style.display = 'none';
    document.getElementById('music-now-body').style.display = '';
    document.getElementById('music-queue').style.display = 'none';
  },

  toggleQueue() {
    this.queueVisible = !this.queueVisible;
    document.getElementById('music-now-body').style.display = this.queueVisible ? 'none' : '';
    document.getElementById('music-queue').style.display = this.queueVisible ? 'block' : 'none';
    this.renderQueue();
  },

  renderQueue() {
    const list = document.getElementById('music-queue');
    if (!this.queueVisible) return;
    list.replaceChildren();

    const heading = document.createElement('div');
    heading.className = 'music-queue-title';
    heading.textContent = 'Up next';
    list.append(heading);

    this.queue.forEach((track, i) => {
      const row = document.createElement('div');
      row.className = 'music-queue-item' + (i === this.index ? ' current' : '');

      const info = document.createElement('button');
      info.type = 'button';
      info.className = 'music-queue-info';
      info.addEventListener('click', () => {
        this.index = i;
        this.loadCurrent(true);
      });
      const art = document.createElement('img');
      art.className = 'music-art music-queue-art';
      art.alt = '';
      art.loading = 'lazy';
      art.src = track.image_url || '';
      const text = document.createElement('div');
      text.className = 'music-queue-text';
      const title = document.createElement('div');
      title.className = 'music-queue-name';
      title.textContent = track.title;
      const artist = document.createElement('div');
      artist.className = 'music-queue-artist';
      artist.textContent = track.artist || '';
      text.append(title, artist);
      info.append(art, text);
      row.append(info);

      if (i !== this.index) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'music-icon-btn';
        remove.setAttribute('aria-label', 'Remove from queue');
        remove.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>';
        remove.addEventListener('click', () => this.removeFromQueue(i));
        row.append(remove);
      }
      list.append(row);
    });
  },

  removeFromQueue(i) {
    if (i === this.index) return;
    this.queue.splice(i, 1);
    if (i < this.index) this.index--;
    this.renderQueue();
  },

  // =========================================================
  // Picker
  // =========================================================
  pickerItem(label, onClick) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'music-picker-item';
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    return btn;
  },

  async loadPickerPlaylists(token) {
    const list = document.getElementById('music-picker-list');
    try {
      const data = await api.getMusicPlaylists();
      if (token !== this.pickerToken) return;
      (data.playlists || []).forEach((playlist) => {
        list.append(this.pickerItem(`${playlist.name} (${playlist.track_count})`, () => this.addToPlaylist(playlist)));
      });
    } catch (err) {
      if (token !== this.pickerToken) return;
      const note = document.createElement('div');
      note.className = 'music-picker-note';
      note.textContent = 'Could not load playlists';
      list.append(note);
    }
  },

  async addToPlaylist(playlist) {
    if (!this.pickerTrack) return;
    try {
      await api.addMusicPlaylistTrack(playlist.playlist_id, this.pickerTrack.track_id);
      App.showToast(`Added to ${playlist.name}`);
      this.closePicker();
    } catch (err) {
      App.showToast(err.message);
    }
  },

  async submitNewPlaylist(event) {
    event.preventDefault();
    const input = document.getElementById('music-picker-name');
    const name = input.value.trim();
    if (!name || !this.pickerTrack) return;
    try {
      const playlist = await api.createMusicPlaylist(name);
      await api.addMusicPlaylistTrack(playlist.playlist_id, this.pickerTrack.track_id);
      input.value = '';
      App.showToast(`Added to ${playlist.name}`);
      this.closePicker();
    } catch (err) {
      App.showToast(err.message);
    }
  },

  closePicker() {
    this.pickerToken++;
    this.pickerTrack = null;
    document.getElementById('music-picker').style.display = 'none';
    document.getElementById('music-picker-list').replaceChildren();
  },

  // =========================================================
  // Media Session (lock screen and notification controls)
  // =========================================================
  bindMediaSession() {
    if (!('mediaSession' in navigator)) return;
    const handlers = {
      play: () => this.audio.play().catch((err) => this.onPlayError(err)),
      pause: () => this.audio.pause(),
      previoustrack: () => this.previous(),
      nexttrack: () => this.next(),
      seekbackward: (details) => { this.audio.currentTime = Math.max(0, this.audio.currentTime - (details.seekOffset || 10)); },
      seekforward: (details) => { this.audio.currentTime = Math.min(this.duration(), this.audio.currentTime + (details.seekOffset || 10)); },
      seekto: (details) => { if (details.seekTime != null) this.audio.currentTime = details.seekTime; }
    };
    Object.entries(handlers).forEach(([action, handler]) => {
      try {
        navigator.mediaSession.setActionHandler(action, handler);
      } catch (err) {
        // Action not supported by this browser
      }
    });
  },

  formatTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
    const total = Math.floor(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = String(total % 60).padStart(2, '0');
    return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
  }
};
