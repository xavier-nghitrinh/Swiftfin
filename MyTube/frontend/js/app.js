/**
 * MyTube Application Controller
 * Handles SPA page tracking, YouTube-style Watch View, 2-option popover menu,
 * local cached thumbnails, and mobile swipe navigation.
 */

const App = {
  currentRoute: 'home',
  previousRouteHash: '#home',
  routeHistory: [],
  lastBrowseHash: null,
  savedBrowseScrollY: 0,
  hasBrowseDom: false,
  currentChannelId: null,
  currentWatchVideoId: null,
  currentWatchData: null,
  upNextSource: 'feed', // 'feed' or 'channel'
  channelFilter: 'all', // 'all', 'unwatched', 'watched'
  feedUnplayedOnly: true,
  searchQuery: '',

  // Pagination
  feedOffset: 0,
  feedLimit: 40,
  feedHasMore: true,
  isLoading: false,

  // Popover state
  popoverVideo: null,
  popoverCardEl: null,
  toastTimeout: null,

  // DOM elements
  appContainer: null,
  browseView: null,
  watchView: null,
  moviesView: null,
  movieDetailsView: null,
  showsView: null,
  showDetailsView: null,
  headerMoviesBtn: null,
  headerShowsBtn: null,
  headerBackBtn: null,
  videoGrid: null,
  channelList: null,
  viewTitle: null,
  channelHeaderAvatar: null,
  filterChips: null,
  loadingSpinner: null,
  emptyState: null,
  badgeUnwatched: null,
  searchInput: null,
  popoverMenu: null,
  toastEl: null,

  init() {
    if ('scrollRestoration' in history) {
      history.scrollRestoration = 'manual';
    }
    this.appContainer = document.getElementById('app-container');
    this.browseView = document.getElementById('browse-view');
    this.watchView = document.getElementById('watch-view');
    this.moviesView = document.getElementById('movies-view');
    this.movieDetailsView = document.getElementById('movie-details-view');
    this.showsView = document.getElementById('shows-view');
    this.showDetailsView = document.getElementById('show-details-view');
    this.headerMoviesBtn = document.getElementById('header-movies-btn');
    this.headerShowsBtn = document.getElementById('header-shows-btn');
    this.headerBackBtn = document.getElementById('header-back-btn');
    this.videoGrid = document.getElementById('video-grid');
    this.channelList = document.getElementById('channel-list');
    this.viewTitle = document.getElementById('view-title');
    this.channelHeaderAvatar = document.getElementById('channel-header-avatar');
    this.filterChips = document.getElementById('filter-chips');
    this.loadingSpinner = document.getElementById('loading-spinner');
    this.emptyState = document.getElementById('empty-state');
    this.badgeUnwatched = document.getElementById('badge-unwatched');
    this.searchInput = document.getElementById('search-input');
    this.popoverMenu = document.getElementById('card-popover-menu');
    this.toastEl = document.getElementById('toast-notification');

    Player.init();
    this.bindEvents();
    this.setupSwipeNavigation();
    this.handleRoute();
    this.updateStats();

    window.addEventListener('hashchange', () => this.handleRoute());
  },

  bindEvents() {
    // Logo click returns to home
    document.getElementById('logo-btn').addEventListener('click', () => {
      window.location.hash = '#home';
    });

    // Movies logo button
    if (this.headerMoviesBtn) {
      this.headerMoviesBtn.addEventListener('click', () => {
        window.location.hash = '#movies';
      });
    }

    // Shows logo button
    if (this.headerShowsBtn) {
      this.headerShowsBtn.addEventListener('click', () => {
        window.location.hash = '#shows';
      });
    }

    // Header back button
    this.headerBackBtn.addEventListener('click', () => {
      this.goBack();
    });

    // Search form submit
    document.getElementById('search-form').addEventListener('submit', (e) => {
      e.preventDefault();
      const q = this.searchInput.value.trim();
      if (q) {
        document.getElementById('search-form').classList.remove('mobile-open');
        window.location.hash = `#search?q=${encodeURIComponent(q)}`;
      }
    });

    // Mobile search toggle
    document.getElementById('mobile-search-toggle').addEventListener('click', () => {
      const form = document.getElementById('search-form');
      form.classList.toggle('mobile-open');
      if (form.classList.contains('mobile-open')) {
        this.searchInput.focus();
      }
    });

    // Refresh sync button
    document.getElementById('refresh-sync-btn').addEventListener('click', async () => {
      const icon = document.getElementById('sync-icon');
      icon.style.animation = 'spin 1s linear infinite';
      this.showToast('Syncing library & caching thumbnails...');
      try {
        const res = await api.triggerScan();
        await this.updateStats();
        this.handleRoute(true);
        this.showToast(`Synced ${res.synced_videos} videos (${res.cached_thumbnails || 0} new thumbs)`);
      } catch (err) {
        console.error('Sync failed:', err);
        this.showToast('Library sync failed');
      } finally {
        icon.style.animation = '';
      }
    });

    // 2-Option Popover Menu actions
    document.getElementById('popover-opt-watched').addEventListener('click', async (e) => {
      e.stopPropagation();
      const video = this.popoverVideo;
      const cardEl = this.popoverCardEl;
      this.hidePopover();
      if (!video) return;

      if (video.watched) {
        await api.markUnwatched(video.video_id);
        video.watched = 0;
        this.showToast('Marked as unwatched');
        this.handleRoute(true);
      } else {
        await api.markWatched(video.video_id);
        video.watched = 1;
        this.showToast('Marked as watched');
        if (this.currentRoute === 'home' && this.feedUnplayedOnly && cardEl) {
          cardEl.remove();
        } else {
          this.handleRoute(true);
        }
      }
      this.updateStats();
    });

    document.getElementById('popover-opt-trash').addEventListener('click', async (e) => {
      e.stopPropagation();
      const video = this.popoverVideo;
      const cardEl = this.popoverCardEl;
      this.hidePopover();
      if (!video) return;

      try {
        const result = await api.moveToTrash(video.video_id);
        if (!result || result.status !== 'ok') {
          throw new Error(result?.message || 'Failed to move media to Trash');
        }
        if (video.media_type === 'movie' || video.media_type === 'episode') {
          this.handleRoute(true);
        } else if (cardEl) {
          cardEl.remove();
        }
        this.showToast('Moved to Trash');
        this.updateStats();
      } catch (error) {
        console.error('Failed to move media to Trash:', error);
        this.showToast('Failed to move to Trash');
      }
    });

    // Close popover on outside click or scroll
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.card-popover-menu') && !e.target.closest('.card-action-btn')) {
        this.hidePopover();
      }
    });
    window.addEventListener('scroll', () => {
      if (this.popoverMenu.classList.contains('active')) {
        this.hidePopover();
      }
      const hash = window.location.hash || '#home';
      if (!hash.startsWith('#watch/') && this.browseView.style.display !== 'none') {
        this.savedBrowseScrollY = window.scrollY;
      }
    }, { passive: true });

    // Watch View buttons
    document.getElementById('watch-channel-link').addEventListener('click', () => {
      if (!this.currentWatchData) return;
      if (this.currentWatchData.media_type === 'movie') {
        window.location.hash = `#movie/${encodeURIComponent(this.currentWatchData.video_id)}`;
      } else if (this.currentWatchData.media_type === 'episode') {
        window.location.hash = `#show/${encodeURIComponent(this.currentWatchData.channel_id)}`;
      } else if (this.currentWatchData.channel_id) {
        window.location.hash = `#channel/${encodeURIComponent(this.currentWatchData.channel_id)}`;
      }
    });

    document.getElementById('watch-toggle-watched-btn').addEventListener('click', async () => {
      if (!this.currentWatchData) return;
      const vid = this.currentWatchData.video_id;
      if (this.currentWatchData.watched) {
        await api.markUnwatched(vid);
        this.currentWatchData.watched = false;
        this.updateWatchWatchedButton(false);
        this.showToast('Marked as unwatched');
      } else {
        await api.markWatched(vid);
        this.currentWatchData.watched = true;
        this.updateWatchWatchedButton(true);
        this.showToast('Marked as watched');
      }
      this.updateStats();
    });

    document.getElementById('watch-trash-btn').addEventListener('click', async () => {
      if (!this.currentWatchData) return;
      const vid = this.currentWatchData.video_id;
      const mType = this.currentWatchData.media_type;
      await api.moveToTrash(vid);
      const cardEl = document.getElementById(`video-card-${vid}`);
      if (cardEl) cardEl.remove();
      this.showToast('Moved to Trash');
      this.updateStats();
      if (mType === 'movie') {
        window.location.hash = '#movies';
      } else if (mType === 'episode') {
        window.location.hash = `#show/${encodeURIComponent(this.currentWatchData.channel_id)}`;
      } else {
        this.goBack();
      }
    });

    // Up Next filter chips in Watch View
    document.querySelectorAll('#up-next-chips .chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        document.querySelectorAll('#up-next-chips .chip').forEach((c) => c.classList.remove('active'));
        chip.classList.add('active');
        this.upNextSource = chip.dataset.source;
        this.loadUpNextVideos();
      });
    });

    // Infinite scroll listener for Browse View
    window.addEventListener('scroll', () => {
      if (this.currentRoute !== 'home' && !this.currentRoute.startsWith('#channel/')) return;
      if (this.isLoading || !this.feedHasMore) return;

      const scrollBottom = window.innerHeight + window.scrollY;
      if (scrollBottom >= document.documentElement.offsetHeight - 400) {
        this.loadMore();
      }
    }, { passive: true });
  },

  setupSwipeNavigation() {
    let touchStartX = 0;
    let touchStartY = 0;
    let touchStartTarget = null;

    document.addEventListener('touchstart', (e) => {
      if (e.touches.length !== 1) return;
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchStartTarget = e.target;
    }, { passive: true });

    document.addEventListener('touchend', (e) => {
      if (e.changedTouches.length !== 1) return;
      const dx = e.changedTouches[0].clientX - touchStartX;
      const dy = e.changedTouches[0].clientY - touchStartY;

      // Ignore page-navigation swipes while player is in fullscreen
      if (window.Player && Player.isFullscreen()) {
        // In unrotated pseudo-fullscreen, swiping down exits fullscreen back to inline Watch View
        if (
          Player.isPseudoFs &&
          !Player.isPseudoLandscape() &&
          touchStartTarget &&
          touchStartTarget.closest('#player-container') &&
          !touchStartTarget.closest('.seekbar, .seekbar-container, .dropdown-menu') &&
          dy > 95 &&
          Math.abs(dx) < 60
        ) {
          Player.exitFullscreen();
        }
        return;
      }

      // 1. Edge swipe right (from left edge < 45px) to go back on any sub-page
      if (touchStartX < 45 && dx > 80 && Math.abs(dy) < 55) {
        if (window.location.hash && window.location.hash !== '#home') {
          this.goBack();
          return;
        }
      }

      // 2. Swipe down on inline video player on mobile to close Watch View & go back
      if (
        this.currentRoute.startsWith('#watch/') &&
        !document.fullscreenElement &&
        touchStartTarget &&
        touchStartTarget.closest('#player-container') &&
        !touchStartTarget.closest('.seekbar, .seekbar-container, .dropdown-menu') &&
        dy > 95 &&
        Math.abs(dx) < 60
      ) {
        this.goBack();
      }
    }, { passive: true });
  },

  goBack() {
    if (this.routeHistory.length > 1) {
      this.routeHistory.pop(); // current
      const prev = this.routeHistory.pop();
      window.location.hash = prev || '#home';
    } else if (window.location.hash !== '#home') {
      window.location.hash = '#home';
    }
  },

  async updateStats() {
    try {
      const stats = await api.getStats();
      if (stats.unwatched_videos > 0) {
        this.badgeUnwatched.textContent = stats.unwatched_videos > 99 ? '99+' : stats.unwatched_videos;
        this.badgeUnwatched.style.display = 'inline-block';
      } else {
        this.badgeUnwatched.style.display = 'none';
      }
    } catch (e) {
      console.warn('Failed to load stats:', e);
    }
  },

  setActiveNav(id) {
    document.querySelectorAll('.nav-item').forEach((item) => item.classList.remove('active'));
    const target = document.getElementById(id);
    if (target) target.classList.add('active');
  },

  updateHeaderModeNav(mode) {
    if (this.headerMoviesBtn) this.headerMoviesBtn.classList.toggle('active', mode === 'movies');
    if (this.headerShowsBtn) this.headerShowsBtn.classList.toggle('active', mode === 'shows');
  },

  handleRoute(forceReload = false) {
    const hash = window.location.hash || '#home';
    const wasWatching = String(this.currentRoute).startsWith('#watch/');
    this.hidePopover();

    // Track route history
    if (this.routeHistory[this.routeHistory.length - 1] !== hash) {
      this.routeHistory.push(hash);
      if (this.routeHistory.length > 20) this.routeHistory.shift();
    }

    // Show header back button when not on root hubs
    const isRoot = (hash === '#home' || hash === '#movies' || hash === '#shows');
    this.headerBackBtn.style.display = !isRoot ? 'flex' : 'none';

    // Stop player if leaving #watch/
    if (!hash.startsWith('#watch/') && Player.isActive) {
      Player.stop();
      this.updateStats();
    }

    const hideAllViews = () => {
      this.watchView.style.display = 'none';
      this.browseView.style.display = 'none';
      if (this.moviesView) this.moviesView.style.display = 'none';
      if (this.movieDetailsView) this.movieDetailsView.style.display = 'none';
      if (this.showsView) this.showsView.style.display = 'none';
      if (this.showDetailsView) this.showDetailsView.style.display = 'none';
    };

    // 1. Watch View
    if (hash.startsWith('#watch/')) {
      hideAllViews();
      this.currentRoute = hash;
      const videoId = decodeURIComponent(hash.slice('#watch/'.length));
      this.watchView.style.display = 'grid';
      this.appContainer.classList.add('watch-mode');
      window.scrollTo(0, 0);
      this.renderWatchView(videoId);
      return;
    }

    this.appContainer.classList.remove('watch-mode');

    // 2. Movies Home View
    if (hash === '#movies') {
      hideAllViews();
      this.currentRoute = 'movies';
      this.setActiveNav('nav-movies');
      this.updateHeaderModeNav('movies');
      if (this.moviesView) this.moviesView.style.display = 'block';
      window.scrollTo(0, 0);
      this.renderMoviesHome(forceReload);
      return;
    }

    // 3. Movie Details View
    if (hash.startsWith('#movie/')) {
      hideAllViews();
      this.currentRoute = hash;
      const movieId = decodeURIComponent(hash.slice('#movie/'.length));
      this.setActiveNav('nav-movies');
      this.updateHeaderModeNav('movies');
      if (this.movieDetailsView) this.movieDetailsView.style.display = 'block';
      window.scrollTo(0, 0);
      this.renderMovieDetail(movieId);
      return;
    }

    // 4. Shows Home View
    if (hash === '#shows') {
      hideAllViews();
      this.currentRoute = 'shows';
      this.setActiveNav('nav-shows');
      this.updateHeaderModeNav('shows');
      if (this.showsView) this.showsView.style.display = 'block';
      window.scrollTo(0, 0);
      this.renderShowsHome(forceReload);
      return;
    }

    // 5. Show Details View
    if (hash.startsWith('#show/')) {
      hideAllViews();
      this.currentRoute = hash;
      const showId = decodeURIComponent(hash.slice('#show/'.length));
      this.setActiveNav('nav-shows');
      this.updateHeaderModeNav('shows');
      if (this.showDetailsView) this.showDetailsView.style.display = 'block';
      window.scrollTo(0, 0);
      this.renderShowDetail(showId);
      return;
    }

    // 6. YouTube Browse Views (Home, Channels, Channel, Trash, Search)
    hideAllViews();
    this.browseView.style.display = 'block';
    this.updateHeaderModeNav('youtube');

    // If returning from Watch View to the exact same Browse page, keep existing DOM & restore scroll position
    if (!forceReload && wasWatching && this.hasBrowseDom && this.lastBrowseHash === hash) {
      if (hash.startsWith('#channel/')) {
        this.currentRoute = hash;
        this.setActiveNav('nav-channels');
      } else if (hash === '#channels') {
        this.currentRoute = 'channels';
        this.setActiveNav('nav-channels');
      } else if (hash === '#trash') {
        this.currentRoute = 'trash';
        this.setActiveNav('nav-trash');
      } else if (hash.startsWith('#search')) {
        this.currentRoute = 'search';
      } else {
        this.currentRoute = 'home';
        this.setActiveNav('nav-home');
      }

      // Update or remove the card in-place if its watched state changed while watching
      if (this.currentWatchData) {
        const cardEl = document.getElementById(`video-card-${this.currentWatchData.video_id}`);
        if (cardEl && this.currentWatchData.watched) {
          if (hash === '#home' && this.feedUnplayedOnly) {
            cardEl.remove();
          } else if (!cardEl.querySelector('.watched-badge')) {
            const thumbBox = cardEl.querySelector('.thumbnail-box');
            if (thumbBox) {
              const badge = document.createElement('span');
              badge.className = 'watched-badge';
              badge.textContent = 'WATCHED';
              thumbBox.appendChild(badge);
            }
          }
        }
      }

      const targetY = this.savedBrowseScrollY || 0;
      window.scrollTo(0, targetY);
      requestAnimationFrame(() => window.scrollTo(0, targetY));
      return;
    }

    this.lastBrowseHash = hash;
    this.savedBrowseScrollY = 0;
    this.hasBrowseDom = true;
    this.channelHeaderAvatar.style.display = 'none';
    window.scrollTo(0, 0);

    this.feedOffset = 0;
    this.feedHasMore = true;

    if (hash.startsWith('#channel/')) {
      this.currentRoute = hash;
      const parts = hash.split('/');
      this.currentChannelId = decodeURIComponent(parts[1]);
      this.setActiveNav('nav-channels');
      this.renderChannelFeed();
    } else if (hash === '#channels') {
      this.currentRoute = 'channels';
      this.setActiveNav('nav-channels');
      this.renderChannelsList();
    } else if (hash === '#trash') {
      this.currentRoute = 'trash';
      this.setActiveNav('nav-trash');
      this.renderTrash();
    } else if (hash.startsWith('#search')) {
      this.currentRoute = 'search';
      const urlParams = new URLSearchParams(hash.split('?')[1]);
      this.searchQuery = urlParams.get('q') || '';
      this.renderSearchResults();
    } else {
      this.currentRoute = 'home';
      this.setActiveNav('nav-home');
      this.renderHomeFeed();
    }
  },

  // =========================================================
  // YouTube-Style Watch View
  // =========================================================
  async renderWatchView(videoId) {
    this.currentWatchVideoId = videoId;
    document.getElementById('watch-video-title').textContent = 'Loading video...';
    document.getElementById('watch-description').textContent = '';

    let data = null;
    try {
      data = await api.getPlayback(videoId);
    } catch (e) {
      console.error('Failed to fetch playback metadata:', e);
      document.getElementById('watch-video-title').textContent = 'Could not load video metadata';
      return;
    }

    if (!data) return;
    this.currentWatchData = data;

    // Cinema mode for Movies and Shows: only player, no watch next, no recommendations
    if (data.media_type === 'movie' || data.media_type === 'episode') {
      this.watchView.classList.add('watch-cinema-mode');
      const listEl = document.getElementById('up-next-list');
      if (listEl) listEl.innerHTML = '';
    } else {
      this.watchView.classList.remove('watch-cinema-mode');
      this.loadUpNextVideos();
    }

    if (data.media_type === 'movie') {
      document.getElementById('watch-video-title').textContent = data.title;
      document.getElementById('watch-channel-name').textContent = `Movie (${data.upload_date || 'Film'})`;
      document.getElementById('watch-upload-date').textContent = data.duration ? this.formatDurationHuman(data.duration) : '';
    } else if (data.media_type === 'episode') {
      document.getElementById('watch-video-title').textContent = data.title;
      document.getElementById('watch-channel-name').textContent = data.channel_name;
      document.getElementById('watch-upload-date').textContent = data.duration ? this.formatDurationHuman(data.duration) : '';
    } else {
      document.getElementById('watch-video-title').textContent = data.title;
      document.getElementById('watch-channel-name').textContent = data.channel_name;
      document.getElementById('watch-upload-date').textContent = data.upload_date
        ? `Uploaded ${this.formatRelativeTime(data.upload_date)} (${data.upload_date})`
        : '';
    }

    const avatarBox = document.getElementById('watch-channel-avatar');
    this.populateAvatarElement(avatarBox, data.channel_name, data.channel_thumbnail_url);

    this.updateWatchWatchedButton(Boolean(data.watched));

    const descEl = document.getElementById('watch-description');
    if (data.description && data.description.trim()) {
      descEl.style.display = 'block';
      descEl.textContent = data.description;
    } else {
      descEl.style.display = 'none';
    }

    if (this.upNextSource === 'channel' && data.media_type !== 'movie' && data.media_type !== 'episode') {
      this.loadUpNextVideos();
    }

    // Start player stream without blocking UI rendering
    Player.startPlayback(data, () => {
      if (this.currentWatchData) {
        this.currentWatchData.watched = true;
      }
      this.updateWatchWatchedButton(true);
      this.updateStats();
    });
  },

  updateWatchWatchedButton(isWatched) {
    const btn = document.getElementById('watch-toggle-watched-btn');
    const label = document.getElementById('watch-watched-label');
    btn.classList.toggle('active', isWatched);
    label.textContent = isWatched ? 'Watched' : 'Mark Watched';
  },

  async loadUpNextVideos() {
    const listEl = document.getElementById('up-next-list');
    listEl.innerHTML = '';

    try {
      let items = [];
      if (this.upNextSource === 'channel' && this.currentWatchData?.channel_id) {
        const res = await api.getChannelVideos(this.currentWatchData.channel_id, 'all', 25, 0);
        items = res.items || [];
      } else {
        const res = await api.getHomeFeed(25, 0, true);
        items = res.items || [];
      }

      const filtered = items.filter((v) => v.video_id !== this.currentWatchVideoId);
      if (filtered.length === 0) {
        listEl.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem; padding: 12px 0;">No more videos in this queue.</div>`;
        return;
      }

      filtered.forEach((video) => {
        listEl.appendChild(this.createCompactVideoCard(video));
      });
    } catch (e) {
      console.warn('Failed to load Up Next videos:', e);
    }
  },

  createCompactVideoCard(video) {
    const card = document.createElement('div');
    card.className = 'compact-video-card';

    const thumbUrl = video.thumbnail_url || `/thumbnails/videos/${video.video_id}.jpg`;
    const durStr = Player.formatTime(video.duration);
    const uploadTimeAgo = this.formatRelativeTime(video.upload_date);

    let progressPercent = 0;
    if (video.duration > 0 && video.playback_position > 0 && !video.watched) {
      progressPercent = Math.min(100, (video.playback_position / video.duration) * 100);
    }

    card.innerHTML = `
      <div class="thumbnail-box">
        <img src="${thumbUrl}" loading="lazy" alt="${this.escapeHtml(video.title)}">
        <span class="duration-badge">${durStr}</span>
        ${video.watched ? `<span class="watched-badge">WATCHED</span>` : ''}
        ${progressPercent > 0 ? `<div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${progressPercent}%;"></div></div>` : ''}
      </div>
      <div class="video-info">
        <h4 class="video-title">${this.escapeHtml(video.title)}</h4>
        <div class="video-subtext">${this.escapeHtml(video.channel_name)}</div>
        <div class="video-subtext">${uploadTimeAgo}</div>
      </div>
      <button class="btn-icon card-action-btn" title="More options">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>
      </button>
    `;

    card.addEventListener('click', (e) => {
      if (e.target.closest('.card-action-btn')) return;
      if (window.Player) Player.blessFromUserGesture();
      window.location.hash = `#watch/${encodeURIComponent(video.video_id)}`;
    });

    card.querySelector('.card-action-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      this.openPopover(e.currentTarget, video, card);
    });

    return card;
  },

  // =========================================================
  // 1. Home Feed View
  // =========================================================
  async renderHomeFeed(append = false) {
    if (!append) {
      this.viewTitle.textContent = 'Subscription Feed';
      this.videoGrid.style.display = 'grid';
      this.channelList.style.display = 'none';
      this.videoGrid.innerHTML = '';
      this.renderFeedChips();
    }

    this.showLoading(true);
    try {
      const data = await api.getHomeFeed(this.feedLimit, this.feedOffset, this.feedUnplayedOnly);
      this.feedHasMore = data.has_more;

      if (!append && data.items.length === 0) {
        this.showEmpty(true, 'No new unwatched videos!', 'Switch to "All Videos" or sync for new uploads.');
      } else {
        this.showEmpty(false);
        data.items.forEach((video) => {
          this.videoGrid.appendChild(this.createVideoCard(video));
        });
      }
    } catch (err) {
      console.error(err);
    } finally {
      this.showLoading(false);
    }
  },

  renderFeedChips() {
    this.filterChips.innerHTML = `
      <div class="chip ${this.feedUnplayedOnly ? 'active' : ''}" id="chip-unwatched">Unwatched</div>
      <div class="chip ${!this.feedUnplayedOnly ? 'active' : ''}" id="chip-all">All Videos</div>
    `;

    document.getElementById('chip-unwatched').addEventListener('click', () => {
      this.feedUnplayedOnly = true;
      this.feedOffset = 0;
      this.renderHomeFeed();
    });

    document.getElementById('chip-all').addEventListener('click', () => {
      this.feedUnplayedOnly = false;
      this.feedOffset = 0;
      this.renderHomeFeed();
    });
  },

  // =========================================================
  // 2. Channels List View
  // =========================================================
  async renderChannelsList() {
    this.viewTitle.textContent = 'Subscribed Channels';
    this.filterChips.innerHTML = '';
    this.videoGrid.style.display = 'none';
    this.channelList.style.display = 'grid';
    this.channelList.innerHTML = '';
    this.showEmpty(false);
    this.showLoading(true);

    try {
      const channels = await api.getChannels();
      if (channels.length === 0) {
        this.showEmpty(true, 'No channels found', 'Sync your library to index downloaded channels.');
      } else {
        channels.forEach((ch) => {
          const card = document.createElement('div');
          card.className = 'channel-card';

          const avatarDiv = document.createElement('div');
          avatarDiv.className = 'channel-avatar';
          this.populateAvatarElement(avatarDiv, ch.name, ch.thumbnail_url);

          const nameDiv = document.createElement('div');
          nameDiv.className = 'channel-card-name';
          nameDiv.textContent = ch.name;

          const metaDiv = document.createElement('div');
          metaDiv.className = 'channel-card-meta';
          metaDiv.textContent = `${ch.unwatched_count} unwatched • ${ch.total_videos} videos`;

          card.appendChild(avatarDiv);
          card.appendChild(nameDiv);
          card.appendChild(metaDiv);

          card.addEventListener('click', () => {
            window.location.hash = `#channel/${encodeURIComponent(ch.channel_id)}`;
          });
          this.channelList.appendChild(card);
        });
      }
    } catch (err) {
      console.error(err);
    } finally {
      this.showLoading(false);
    }
  },

  // =========================================================
  // 3. Channel Feed View
  // =========================================================
  async renderChannelFeed(append = false) {
    if (!append) {
      this.videoGrid.style.display = 'grid';
      this.channelList.style.display = 'none';
      this.videoGrid.innerHTML = '';
      this.renderChannelChips();
    }

    this.showLoading(true);
    try {
      if (!append) {
        const detail = await api.getChannelDetail(this.currentChannelId);
        if (detail) {
          this.viewTitle.textContent = `${detail.name} (${detail.total_videos})`;
          if (detail.thumbnail_url) {
            this.channelHeaderAvatar.src = detail.thumbnail_url;
            this.channelHeaderAvatar.style.display = 'block';
            this.channelHeaderAvatar.onerror = () => {
              this.channelHeaderAvatar.style.display = 'none';
            };
          }
        } else {
          this.viewTitle.textContent = 'Channel Videos';
        }
      }

      const data = await api.getChannelVideos(
        this.currentChannelId,
        this.channelFilter,
        this.feedLimit,
        this.feedOffset
      );
      this.feedHasMore = data.has_more;

      if (!append && data.items.length === 0) {
        this.showEmpty(true, 'No videos found for this filter.');
      } else {
        this.showEmpty(false);
        data.items.forEach((video) => {
          this.videoGrid.appendChild(this.createVideoCard(video));
        });
      }
    } catch (err) {
      console.error(err);
    } finally {
      this.showLoading(false);
    }
  },

  renderChannelChips() {
    this.filterChips.innerHTML = `
      <div class="chip ${this.channelFilter === 'all' ? 'active' : ''}" data-filter="all">All</div>
      <div class="chip ${this.channelFilter === 'unwatched' ? 'active' : ''}" data-filter="unwatched">Unwatched</div>
      <div class="chip ${this.channelFilter === 'watched' ? 'active' : ''}" data-filter="watched">Watched</div>
    `;

    this.filterChips.querySelectorAll('.chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        this.channelFilter = chip.dataset.filter;
        this.feedOffset = 0;
        this.renderChannelFeed();
      });
    });
  },

  // =========================================================
  // 4. Trash View
  // =========================================================
  async renderTrash() {
    this.viewTitle.textContent = 'Trash (Auto-deleted after 30 days)';
    this.filterChips.innerHTML = '';
    this.videoGrid.style.display = 'grid';
    this.channelList.style.display = 'none';
    this.videoGrid.innerHTML = '';
    this.showEmpty(false);
    this.showLoading(true);

    try {
      const items = await api.getTrash();
      if (items.length === 0) {
        this.showEmpty(true, 'Trash is empty', 'Videos moved to Trash stay here for 30 days before permanent SSD deletion.');
      } else {
        items.forEach((item) => {
          this.videoGrid.appendChild(this.createTrashCard(item));
        });
      }
    } catch (err) {
      console.error(err);
    } finally {
      this.showLoading(false);
    }
  },

  // =========================================================
  // 5. Search Results View
  // =========================================================
  async renderSearchResults() {
    this.viewTitle.textContent = `Search: "${this.searchQuery}"`;
    this.filterChips.innerHTML = '';
    this.videoGrid.style.display = 'grid';
    this.channelList.style.display = 'none';
    this.videoGrid.innerHTML = '';
    this.showEmpty(false);
    this.showLoading(true);

    try {
      const results = await api.search(this.searchQuery);
      if (results.length === 0) {
        this.showEmpty(true, `No results for "${this.searchQuery}"`);
      } else {
        results.forEach((video) => {
          this.videoGrid.appendChild(this.createVideoCard(video));
        });
      }
    } catch (err) {
      console.error(err);
    } finally {
      this.showLoading(false);
    }
  },

  loadMore() {
    this.isLoading = true;
    this.feedOffset += this.feedLimit;
    if (this.currentRoute === 'home') {
      this.renderHomeFeed(true);
    } else if (this.currentRoute.startsWith('#channel/')) {
      this.renderChannelFeed(true);
    }
  },

  // =========================================================
  // Card Builders & Popover Menu
  // =========================================================
  populateAvatarElement(el, name, thumbUrl) {
    const initial = ((name || 'Y').trim()[0] || 'Y').toUpperCase();
    el.innerHTML = '';
    if (thumbUrl) {
      const img = document.createElement('img');
      img.src = thumbUrl;
      img.alt = name || '';
      img.loading = 'lazy';
      img.onerror = () => {
        img.remove();
        el.textContent = initial;
      };
      el.appendChild(img);
    } else {
      el.textContent = initial;
    }
  },

  createVideoCard(video) {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.id = `video-card-${video.video_id}`;

    const thumbUrl = video.thumbnail_url || `/thumbnails/videos/${video.video_id}.jpg`;
    const channelThumbUrl = video.channel_thumbnail_url || `/thumbnails/channels/${video.channel_id}.jpg`;
    const durStr = Player.formatTime(video.duration);

    let progressPercent = 0;
    if (video.duration > 0 && video.playback_position > 0 && !video.watched) {
      progressPercent = Math.min(100, (video.playback_position / video.duration) * 100);
    }

    const uploadTimeAgo = this.formatRelativeTime(video.upload_date);

    card.innerHTML = `
      <div class="thumbnail-box">
        <img src="${thumbUrl}" loading="lazy" alt="${this.escapeHtml(video.title)}">
        <span class="duration-badge">${durStr}</span>
        ${video.watched ? `<span class="watched-badge">WATCHED</span>` : ''}
        ${progressPercent > 0 ? `<div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${progressPercent}%;"></div></div>` : ''}
      </div>
      <div class="video-meta">
        <div class="channel-avatar"></div>
        <div class="video-info">
          <h3 class="video-title">${this.escapeHtml(video.title)}</h3>
          <div class="video-subtext">
            <span class="channel-link">${this.escapeHtml(video.channel_name)}</span> • ${uploadTimeAgo}
          </div>
        </div>
        <div class="video-actions">
          <button class="btn-icon card-action-btn" title="More options">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>
          </button>
        </div>
      </div>
    `;

    const avatarEl = card.querySelector('.channel-avatar');
    this.populateAvatarElement(avatarEl, video.channel_name, channelThumbUrl);

    // Click avatar or channel name to open channel page or media info
    avatarEl.addEventListener('click', (e) => {
      e.stopPropagation();
      if (video.media_type === 'movie') {
        window.location.hash = `#movie/${encodeURIComponent(video.video_id)}`;
      } else if (video.media_type === 'show') {
        window.location.hash = `#show/${encodeURIComponent(video.video_id)}`;
      } else {
        window.location.hash = `#channel/${encodeURIComponent(video.channel_id)}`;
      }
    });
    card.querySelector('.channel-link').addEventListener('click', (e) => {
      e.stopPropagation();
      if (video.media_type === 'movie') {
        window.location.hash = `#movie/${encodeURIComponent(video.video_id)}`;
      } else if (video.media_type === 'show') {
        window.location.hash = `#show/${encodeURIComponent(video.video_id)}`;
      } else {
        window.location.hash = `#channel/${encodeURIComponent(video.channel_id)}`;
      }
    });

    // Click thumbnail or title to open YouTube Watch View or Movie/Show Info
    const handleCardClick = () => {
      this.savedBrowseScrollY = window.scrollY;
      if (video.media_type === 'movie') {
        window.location.hash = `#movie/${encodeURIComponent(video.video_id)}`;
      } else if (video.media_type === 'show') {
        window.location.hash = `#show/${encodeURIComponent(video.video_id)}`;
      } else {
        if (window.Player) Player.blessFromUserGesture();
        window.location.hash = `#watch/${encodeURIComponent(video.video_id)}`;
      }
    };
    card.querySelector('.thumbnail-box').addEventListener('click', handleCardClick);
    card.querySelector('.video-title').addEventListener('click', handleCardClick);

    // 3-dot button opens sleek 2-option popover menu
    card.querySelector('.card-action-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      this.openPopover(e.currentTarget, video, card);
    });

    return card;
  },

  openPopover(anchorBtn, video, cardEl) {
    if (this.popoverMenu.classList.contains('active') && this.popoverVideo?.video_id === video.video_id) {
      this.hidePopover();
      return;
    }

    this.popoverVideo = video;
    this.popoverCardEl = cardEl;

    document.getElementById('popover-watched-text').textContent = video.watched
      ? 'Mark as Unwatched'
      : 'Mark as Watched';

    this.popoverMenu.classList.add('active');

    // Position near the anchor button while keeping inside viewport
    const rect = anchorBtn.getBoundingClientRect();
    const menuWidth = 200;
    const menuHeight = 96;

    let left = rect.right - menuWidth;
    let top = rect.bottom + 4;

    if (left < 10) left = 10;
    if (top + menuHeight > window.innerHeight - 12) {
      top = rect.top - menuHeight - 4;
    }

    this.popoverMenu.style.left = `${left}px`;
    this.popoverMenu.style.top = `${top}px`;
  },

  hidePopover() {
    this.popoverMenu.classList.remove('active');
    this.popoverVideo = null;
    this.popoverCardEl = null;
  },

  createTrashCard(item) {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.id = `trash-card-${item.video_id}`;

    const thumbUrl = item.thumbnail_url || `/thumbnails/videos/${item.video_id}.jpg`;
    const durStr = Player.formatTime(item.duration);

    const trashAt = item.trashed_at || item.trash_at;
    let daysLeft = item.days_until_deletion;
    if (daysLeft === undefined || daysLeft === null) {
      if (trashAt) {
        try {
          const trashDate = new Date(trashAt);
          const expiryDate = new Date(trashDate.getTime() + 30 * 24 * 60 * 60 * 1000);
          const diffMs = expiryDate - new Date();
          daysLeft = Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
        } catch {
          daysLeft = 30;
        }
      } else {
        daysLeft = 30;
      }
    }

    const expireText = daysLeft <= 0
      ? 'Expires today'
      : (daysLeft === 1 ? 'Expires in 1 day' : `Expires in ${daysLeft} days`);
    const relativeTrashed = trashAt ? this.formatRelativeTime(trashAt) : 'recently';

    card.innerHTML = `
      <div class="thumbnail-box">
        <img src="${thumbUrl}" loading="lazy" alt="${this.escapeHtml(item.title)}">
        <span class="duration-badge">${durStr}</span>
        <div style="position: absolute; top: 8px; left: 8px; background: rgba(255,0,0,0.85); color: #fff; font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; font-weight: 600;">
          ${expireText}
        </div>
      </div>
      <div class="video-meta">
        <div class="video-info">
          <h3 class="video-title">${this.escapeHtml(item.title)}</h3>
          <div class="video-subtext">${this.escapeHtml(item.channel_name)} • Trashed ${relativeTrashed}</div>
        </div>
      </div>
      <div style="display: flex; gap: 8px; margin-top: 10px;">
        <button class="chip" style="flex: 1;" id="restore-btn-${item.video_id}">Restore</button>
        <button class="chip" style="flex: 1; border-color: var(--accent-red); color: #ff5252;" id="perm-del-btn-${item.video_id}">Delete Permanently</button>
      </div>
    `;

    card.querySelector(`#restore-btn-${item.video_id}`).addEventListener('click', async () => {
      await api.restoreFromTrash(item.video_id);
      card.remove();
      this.showToast('Restored video from Trash');
      this.updateStats();
    });

    let confirmPending = false;
    const delBtn = card.querySelector(`#perm-del-btn-${item.video_id}`);
    delBtn.addEventListener('click', async () => {
      if (!confirmPending) {
        confirmPending = true;
        delBtn.textContent = 'Tap again to confirm SSD delete';
        delBtn.style.background = 'rgba(255, 0, 0, 0.25)';
        setTimeout(() => {
          confirmPending = false;
          if (delBtn.isConnected) {
            delBtn.textContent = 'Delete Permanently';
            delBtn.style.background = '';
          }
        }, 3500);
        return;
      }
      await api.deletePermanently(item.video_id);
      card.remove();
      this.showToast('Permanently deleted from SSD');
      this.updateStats();
    });

    return card;
  },

  showToast(message) {
    if (!this.toastEl) return;
    this.toastEl.textContent = message;
    this.toastEl.classList.add('show');
    if (this.toastTimeout) clearTimeout(this.toastTimeout);
    this.toastTimeout = setTimeout(() => {
      this.toastEl.classList.remove('show');
    }, 2600);
  },

  showLoading(show) {
    this.isLoading = show;
    this.loadingSpinner.style.display = show ? 'block' : 'none';
  },

  showEmpty(show, title = 'No videos found', subtitle = '') {
    if (show) {
      this.emptyState.querySelector('p:first-child').textContent = title;
      this.emptyState.querySelector('p:last-child').textContent = subtitle;
      this.emptyState.style.display = 'block';
    } else {
      this.emptyState.style.display = 'none';
    }
  },

  formatRelativeTime(dateStr) {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now - date;
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

      if (diffDays <= 0) return 'Today';
      if (diffDays === 1) return 'Yesterday';
      if (diffDays < 7) return `${diffDays} days ago`;
      if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
      if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
      return `${Math.floor(diffDays / 365)} years ago`;
    } catch {
      return dateStr;
    }
  },

  formatDurationHuman(seconds) {
    if (!seconds || seconds <= 0) return '';
    const totalSecs = Math.round(seconds);
    const h = Math.floor(totalSecs / 3600);
    const m = Math.floor((totalSecs % 3600) / 60);
    if (h > 0) {
      return m > 0 ? `${h}h ${m}m` : `${h}h`;
    }
    if (m > 0) {
      return `${m}m`;
    }
    return `${totalSecs}s`;
  },

  createMediaCard(item, isWide = false, clickRoute = '') {
    const card = document.createElement('div');
    card.className = `media-card ${isWide ? 'wide-card' : ''}`;

    const title = item.title || item.show_name || 'Untitled';
    const imgUrl = isWide
      ? (item.backdrop_url || item.thumbnail_url || item.poster_url || '')
      : (item.poster_url || item.thumbnail_url || item.backdrop_url || '');

    const rating = item.community_rating ? Number(item.community_rating).toFixed(1) : null;
    const isWatched = Boolean(item.watched);
    const progressPercent = item.progress_percent || 0;

    let subText = '';
    if (item.media_type === 'movie') {
      const year = item.release_year || '';
      const dur = this.formatDurationHuman(item.duration);
      subText = [year, dur].filter(Boolean).join(' • ');
    } else if (item.media_type === 'show') {
      if (item.current_episode) {
        const ep = item.current_episode;
        subText = `S${ep.season_number} E${ep.episode_number} • ${this.escapeHtml(ep.title)}`;
      } else {
        const yr = item.start_year || '';
        const eps = item.total_episodes ? `${item.total_episodes} eps` : '';
        subText = [yr, eps].filter(Boolean).join(' • ');
      }
    } else if (item.media_type === 'episode') {
      const dur = this.formatDurationHuman(item.duration);
      subText = `S${item.season_number} E${item.episode_number}${dur ? ' • ' + dur : ''}`;
    }

    const ratingBadge = rating ? `
      <div class="card-rating-badge">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>
        <span>${rating}</span>
      </div>
    ` : '';

    const watchedBadge = isWatched ? `<span class="card-watched-badge">WATCHED</span>` : '';
    const progressBar = (!isWatched && progressPercent > 0) ? `
      <div class="card-progress-bar">
        <div class="card-progress-bar-fill" style="width: ${Math.min(100, progressPercent)}%;"></div>
      </div>
    ` : '';

    const itemId = item.movie_id || item.show_id || item.episode_id || item.video_id;
    const movieMenuButton = item.media_type === 'movie' ? `
      <button type="button" class="btn-icon card-action-btn media-card-action-btn" title="More options" aria-label="More options for ${this.escapeHtml(title)}">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 2 .9 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>
      </button>
    ` : '';

    card.innerHTML = `
      <div class="media-poster-box">
        ${imgUrl ? `<img src="${imgUrl}" loading="lazy" alt="${this.escapeHtml(title)}">` : '<div style="width:100%;height:100%;background:var(--bg-card);display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:0.8rem;">No Image</div>'}
        ${ratingBadge}
        ${watchedBadge}
        ${progressBar}
      </div>
      <div class="media-card-info">
        <div class="media-card-heading">
          <div class="media-card-title" title="${this.escapeHtml(title)}">${this.escapeHtml(title)}</div>
          ${movieMenuButton}
        </div>
        <div class="media-card-sub">${subText}</div>
      </div>
    `;

    card.addEventListener('click', () => {
      if (!itemId) return;
      this.savedBrowseScrollY = window.scrollY;
      if (clickRoute) {
        window.location.hash = clickRoute;
      } else if (item.media_type === 'movie') {
        window.location.hash = `#movie/${encodeURIComponent(itemId)}`;
      } else if (item.media_type === 'show') {
        window.location.hash = `#show/${encodeURIComponent(itemId)}`;
      } else if (item.media_type === 'episode') {
        if (window.Player) Player.blessFromUserGesture();
        window.location.hash = `#watch/${encodeURIComponent(itemId)}`;
      }
    });

    const actionButton = card.querySelector('.card-action-btn');
    if (actionButton) {
      actionButton.addEventListener('click', (event) => {
        event.stopPropagation();
        this.openPopover(event.currentTarget, {
          ...item,
          video_id: itemId,
          media_type: 'movie',
        }, card);
      });
    }

    return card;
  },

  async renderMoviesHome(forceReload = false) {
    if (!this.moviesView) return;
    const heroEl = document.getElementById('movies-hero');
    const shelvesEl = document.getElementById('movies-shelves');
    if (!heroEl || !shelvesEl) return;

    this.showLoading(true);
    try {
      const data = await api.getMoviesHome();
      this.showLoading(false);

      // 1. Featured Hero
      if (data.featured) {
        const m = data.featured;
        const heroBg = m.backdrop_url || m.poster_url || '';
        const rating = m.community_rating ? Number(m.community_rating).toFixed(1) : null;
        const dur = this.formatDurationHuman(m.duration);
        const genres = Array.isArray(m.genres) ? m.genres.slice(0, 3) : [];

        heroEl.style.display = 'flex';
        heroEl.style.backgroundImage = heroBg ? `url("${heroBg}")` : 'none';
        heroEl.innerHTML = `
          <div class="netflix-hero-content">
            <span class="netflix-hero-badge">Featured Movie</span>
            <h1 class="netflix-hero-title">${this.escapeHtml(m.title)}</h1>
            <div class="netflix-hero-meta">
              ${rating ? `<span class="rating-badge"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg> ${rating}</span>` : ''}
              ${m.release_year ? `<span>${m.release_year}</span>` : ''}
              ${dur ? `<span>${dur}</span>` : ''}
              ${genres.map(g => `<span class="genre-pill">${this.escapeHtml(g)}</span>`).join('')}
            </div>
            ${m.overview ? `<p class="netflix-hero-overview">${this.escapeHtml(m.overview)}</p>` : ''}
            <div class="netflix-hero-actions">
              <button class="btn-hero-play" id="hero-movie-play-btn">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                <span>${m.playback_position > 15 && !m.watched ? 'Resume' : 'Play'}</span>
              </button>
              <button class="btn-hero-info" id="hero-movie-info-btn">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/></svg>
                <span>Details</span>
              </button>
            </div>
          </div>
        `;

        document.getElementById('hero-movie-play-btn').addEventListener('click', () => {
          if (window.Player) Player.blessFromUserGesture();
          window.location.hash = `#watch/${encodeURIComponent(m.movie_id)}`;
        });
        document.getElementById('hero-movie-info-btn').addEventListener('click', () => {
          window.location.hash = `#movie/${encodeURIComponent(m.movie_id)}`;
        });
      } else {
        heroEl.style.display = 'none';
      }

      // 2. Shelves
      shelvesEl.innerHTML = '';

      const appendShelf = (title, items, isWide = false) => {
        if (!items || items.length === 0) return;
        const shelf = document.createElement('div');
        shelf.className = 'netflix-shelf';
        shelf.innerHTML = `
          <div class="shelf-header">
            <h3 class="shelf-title">${this.escapeHtml(title)}</h3>
          </div>
          <div class="shelf-track"></div>
        `;
        const track = shelf.querySelector('.shelf-track');
        items.forEach(it => {
          track.appendChild(this.createMediaCard(it, isWide, `#movie/${encodeURIComponent(it.movie_id)}`));
        });
        shelvesEl.appendChild(shelf);
      };

      // Shelf: Continue Watching
      if (data.continue_watching && data.continue_watching.length > 0) {
        appendShelf('Continue Watching', data.continue_watching, false);
      }

      // Shelf: Recently Added
      if (data.recently_added && data.recently_added.length > 0) {
        appendShelf('Recently Added Movies', data.recently_added, false);
      }

      // Shelves: 5 Random Genres
      if (data.genres && data.genres.length > 0) {
        data.genres.forEach(gShelf => {
          appendShelf(gShelf.genre, gShelf.movies, false);
        });
      }

      // Shelf: All Movies
      if (data.all_movies && data.all_movies.length > 0) {
        appendShelf('All Movies', data.all_movies, false);
      }

      if (!data.all_movies || data.all_movies.length === 0) {
        shelvesEl.innerHTML = `
          <div style="text-align: center; padding: 60px 20px; color: var(--text-muted);">
            <p style="font-size: 1.1rem; margin-bottom: 8px;">No movies found</p>
            <p style="font-size: 0.9rem;">Click the sync button in the header to import movies from Jellyfin.</p>
          </div>
        `;
      }
    } catch (e) {
      console.error('Failed to load movies home:', e);
      this.showLoading(false);
      this.showToast('Failed to load movies');
    }
  },

  async renderMovieDetail(movieId) {
    if (!this.movieDetailsView) return;
    const heroEl = document.getElementById('movie-details-hero');
    const bodyEl = document.getElementById('movie-details-body');
    if (!heroEl || !bodyEl) return;

    this.showLoading(true);
    try {
      const movie = await api.getMovieDetail(movieId);
      this.showLoading(false);
      if (!movie) {
        this.showToast('Movie not found');
        window.location.hash = '#movies';
        return;
      }

      const heroBg = movie.backdrop_url || movie.poster_url || '';
      const rating = movie.community_rating ? Number(movie.community_rating).toFixed(1) : null;
      const dur = this.formatDurationHuman(movie.duration);
      const genres = Array.isArray(movie.genres) ? movie.genres : [];
      const resumePos = movie.playback_position || 0;
      const isWatched = Boolean(movie.watched);

      let playLabel = 'Play';
      if (resumePos > 15 && !isWatched) {
        playLabel = `Resume (${Player.formatTime(resumePos)})`;
      }

      heroEl.style.backgroundImage = heroBg ? `url("${heroBg}")` : 'none';
      heroEl.innerHTML = `
        <div class="details-hero-layout">
          ${movie.poster_url ? `
            <div class="details-poster-wrap">
              <img src="${movie.poster_url}" alt="${this.escapeHtml(movie.title)}">
            </div>
          ` : ''}
          <div class="details-hero-info">
            <h1 class="details-title">${this.escapeHtml(movie.title)}</h1>
            <div class="details-meta-row">
              ${rating ? `<span class="rating">★ ${rating}</span>` : ''}
              ${movie.release_year ? `<span>${movie.release_year}</span>` : ''}
              ${dur ? `<span>${dur}</span>` : ''}
              ${genres.map(g => `<span class="genre-tag">${this.escapeHtml(g)}</span>`).join('')}
            </div>
            ${movie.overview ? `<p class="details-overview">${this.escapeHtml(movie.overview)}</p>` : ''}
            <div class="details-actions-row">
              <button class="btn-details-play" id="movie-play-btn">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                <span>${playLabel}</span>
              </button>
              <button class="btn-details-action" id="movie-watched-btn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
                <span id="movie-watched-btn-label">${isWatched ? 'Mark as Unwatched' : 'Mark as Watched'}</span>
              </button>
              <button class="btn-details-action danger" id="movie-trash-btn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                <span>Trash</span>
              </button>
            </div>
          </div>
        </div>
      `;

      // Event listeners
      document.getElementById('movie-play-btn').addEventListener('click', () => {
        if (window.Player) Player.blessFromUserGesture();
        window.location.hash = `#watch/${encodeURIComponent(movie.movie_id)}`;
      });

      const watchedBtn = document.getElementById('movie-watched-btn');
      const watchedLabel = document.getElementById('movie-watched-btn-label');
      watchedBtn.addEventListener('click', async () => {
        if (movie.watched) {
          await api.markUnwatched(movie.movie_id);
          movie.watched = 0;
          watchedLabel.textContent = 'Mark as Watched';
          this.showToast('Marked as unwatched');
        } else {
          await api.markWatched(movie.movie_id);
          movie.watched = 1;
          watchedLabel.textContent = 'Mark as Unwatched';
          this.showToast('Marked as watched');
        }
        this.updateStats();
      });

      document.getElementById('movie-trash-btn').addEventListener('click', async () => {
        await api.moveToTrash(movie.movie_id);
        this.showToast('Moved movie to Trash');
        this.updateStats();
        window.location.hash = '#movies';
      });

      // Recommendations / More Like This
      bodyEl.innerHTML = '';
      if (movie.recommendations && movie.recommendations.length > 0) {
        const shelf = document.createElement('div');
        shelf.className = 'netflix-shelf';
        shelf.style.marginTop = '24px';
        shelf.innerHTML = `
          <div class="shelf-header">
            <h3 class="shelf-title">More Like This</h3>
          </div>
          <div class="shelf-track"></div>
        `;
        const track = shelf.querySelector('.shelf-track');
        movie.recommendations.forEach(rec => {
          track.appendChild(this.createMediaCard(rec, false, `#movie/${encodeURIComponent(rec.movie_id)}`));
        });
        bodyEl.appendChild(shelf);
      }
    } catch (e) {
      console.error('Failed to load movie detail:', e);
      this.showLoading(false);
      this.showToast('Failed to load movie details');
    }
  },

  async renderShowsHome(forceReload = false) {
    if (!this.showsView) return;
    const heroEl = document.getElementById('shows-hero');
    const shelvesEl = document.getElementById('shows-shelves');
    if (!heroEl || !shelvesEl) return;

    this.showLoading(true);
    try {
      const data = await api.getShowsHome();
      this.showLoading(false);

      // 1. Featured Hero
      if (data.featured) {
        const s = data.featured;
        const heroBg = s.backdrop_url || s.poster_url || '';
        const rating = s.community_rating ? Number(s.community_rating).toFixed(1) : null;
        const genres = Array.isArray(s.genres) ? s.genres.slice(0, 3) : [];

        heroEl.style.display = 'flex';
        heroEl.style.backgroundImage = heroBg ? `url("${heroBg}")` : 'none';
        heroEl.innerHTML = `
          <div class="netflix-hero-content">
            <span class="netflix-hero-badge" style="background: rgba(168, 85, 247, 0.35);">Featured Series</span>
            <h1 class="netflix-hero-title">${this.escapeHtml(s.title)}</h1>
            <div class="netflix-hero-meta">
              ${rating ? `<span class="rating-badge" style="color: #c084fc;"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg> ${rating}</span>` : ''}
              ${s.start_year ? `<span>${s.start_year}</span>` : ''}
              ${genres.map(g => `<span class="genre-pill">${this.escapeHtml(g)}</span>`).join('')}
            </div>
            ${s.overview ? `<p class="netflix-hero-overview">${this.escapeHtml(s.overview)}</p>` : ''}
            <div class="netflix-hero-actions">
              <button class="btn-hero-play" id="hero-show-explore-btn">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                <span>Watch Series</span>
              </button>
              <button class="btn-hero-info" id="hero-show-info-btn">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/></svg>
                <span>Episodes & Info</span>
              </button>
            </div>
          </div>
        `;

        document.getElementById('hero-show-explore-btn').addEventListener('click', () => {
          window.location.hash = `#show/${encodeURIComponent(s.show_id)}`;
        });
        document.getElementById('hero-show-info-btn').addEventListener('click', () => {
          window.location.hash = `#show/${encodeURIComponent(s.show_id)}`;
        });
      } else {
        heroEl.style.display = 'none';
      }

      // 2. Shelves
      shelvesEl.innerHTML = '';

      const appendShelf = (title, items, isWide = false) => {
        if (!items || items.length === 0) return;
        const shelf = document.createElement('div');
        shelf.className = 'netflix-shelf';
        shelf.innerHTML = `
          <div class="shelf-header">
            <h3 class="shelf-title">${this.escapeHtml(title)}</h3>
          </div>
          <div class="shelf-track"></div>
        `;
        const track = shelf.querySelector('.shelf-track');
        items.forEach(it => {
          track.appendChild(this.createMediaCard(it, isWide, `#show/${encodeURIComponent(it.show_id)}`));
        });
        shelvesEl.appendChild(shelf);
      };

      // Shelf: Continue Watching
      if (data.continue_watching && data.continue_watching.length > 0) {
        appendShelf('Continue Watching', data.continue_watching, false);
      }

      // Shelf: Recently Added Series
      if (data.recently_added && data.recently_added.length > 0) {
        appendShelf('Recently Added Series', data.recently_added, false);
      }

      // Shelves: 5 Random Genres
      if (data.genres && data.genres.length > 0) {
        data.genres.forEach(gShelf => {
          appendShelf(gShelf.genre, gShelf.shows, false);
        });
      }

      // Shelf: All TV Series
      if (data.all_shows && data.all_shows.length > 0) {
        appendShelf('All TV Series', data.all_shows, false);
      }

      if (!data.all_shows || data.all_shows.length === 0) {
        shelvesEl.innerHTML = `
          <div style="text-align: center; padding: 60px 20px; color: var(--text-muted);">
            <p style="font-size: 1.1rem; margin-bottom: 8px;">No TV shows found</p>
            <p style="font-size: 0.9rem;">Click the sync button in the header to import shows from Jellyfin.</p>
          </div>
        `;
      }
    } catch (e) {
      console.error('Failed to load shows home:', e);
      this.showLoading(false);
      this.showToast('Failed to load shows');
    }
  },

  async renderShowDetail(showId) {
    if (!this.showDetailsView) return;
    const heroEl = document.getElementById('show-details-hero');
    const bodyEl = document.getElementById('show-details-body');
    if (!heroEl || !bodyEl) return;

    this.showLoading(true);
    try {
      const show = await api.getShowDetail(showId);
      this.showLoading(false);
      if (!show) {
        this.showToast('Show not found');
        window.location.hash = '#shows';
        return;
      }

      const heroBg = show.backdrop_url || show.poster_url || '';
      const rating = show.community_rating ? Number(show.community_rating).toFixed(1) : null;
      const genres = Array.isArray(show.genres) ? show.genres : [];
      const nextEp = show.next_episode;

      let playBtnText = 'Play';
      if (nextEp) {
        const isNextResuming = nextEp.playback_position > 15 && !nextEp.watched;
        const prefix = isNextResuming ? 'Resume' : 'Play';
        playBtnText = `${prefix} S${nextEp.season_number}:E${nextEp.episode_number} - ${nextEp.title}`;
      }

      heroEl.style.backgroundImage = heroBg ? `url("${heroBg}")` : 'none';
      heroEl.innerHTML = `
        <div class="details-hero-layout">
          ${show.poster_url ? `
            <div class="details-poster-wrap">
              <img src="${show.poster_url}" alt="${this.escapeHtml(show.title)}">
            </div>
          ` : ''}
          <div class="details-hero-info">
            <h1 class="details-title">${this.escapeHtml(show.title)}</h1>
            <div class="details-meta-row">
              ${rating ? `<span class="rating">★ ${rating}</span>` : ''}
              ${show.start_year ? `<span>${show.start_year}</span>` : ''}
              <span>${show.total_episodes || 0} Episodes</span>
              ${genres.map(g => `<span class="genre-tag">${this.escapeHtml(g)}</span>`).join('')}
            </div>
            ${show.overview ? `<p class="details-overview">${this.escapeHtml(show.overview)}</p>` : ''}
            <div class="details-actions-row">
              ${nextEp ? `
                <button class="btn-details-play" id="show-play-next-btn">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                  <span>${this.escapeHtml(playBtnText)}</span>
                </button>
              ` : ''}
              <button class="btn-details-action danger" id="show-trash-btn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                <span>Trash Series</span>
              </button>
            </div>
          </div>
        </div>
      `;

      if (nextEp) {
        document.getElementById('show-play-next-btn').addEventListener('click', () => {
          if (window.Player) Player.blessFromUserGesture();
          window.location.hash = `#watch/${encodeURIComponent(nextEp.episode_id)}`;
        });
      }

      document.getElementById('show-trash-btn').addEventListener('click', async () => {
        await api.moveToTrash(show.show_id);
        this.showToast('Moved series to Trash');
        this.updateStats();
        window.location.hash = '#shows';
      });

      // Season Tabs and Episodes Grid
      bodyEl.innerHTML = `
        <div class="seasons-section">
          <div class="seasons-tab-bar" id="seasons-tab-bar"></div>
          <div class="episodes-grid" id="episodes-grid"></div>
        </div>
      `;

      const tabBar = document.getElementById('seasons-tab-bar');
      const grid = document.getElementById('episodes-grid');
      const seasons = show.seasons || [];

      // Determine default season to select
      let activeSeasonNum = seasons.length > 0 ? seasons[0].season_number : 1;
      if (nextEp && seasons.some(s => s.season_number === nextEp.season_number)) {
        activeSeasonNum = nextEp.season_number;
      }

      const renderEpisodesForSeason = (seasonNum) => {
        grid.innerHTML = '';
        const season = seasons.find(s => s.season_number === seasonNum);
        if (!season || !season.episodes || season.episodes.length === 0) {
          grid.innerHTML = `<div style="color: var(--text-muted); padding: 20px;">No episodes available for this season.</div>`;
          return;
        }

        season.episodes.forEach(ep => {
          const isNext = nextEp && (nextEp.episode_id === ep.episode_id);
          const isWatched = Boolean(ep.watched);
          const durStr = this.formatDurationHuman(ep.duration);
          const epThumb = ep.thumbnail_url || show.backdrop_url || show.poster_url || '';

          const card = document.createElement('div');
          card.className = 'episode-card';
          if (isNext) {
            card.style.borderColor = 'var(--accent-red)';
            card.style.boxShadow = '0 0 14px rgba(255, 0, 0, 0.25)';
          }

          card.innerHTML = `
            <div class="episode-thumb-box">
              ${epThumb ? `<img src="${epThumb}" loading="lazy" alt="${this.escapeHtml(ep.title)}">` : ''}
              <div class="episode-play-icon">
                <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
              </div>
              ${durStr ? `<span class="episode-duration-badge">${durStr}</span>` : ''}
              ${isWatched ? `<span class="card-watched-badge" style="position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.85); color: #4ade80; font-size: 0.65rem; font-weight: 800; padding: 2px 6px; border-radius: 3px;">WATCHED</span>` : ''}
              ${isNext ? `<span style="position: absolute; top: 8px; right: 8px; background: var(--accent-red); color: #fff; font-size: 0.65rem; font-weight: 800; padding: 2px 6px; border-radius: 3px; letter-spacing: 0.5px;">NEXT UP</span>` : ''}
              ${!isWatched && ep.progress_percent > 0 ? `
                <div class="card-progress-bar" style="position: absolute; bottom: 0; left: 0; right: 0; height: 4px; background: rgba(255,255,255,0.25);">
                  <div class="card-progress-bar-fill" style="height: 100%; background: var(--accent-red); width: ${Math.min(100, ep.progress_percent)}%;"></div>
                </div>
              ` : ''}
            </div>
            <div class="episode-body">
              <div class="episode-header">
                <div class="episode-title">${this.escapeHtml(ep.title)}</div>
                <button type="button" class="btn-icon card-action-btn episode-action-btn" title="More options" aria-label="More options for ${this.escapeHtml(ep.title)}">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 2 .9 2 2 2 .9 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>
                </button>
              </div>
              ${ep.overview ? `<div class="episode-desc">${this.escapeHtml(ep.overview)}</div>` : ''}
            </div>
          `;

          card.addEventListener('click', () => {
          if (window.Player) Player.blessFromUserGesture();
          window.location.hash = `#watch/${encodeURIComponent(ep.episode_id)}`;
          });

          card.querySelector('.episode-action-btn').addEventListener('click', (event) => {
          event.stopPropagation();
          this.openPopover(event.currentTarget, {
            ...ep,
            video_id: ep.episode_id,
            media_type: 'episode',
          }, card);
          });

          grid.appendChild(card);
        });
      };

      // Create tabs
      seasons.forEach(season => {
        const tab = document.createElement('button');
        tab.className = `season-tab ${season.season_number === activeSeasonNum ? 'active' : ''}`;
        tab.textContent = season.season_name || `Season ${season.season_number}`;
        tab.addEventListener('click', () => {
          tabBar.querySelectorAll('.season-tab').forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          renderEpisodesForSeason(season.season_number);
        });
        tabBar.appendChild(tab);
      });

      renderEpisodesForSeason(activeSeasonNum);

    } catch (e) {
      console.error('Failed to load show detail:', e);
      this.showLoading(false);
      this.showToast('Failed to load show details');
    }
  },

  escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
};

window.App = App;
document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
