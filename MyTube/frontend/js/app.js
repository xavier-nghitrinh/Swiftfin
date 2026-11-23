/**
 * MyTube Application Controller
 * Handles SPA page tracking, YouTube-style Watch View, 2-option popover menu,
 * local cached thumbnails, and mobile swipe navigation.
 */

const App = {
  currentRoute: 'home',
  previousRouteHash: '#home',
  routeHistory: [],
  currentChannelId: null,
  scraperChannels: [],
  unconfiguredChannels: [], // MyTube channels with no channels.json entry; shown so their config can be added
  mytubeChannelsByName: new Map(), // MyTube channels keyed by lowercase name, to match channels.json entries
  scraperEditingName: null, // Original name of the channel being edited; null when adding
  currentWatchData: null,
  upNextSource: 'feed', // 'feed' or 'channel'
  channelSubscriptionFilter: 'all', // 'all', 'subscribed', 'unsubscribed'
  youtubeUnwatchedOnly: true, // Shared Unwatched / All Videos toggle for Subscriptions, Channel, Gone soon and Movies
  searchQuery: '',
  musicRenderToken: 0, // Guards against stale async music renders
  musicSearchToken: 0,

  // Pagination
  feedOffset: 0,
  feedLimit: 10,
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
  musicView: null,
  musicContent: null,
  headerBackBtn: null,
  videoGrid: null,
  continueWatchingShelf: null,
  continueWatchingTrack: null,
  viewTitle: null,
  channelHeaderAvatar: null,
  scraperPanel: null,
  scraperAddBtn: null,
  scraperForm: null,
  scraperSaveBtn: null,
  scraperStatus: null,
  scraperFormError: null,
  scraperList: null,
  scraperDeleteBtn: null,
  filterChips: null,
  loadingSpinner: null,
  emptyState: null,
  badgeUnwatched: null,
  searchInput: null,
  popoverMenu: null,
  toastEl: null,

  icons: {
    bell: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" fill="currentColor"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
    bellOff: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13.73 21a2 2 0 0 1-3.46 0"/><path d="M18.63 13A17.89 17.89 0 0 1 18 8"/><path d="M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14"/><path d="M18 8a6 6 0 0 0-9.33-5"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',
    pencil: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>',
  },

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
    this.musicView = document.getElementById('music-view');
    this.musicContent = document.getElementById('music-content');
    this.headerBackBtn = document.getElementById('header-back-btn');
    this.videoGrid = document.getElementById('video-grid');
    this.continueWatchingShelf = document.getElementById('feed-continue-watching');
    this.continueWatchingTrack = document.getElementById('feed-continue-watching-track');
    this.viewTitle = document.getElementById('view-title');
    this.channelHeaderAvatar = document.getElementById('channel-header-avatar');
    this.scraperPanel = document.getElementById('scraper-panel');
    this.scraperAddBtn = document.getElementById('scraper-add-btn');
    this.scraperForm = document.getElementById('scraper-form');
    this.scraperSaveBtn = document.getElementById('scraper-save-btn');
    this.scraperStatus = document.getElementById('scraper-status');
    this.scraperFormError = document.getElementById('scraper-form-error');
    this.scraperList = document.getElementById('scraper-list');
    this.scraperDeleteBtn = document.getElementById('scraper-delete-btn');
    this.scraperAddBtn.addEventListener('click', () => this.openScraperForm());
    this.scraperDeleteBtn.addEventListener('click', () => this.removeScraperChannel(this.scraperEditingName));
    document.getElementById('scraper-cancel-btn').addEventListener('click', () => this.closeScraperForm());
    this.scraperForm.addEventListener('submit', (event) => this.saveScraperChannel(event));
    this.filterChips = document.getElementById('filter-chips');
    this.loadingSpinner = document.getElementById('loading-spinner');
    this.emptyState = document.getElementById('empty-state');
    this.badgeUnwatched = document.getElementById('badge-unwatched');
    this.searchInput = document.getElementById('search-input');
    this.popoverMenu = document.getElementById('card-popover-menu');
    this.toastEl = document.getElementById('toast-notification');

    Player.init();
    MusicPlayer.init();
    this.bindEvents();
    this.setupSwipeNavigation();

    window.addEventListener('hashchange', () => this.handleRoute());
    window.addEventListener('mytube:user-invalid', () => this.returnToUserSelection());
    window.addEventListener('mytube:music-changed', (e) => this.onMusicChanged(e.detail));
    window.addEventListener('mytube:subtitle-changed', (e) => this.onWatchSubtitleChanged(e.detail));
    document.getElementById('watch-ai-btn').addEventListener('click', () => this.generateWatchAi());
    // Links in the AI note open in a new tab so the app stays open
    DOMPurify.addHook('afterSanitizeAttributes', (node) => {
      if (node.tagName === 'A') {
        node.setAttribute('target', '_blank');
        node.setAttribute('rel', 'noopener noreferrer');
      }
    });

    if (api.getUserId()) {
      this.enterApp();
    } else {
      this.showUserSelection();
    }
  },

  bindEvents() {
    // Logo click returns to home; when already on home, reload it so the feed is fresh
    document.getElementById('logo-btn').addEventListener('click', () => {
      if ((window.location.hash || '#home') === '#home') {
        this.handleRoute(true);
      } else {
        window.location.hash = '#home';
      }
    });

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
        if (this.currentRoute === 'home' && this.youtubeUnwatchedOnly && cardEl) {
          document.getElementById(`video-card-${video.video_id}`)?.remove();
          document.getElementById(`continue-video-card-${video.video_id}`)?.remove();
          this.renderContinueWatchingShelf();
        } else {
          this.handleRoute(true);
        }
      }
      this.updateStats();
    });

    document.getElementById('logout-btn').addEventListener('click', () => this.logout());

    document.getElementById('user-new-btn').addEventListener('click', () => this.toggleNewUserForm(true));
    document.getElementById('user-create-cancel-btn').addEventListener('click', () => this.toggleNewUserForm(false));
    document.getElementById('user-create-form').addEventListener('submit', (e) => {
      e.preventDefault();
      this.createUserFromForm();
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
      if (this.currentRoute !== 'home' && !this.currentRoute.startsWith('#channel/') && this.currentRoute !== '#gone-soon') return;
      if (this.isLoading || !this.feedHasMore) return;

      const scrollBottom = window.innerHeight + window.scrollY;
      if (scrollBottom >= document.documentElement.offsetHeight - 400) {
        this.loadMore();
      }
    }, { passive: true });

    window.addEventListener('resize', () => {
      this.syncContinueWatchingCardWidth();
      this.loadMoreIfNeeded();
    });
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

  // =========================================================
  // User Selection & Logout
  // =========================================================
  enterApp() {
    document.body.classList.remove('user-select-active');
    this.handleRoute();
    this.updateStats();
  },

  resetSessionState() {
    if (Player.isActive) Player.stop();
    MusicPlayer.stop();
    this.hidePopover();
    this.routeHistory = [];
    this.currentWatchData = null;
    this.currentWatchVideoId = null;
    this.currentRoute = 'home';
  },

  showUserSelection() {
    this.resetSessionState();
    document.body.classList.add('user-select-active');
    this.renderUserSelection();
  },

  selectUser(user) {
    api.setUser(user);
    this.enterApp();
  },

  logout() {
    this.returnToUserSelection();
  },

  returnToUserSelection() {
    if (Player.isActive) Player.stop();
    api.clearUser();
    window.location.hash = '#home';
    this.showUserSelection();
  },

  async renderUserSelection() {
    const listEl = document.getElementById('user-select-list');
    const statusEl = document.getElementById('user-select-status');
    listEl.innerHTML = '';
    statusEl.textContent = 'Loading users...';
    this.toggleNewUserForm(false);

    try {
      const users = await api.getUsers();
      statusEl.textContent = users.length === 0 ? 'No users yet. Create one to get started.' : '';
      users.forEach((user) => listEl.appendChild(this.createUserCard(user)));
    } catch (err) {
      console.error('Failed to load users:', err);
      statusEl.textContent = 'Could not load users. Check the server and try again.';
    }
  },

  createUserCard(user) {
    const card = document.createElement('div');
    card.className = 'channel-card';

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'channel-avatar';
    this.populateAvatarElement(avatarDiv, user.name, null);

    const nameDiv = document.createElement('div');
    nameDiv.className = 'channel-card-name';
    nameDiv.textContent = user.name;

    card.append(avatarDiv, nameDiv);

    let pressTimer = null;
    let longPressed = false;
    const cancelPress = () => {
      clearTimeout(pressTimer);
      pressTimer = null;
    };
    card.addEventListener('pointerdown', () => {
      longPressed = false;
      cancelPress();
      pressTimer = setTimeout(() => {
        pressTimer = null;
        longPressed = true;
        this.confirmDeleteUser(user);
      }, 700);
    });
    card.addEventListener('pointerup', cancelPress);
    card.addEventListener('pointerleave', cancelPress);
    card.addEventListener('pointercancel', cancelPress);
    card.addEventListener('contextmenu', (e) => e.preventDefault());
    card.addEventListener('click', (e) => {
      if (longPressed) {
        e.preventDefault();
        longPressed = false;
        return;
      }
      this.selectUser(user);
    });
    return card;
  },

  async confirmDeleteUser(user) {
    const confirmed = window.confirm(`Delete user "${user.name}"? Their subscriptions and watch progress will be removed.`);
    if (!confirmed) return;

    const statusEl = document.getElementById('user-select-status');
    try {
      await api.deleteUser(user.user_id);
      this.showToast(`Deleted user ${user.name}`);
      this.renderUserSelection();
    } catch (err) {
      console.error('Failed to delete user:', err);
      statusEl.textContent = 'Could not delete user. Try again.';
    }
  },

  toggleNewUserForm(show) {
    const form = document.getElementById('user-create-form');
    const input = document.getElementById('user-create-input');
    form.style.display = show ? 'flex' : 'none';
    document.getElementById('user-new-btn').style.display = show ? 'none' : '';
    document.getElementById('user-create-error').textContent = '';
    if (show) {
      input.value = '';
      input.focus();
    }
  },

  async createUserFromForm() {
    const input = document.getElementById('user-create-input');
    const errorEl = document.getElementById('user-create-error');
    const name = input.value.trim();
    errorEl.textContent = '';

    if (!name) {
      errorEl.textContent = 'Name is required';
      return;
    }

    try {
      const user = await api.createUser(name);
      this.selectUser(user);
    } catch (err) {
      errorEl.textContent = err.message;
    }
  },

  async updateStats() {
    try {
      const stats = await api.getStats();
      if (stats.unwatched_recent_videos > 0) {
        this.badgeUnwatched.textContent = stats.unwatched_recent_videos > 99 ? '99+' : stats.unwatched_recent_videos;
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

  handleRoute(forceReload = false) {
    if (!api.getUserId()) {
      if (!document.body.classList.contains('user-select-active')) this.showUserSelection();
      return;
    }

    const hash = window.location.hash || '#home';
    this.hidePopover();

    // Track route history
    if (this.routeHistory[this.routeHistory.length - 1] !== hash) {
      this.routeHistory.push(hash);
      if (this.routeHistory.length > 20) this.routeHistory.shift();
    }

    // Show header back button when not on root hubs
    const isRoot = (hash === '#home' || hash === '#movies' || hash === '#shows' || hash === '#music');
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
      if (this.musicView) this.musicView.style.display = 'none';
    };

    // 1. Watch View
    if (hash.startsWith('#watch/')) {
      hideAllViews();
      MusicPlayer.pause();
      MusicPlayer.closeNow();
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
      if (this.showDetailsView) this.showDetailsView.style.display = 'block';
      window.scrollTo(0, 0);
      this.renderShowDetail(showId);
      return;
    }

    // 7. Music Views (Home, Songs, Artists, Collections, Favorites, Playlists, Search)
    if (hash === '#music' || hash.startsWith('#music/')) {
      hideAllViews();
      this.currentRoute = hash;
      this.setActiveNav('nav-music');
      if (this.musicView) this.musicView.style.display = 'block';
      window.scrollTo(0, 0);
      this.renderMusicRoute(hash);
      return;
    }

    // 6. YouTube Browse Views (Home, Channels, Channel, Search); always reloaded on entry
    hideAllViews();
    this.browseView.style.display = 'block';
    this.channelHeaderAvatar.style.display = 'none';
    this.scraperPanel.style.display = 'none';
    window.scrollTo(0, 0);

    this.feedOffset = 0;
    this.feedHasMore = true;
    if (this.continueWatchingShelf) {
      this.continueWatchingShelf.style.display = 'none';
    }

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
    } else if (hash === '#gone-soon') {
      this.currentRoute = hash;
      this.setActiveNav('nav-gone');
      this.renderGoneSoon();
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
  // Music Views
  // =========================================================
  renderMusicRoute(hash) {
    const parts = hash.slice('#music'.length).split('/').filter(Boolean);
    const section = parts[0] || 'home';
    const param = parts.length > 1 ? decodeURIComponent(parts.slice(1).join('/')) : '';
    const tabForSection = { artist: 'artists', collection: 'collections', playlist: 'playlists' };
    this.setMusicTabs(tabForSection[section] || section);

    const token = ++this.musicRenderToken;
    this.musicContent.replaceChildren(this.musicMessage('Loading...'));
    this.buildMusicView(section, param)
      .then((nodes) => {
        if (token === this.musicRenderToken) this.musicContent.replaceChildren(...nodes);
      })
      .catch((err) => {
        if (token === this.musicRenderToken) {
          this.musicContent.replaceChildren(this.musicMessage(`Failed to load music: ${err.message}`));
        }
      });
  },

  setMusicTabs(active) {
    document.querySelectorAll('#music-tabs [data-music-tab]').forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.musicTab === active);
    });
  },

  countLabel(count, noun) {
    return `${count} ${noun}${count === 1 ? '' : 's'}`;
  },

  async buildMusicView(section, param) {
    switch (section) {
      case 'songs': {
        const { tracks } = await api.getMusicTracks();
        return this.musicTrackView(tracks, { title: 'Songs',         subtitle: this.countLabel(tracks.length, 'song'), emptyText: 'No songs found' });
      }
      case 'artists': {
        const { artists } = await api.getMusicArtists();
        const cards = artists.map((artist) => this.musicCard({
          image: artist.image_url,
          title: artist.name,
          subtitle: this.countLabel(artist.track_count, 'song'),
          round: true,
          onClick: () => { window.location.hash = `#music/artist/${encodeURIComponent(artist.name)}`; }
        }));
        return [
          this.musicPageHeader('Artists', this.countLabel(artists.length, 'artist')),
          cards.length ? this.musicGrid(cards) : this.musicMessage('No artists found')
        ];
      }
      case 'artist': {
        const { artist, tracks } = await api.getMusicArtist(param);
        return this.musicTrackView(tracks, { title: artist.name, subtitle: this.countLabel(tracks.length, 'song'), emptyText: 'No songs found' });
      }
      case 'collections': {
        const { collections } = await api.getMusicCollections();
        const cards = collections.map((collection) => this.musicCard({
          image: collection.image_url,
          title: collection.name,
          subtitle: this.countLabel(collection.track_count, 'song'),
          onClick: () => { window.location.hash = `#music/collection/${encodeURIComponent(collection.name)}`; }
        }));
        return [
          this.musicPageHeader('Collections', 'Grouped by the source playlist in Jellyfin'),
          cards.length ? this.musicGrid(cards) : this.musicMessage('No collections found')
        ];
      }
      case 'collection': {
        const { collection, tracks } = await api.getMusicCollection(param);
        return this.musicTrackView(tracks, { title: collection.name,         subtitle: this.countLabel(tracks.length, 'song'), emptyText: 'No songs found' });
      }
      case 'favorites': {
        const { tracks } = await api.getMusicFavorites();
        return this.musicTrackView(tracks, {
          title: 'Favorites',
          subtitle:           this.countLabel(tracks.length, 'song'),
          emptyText: 'No favorites yet. Tap the heart on a song to save it here.'
        });
      }
      case 'playlists': {
        const { playlists } = await api.getMusicPlaylists();
        const form = this.musicEl('form', 'music-playlist-form');
        form.autocomplete = 'off';
        const input = this.musicEl('input', 'music-playlist-input');
        input.type = 'text';
        input.maxLength = 80;
        input.placeholder = 'New playlist name';
        input.required = true;
        const submit = this.musicEl('button', 'chip active', 'Create');
        submit.type = 'submit';
        form.append(input, submit);
        form.addEventListener('submit', (event) => this.createMusicPlaylistFromForm(event, input));

        const cards = playlists.map((playlist) => this.musicCard({
          title: playlist.name,
          subtitle: this.countLabel(playlist.track_count, 'song'),
          onClick: () => { window.location.hash = `#music/playlist/${encodeURIComponent(playlist.playlist_id)}`; }
        }));
        return [
          this.musicPageHeader('Playlists', this.countLabel(playlists.length, 'playlist')),
          form,
          cards.length ? this.musicGrid(cards) : this.musicMessage('No playlists yet')
        ];
      }
      case 'playlist': {
        const playlist = await api.getMusicPlaylist(param);
        return this.musicTrackView(playlist.tracks, {
          title: playlist.name,
          subtitle:           this.countLabel(playlist.track_count, 'song'),
          emptyText: 'This playlist is empty. Use the more menu on a song to add it here.',
          actions: [
            { label: 'Rename', onClick: () => this.renameMusicPlaylist(playlist) },
            { label: 'Delete', onClick: () => this.deleteMusicPlaylist(playlist) }
          ],
          onRemove: async (track) => {
            await api.removeMusicPlaylistItem(playlist.playlist_id, track.item_id);
            this.renderMusicRoute(window.location.hash);
          }
        });
      }
      case 'search': {
        const input = this.musicEl('input', 'music-search-input');
        input.type = 'search';
        input.placeholder = 'Search songs';
        input.maxLength = 100;
        input.autocomplete = 'off';
        const results = this.musicEl('div', 'music-search-results');
        results.append(this.musicMessage('Type to search your songs'));
        let timer = null;
        input.addEventListener('input', () => {
          clearTimeout(timer);
          timer = setTimeout(() => this.runMusicSearch(input.value, results), 250);
        });
        return [input, results];
      }
      default:
        return this.buildMusicHome();
    }
  },

  async buildMusicHome() {
    const data = await api.getMusicHome();
    const cardsFor = (items, toCard) => (items || []).map(toCard);
    const artistCards = cardsFor(data.random_artists, (artist) => this.musicCard({
      image: artist.image_url,
      title: artist.name,
      subtitle: this.countLabel(artist.track_count, 'song'),
      round: true,
      onClick: () => { window.location.hash = `#music/artist/${encodeURIComponent(artist.name)}`; }
    }));
    const collectionCards = cardsFor(data.random_collections, (collection) => this.musicCard({
      image: collection.image_url,
      title: collection.name,
      subtitle: this.countLabel(collection.track_count, 'song'),
      onClick: () => { window.location.hash = `#music/collection/${encodeURIComponent(collection.name)}`; }
    }));
    const playlistCards = cardsFor(data.playlists, (playlist) => this.musicCard({
      title: playlist.name,
      subtitle: this.countLabel(playlist.track_count, 'song'),
      onClick: () => { window.location.hash = `#music/playlist/${encodeURIComponent(playlist.playlist_id)}`; }
    }));

    const shelves = [
      this.musicTrackShelf('Random picks', data.random_tracks),
      this.musicTrackShelf('Favorites', data.favorites),
      this.musicTrackShelf('Recently played', data.recently_played),
      this.musicTrackShelf('Long time no listen', data.forgotten),
      this.musicCardShelf('Artists', artistCards),
      this.musicCardShelf('Collections', collectionCards),
      this.musicCardShelf('Playlists', playlistCards)
    ].filter(Boolean);

    const nodes = [this.musicPageHeader('Music', `${this.countLabel(data.total_tracks || 0, 'song')} in your library`)];
    if (!shelves.length) {
      nodes.push(this.musicMessage('No music yet. Sync the library to load your Jellyfin Music.'));
    } else {
      nodes.push(this.musicEl('div', 'music-shelves'));
      nodes[nodes.length - 1].append(...shelves);
    }
    return nodes;
  },

  musicEl(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  },

  musicMessage(text) {
    return this.musicEl('div', 'music-empty', text);
  },

  musicPageHeader(title, subtitle = '', actions = []) {
    const header = this.musicEl('div', 'music-page-header');
    const heading = this.musicEl('div', 'music-page-heading');
    heading.append(this.musicEl('h2', 'music-page-title', title));
    if (subtitle) heading.append(this.musicEl('div', 'music-page-subtitle', subtitle));
    header.append(heading);
    if (actions.length) header.append(this.musicActions(actions));
    return header;
  },

  musicActions(actions) {
    const wrap = this.musicEl('div', 'music-actions');
    actions.forEach(({ label, onClick }) => {
      const btn = this.musicEl('button', 'chip', label);
      btn.type = 'button';
      btn.addEventListener('click', onClick);
      wrap.append(btn);
    });
    return wrap;
  },

  musicPlayActions(tracks) {
    return [
      { label: 'Play', onClick: () => MusicPlayer.playList(tracks, 0) },
      { label: 'Shuffle', onClick: () => MusicPlayer.playList(tracks, 0, { shuffle: true }) }
    ];
  },

  musicTrackView(tracks, { title, subtitle = '', emptyText, actions = [], onRemove = null }) {
    const nodes = [this.musicPageHeader(title, subtitle, actions)];
    if (!tracks || !tracks.length) {
      nodes.push(this.musicMessage(emptyText));
      return nodes;
    }
    nodes.push(this.musicActions(this.musicPlayActions(tracks)), this.musicTrackRows(tracks, onRemove));
    return nodes;
  },

  musicTrackRows(tracks, onRemove = null) {
    const list = this.musicEl('div', 'music-track-list');
    tracks.forEach((track, i) => list.append(this.musicTrackRow(track, tracks, i, onRemove)));
    return list;
  },

  musicTrackRow(track, tracks, index, onRemove) {
    const row = this.musicEl('div', 'music-row');

    const art = this.musicEl('img', 'music-art music-row-art');
    art.alt = '';
    art.loading = 'lazy';
    if (track.image_url) art.src = track.image_url;

    const info = this.musicEl('button', 'music-row-info');
    info.type = 'button';
    info.append(
      this.musicEl('div', 'music-row-title', track.title),
      this.musicEl('div', 'music-row-sub', [track.artist, track.source_group].filter(Boolean).join(' · '))
    );
    info.addEventListener('click', () => MusicPlayer.playList(tracks, index));

    const duration = this.musicEl('div', 'music-row-duration', MusicPlayer.formatTime(track.duration));

    const fav = this.musicIconButton('Favorite', this.musicIcons.heart, `music-favorite-btn music-row-fav${track.favorite ? ' active' : ''}`);
    fav.dataset.trackId = track.track_id;
    fav.setAttribute('aria-pressed', String(!!track.favorite));
    fav.addEventListener('click', () => MusicPlayer.toggleFavorite(track));

    const more = this.musicIconButton('More options', this.musicIcons.more);
    more.addEventListener('click', () => MusicPlayer.openPicker(track));

    row.append(art, info, duration, fav, more);

    if (onRemove) {
      const remove = this.musicIconButton('Remove from playlist', this.musicIcons.close);
      remove.addEventListener('click', async () => {
        try {
          await onRemove(track);
        } catch (err) {
          this.showToast(err.message);
        }
      });
      row.append(remove);
    }
    return row;
  },

  musicIcons: {
    heart: '<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>',
    more: '<path fill="currentColor" d="M6 10c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm12 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-6 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/>',
    close: '<path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>'
  },

  musicIconButton(label, svgInner, className = '') {
    const btn = this.musicEl('button', `music-icon-btn ${className}`.trim());
    btn.type = 'button';
    btn.setAttribute('aria-label', label);
    btn.innerHTML = `<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">${svgInner}</svg>`;
    return btn;
  },

  musicCard({ image, title, subtitle = '', round = false, onClick }) {
    const card = this.musicEl('button', 'music-card');
    card.type = 'button';
    const art = this.musicEl('img', round ? 'music-card-art round' : 'music-card-art');
    art.alt = '';
    art.loading = 'lazy';
    if (image) art.src = image;
    card.append(art, this.musicEl('div', 'music-card-title', title), this.musicEl('div', 'music-card-sub', subtitle));
    card.addEventListener('click', onClick);
    return card;
  },

  musicGrid(cards) {
    const grid = this.musicEl('div', 'music-grid');
    grid.append(...cards);
    return grid;
  },

  musicShelf(title, body, actions = []) {
    const shelf = this.musicEl('section', 'music-shelf');
    const header = this.musicEl('div', 'music-shelf-header');
    header.append(this.musicEl('h3', 'music-shelf-title', title));
    if (actions.length) header.append(this.musicActions(actions));
    shelf.append(header, body);
    return shelf;
  },

  musicTrackShelf(title, tracks) {
    if (!tracks || !tracks.length) return null;
    const track = this.musicEl('div', 'music-shelf-track');
    tracks.forEach((item, i) => track.append(this.musicCard({
      image: item.image_url,
      title: item.title,
      subtitle: item.artist || '',
      onClick: () => MusicPlayer.playList(tracks, i)
    })));
    return this.musicShelf(title, track, this.musicPlayActions(tracks));
  },

  musicCardShelf(title, cards) {
    if (!cards.length) return null;
    const track = this.musicEl('div', 'music-shelf-track');
    track.append(...cards);
    return this.musicShelf(title, track);
  },

  async runMusicSearch(query, container) {
    const q = query.trim();
    const token = ++this.musicSearchToken;
    if (!q) {
      container.replaceChildren(this.musicMessage('Type to search your songs'));
      return;
    }
    try {
      const { tracks } = await api.getMusicTracks(q);
      if (token !== this.musicSearchToken) return;
      container.replaceChildren(tracks.length ? this.musicTrackRows(tracks) : this.musicMessage('No songs match your search'));
    } catch (err) {
      if (token !== this.musicSearchToken) return;
      container.replaceChildren(this.musicMessage(`Search failed: ${err.message}`));
    }
  },

  async createMusicPlaylistFromForm(event, input) {
    event.preventDefault();
    const name = input.value.trim();
    if (!name) return;
    try {
      const playlist = await api.createMusicPlaylist(name);
      window.location.hash = `#music/playlist/${encodeURIComponent(playlist.playlist_id)}`;
    } catch (err) {
      this.showToast(err.message);
    }
  },

  async renameMusicPlaylist(playlist) {
    const name = window.prompt('Playlist name', playlist.name);
    if (name === null || !name.trim()) return;
    try {
      await api.renameMusicPlaylist(playlist.playlist_id, name.trim());
      this.renderMusicRoute(window.location.hash);
    } catch (err) {
      this.showToast(err.message);
    }
  },

  async deleteMusicPlaylist(playlist) {
    if (!window.confirm(`Delete playlist "${playlist.name}"?`)) return;
    try {
      await api.deleteMusicPlaylist(playlist.playlist_id);
      window.location.hash = '#music/playlists';
    } catch (err) {
      this.showToast(err.message);
    }
  },

  onMusicChanged({ trackId, favorite }) {
    const onFavorites = window.location.hash === '#music/favorites';
    document.querySelectorAll('.music-row-fav').forEach((btn) => {
      if (btn.dataset.trackId !== trackId) return;
      if (!favorite && onFavorites) {
        btn.closest('.music-row').remove();
        return;
      }
      btn.classList.toggle('active', favorite);
      btn.setAttribute('aria-pressed', String(favorite));
    });
  },

  // =========================================================
  // YouTube-Style Watch View
  // =========================================================
  async renderWatchView(videoId) {
    this.currentWatchVideoId = videoId;
    this.onWatchSubtitleChanged(null);
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

    const watchTitle = cleanVideoTitle(data.title);
    if (data.media_type === 'movie') {
      document.getElementById('watch-video-title').textContent = watchTitle;
      document.getElementById('watch-channel-name').textContent = `Movie (${data.upload_date || 'Film'})`;
      document.getElementById('watch-upload-date').textContent = data.duration ? this.formatDurationHuman(data.duration) : '';
    } else if (data.media_type === 'episode') {
      document.getElementById('watch-video-title').textContent = watchTitle;
      document.getElementById('watch-channel-name').textContent = data.channel_name;
      document.getElementById('watch-upload-date').textContent = data.duration ? this.formatDurationHuman(data.duration) : '';
    } else {
      document.getElementById('watch-video-title').textContent = watchTitle;
      document.getElementById('watch-channel-name').textContent = data.channel_name;
      document.getElementById('watch-upload-date').textContent = data.upload_date
        ? `Uploaded ${this.formatUploadDate(data.upload_date)}`
        : '';
    }

    const avatarBox = document.getElementById('watch-channel-avatar');
    this.populateAvatarElement(avatarBox, data.channel_name, data.channel_thumbnail_url);

    this.updateWatchWatchedButton(Boolean(data.watched));

    this.renderWatchDescription(data.description);

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

  // Shows a short preview ending in "…" with a "more" toggle; the full text is never clipped in a scroll box
  renderWatchDescription(description) {
    const descEl = document.getElementById('watch-description');
    const text = (description || '').trim();
    descEl.innerHTML = '';
    if (!text) {
      descEl.style.display = 'none';
      return;
    }
    descEl.style.display = 'block';

    const previewLength = 150;
    const isLong = text.length > previewLength;
    const preview = isLong ? `${text.slice(0, previewLength).replace(/\s+\S*$/, '')}…` : text;

    const bodyEl = document.createElement('span');
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'watch-description-toggle';
    let expanded = false;
    const render = () => {
      bodyEl.textContent = expanded ? text : preview;
      toggle.textContent = expanded ? ' less' : ' more';
    };
    toggle.addEventListener('click', () => {
      expanded = !expanded;
      render();
    });

    descEl.append(bodyEl, toggle);
    if (isLong) {
      render();
    } else {
      bodyEl.textContent = text;
      toggle.remove();
    }
  },

  // The AI button is only offered while a subtitle track is selected; its result belongs to that track
  onWatchSubtitleChanged(subtitle) {
    this.watchAiSubtitle = subtitle;
    this.watchAiRequestId = (this.watchAiRequestId || 0) + 1;
    document.getElementById('watch-ai-row').style.display = subtitle ? 'flex' : 'none';
    const resultEl = document.getElementById('watch-ai-result');
    resultEl.style.display = 'none';
    resultEl.innerHTML = '';
  },

  async generateWatchAi() {
    const subtitle = this.watchAiSubtitle;
    if (!subtitle) return;
    const requestId = (this.watchAiRequestId = (this.watchAiRequestId || 0) + 1);
    this.showWatchAiStatus(`Synthesizing the full ${subtitle.label} subtitle track…`);

    try {
      const result = await api.synthesizeSubtitle(subtitle.videoId, subtitle.index);
      if (requestId !== this.watchAiRequestId) return;
      this.renderWatchAiResult(result.markdown, subtitle.label);
    } catch (e) {
      if (requestId !== this.watchAiRequestId) return;
      this.showWatchAiStatus(e.message || 'Synthesis failed', true);
    }
  },

  showWatchAiStatus(message, isError = false) {
    const resultEl = document.getElementById('watch-ai-result');
    resultEl.innerHTML = '';
    resultEl.style.display = 'block';
    const status = document.createElement('div');
    status.className = `watch-ai-status${isError ? ' watch-ai-error' : ''}`;
    status.textContent = message;
    resultEl.appendChild(status);
    if (isError) {
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'watch-ai-retry';
      retry.textContent = 'Try again';
      retry.addEventListener('click', () => this.generateWatchAi());
      resultEl.appendChild(retry);
    }
  },

  renderWatchAiResult(markdown, label) {
    const resultEl = document.getElementById('watch-ai-result');
    resultEl.innerHTML = '';
    resultEl.style.display = 'block';

    const header = document.createElement('div');
    header.className = 'watch-ai-result-header';
    const title = document.createElement('span');
    title.textContent = label ? `AI Synthesis · ${label}` : 'AI Synthesis';
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'watch-ai-close';
    close.textContent = 'Hide';
    close.addEventListener('click', () => this.onWatchSubtitleChanged(this.watchAiSubtitle));
    header.append(title, close);

    const body = document.createElement('div');
    body.innerHTML = this.renderMarkdown(markdown);
    resultEl.append(header, body);
  },

  // marked renders the AI note; DOMPurify sanitizes the output because the text comes from a model
  renderMarkdown(markdown) {
    return DOMPurify.sanitize(marked.parse(markdown || '', { gfm: true, breaks: true }));
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
    const title = cleanVideoTitle(video.title);
    const uploadTimeAgo = this.formatUploadDate(video.upload_date);

    let progressPercent = 0;
    if (video.duration > 0 && video.playback_position > 0 && !video.watched) {
      progressPercent = Math.min(100, (video.playback_position / video.duration) * 100);
    }

    card.innerHTML = `
      <div class="thumbnail-box">
        <img src="${thumbUrl}" loading="lazy" alt="${this.escapeHtml(title)}">
        <span class="duration-badge">${durStr}</span>
        ${video.watched ? `<span class="watched-badge">WATCHED</span>` : ''}
        ${progressPercent > 0 ? `<div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${progressPercent}%;"></div></div>` : ''}
      </div>
      <div class="video-info">
        <h4 class="video-title">${this.escapeHtml(title)}</h4>
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
    let shouldCheckAutoLoad = false;
    if (!append) {
      this.viewTitle.textContent = 'Subscription Feed';
      this.videoGrid.style.display = 'grid';
      this.videoGrid.innerHTML = '';
      this.renderContinueWatchingShelf();
      this.renderUnwatchedToggle();
    }

    this.showLoading(true);
    try {
      const data = await api.getHomeFeed(this.feedLimit, this.feedOffset, this.youtubeUnwatchedOnly);
      this.feedHasMore = data.has_more;

      if (!append && data.items.length === 0) {
        this.showEmpty(true, 'No new unwatched videos! Or you didn\'t subscribe to any channels.', 'Switch to "All Videos", subscribe some channels or sync for new uploads.');
      } else {
        this.showEmpty(false);
        const batch = this.shuffleItems(data.items);
        batch.forEach((video) => {
          this.videoGrid.appendChild(this.createVideoCard(video));
        });
        shouldCheckAutoLoad = batch.length > 0;
      }
    } catch (err) {
      console.error(err);
    } finally {
      this.showLoading(false);
      if (shouldCheckAutoLoad) {
        this.loadMoreIfNeeded();
      }
    }
  },

  shuffleItems(items) {
    const shuffled = items.slice();
    for (let index = shuffled.length - 1; index > 0; index -= 1) {
      const randomIndex = Math.floor(Math.random() * (index + 1));
      [shuffled[index], shuffled[randomIndex]] = [shuffled[randomIndex], shuffled[index]];
    }
    return shuffled;
  },

  async renderContinueWatchingShelf() {
    if (!this.continueWatchingShelf || !this.continueWatchingTrack) return;
    let items = [];
    try {
      const data = await api.getContinueWatching();
      items = data.items || [];
    } catch (err) {
      console.error('Failed to load continue watching:', err);
    }
    if (this.currentRoute !== 'home') return;

    this.continueWatchingTrack.innerHTML = '';
    this.continueWatchingShelf.style.display = items.length > 0 ? 'block' : 'none';
    items.forEach((video) => {
      this.continueWatchingTrack.appendChild(this.createVideoCard(video, 'continue-video-card-'));
    });
    this.syncContinueWatchingCardWidth();
  },

  syncContinueWatchingCardWidth() {
    const feedCard = this.videoGrid?.querySelector('.video-card');
    if (!feedCard || !this.continueWatchingTrack) return;
    const width = feedCard.getBoundingClientRect().width;
    if (width > 0) {
      this.continueWatchingTrack.style.setProperty('--feed-video-card-width', `${width}px`);
    }
  },

  // Shared Unwatched / All Videos toggle for Subscriptions, Channel, Gone soon and Movies screens
  renderUnwatchedToggle(noteHtml = '', container = this.filterChips) {
    container.innerHTML = `
      ${noteHtml}
      <div class="chip ${this.youtubeUnwatchedOnly ? 'active' : ''}" data-unwatched="true">Unwatched</div>
      <div class="chip ${!this.youtubeUnwatchedOnly ? 'active' : ''}" data-unwatched="false">All Videos</div>
    `;

    container.querySelectorAll('.chip[data-unwatched]').forEach((chip) => {
      chip.addEventListener('click', () => {
        const unwatchedOnly = chip.dataset.unwatched === 'true';
        if (unwatchedOnly === this.youtubeUnwatchedOnly) return;
        this.youtubeUnwatchedOnly = unwatchedOnly;
        this.reloadYoutubeList();
      });
    });
  },

  reloadYoutubeList() {
    this.feedOffset = 0;
    if (this.currentRoute === 'home') {
      this.renderHomeFeed();
    } else if (this.currentRoute.startsWith('#channel/')) {
      this.renderChannelFeed();
    } else if (this.currentRoute === '#gone-soon') {
      this.renderGoneSoon();
    } else if (this.currentRoute === 'movies') {
      this.renderMoviesHome();
    }
  },

  // =========================================================
  // 2. Channels List View
  // =========================================================
  async renderChannelsList() {
    this.viewTitle.textContent = 'Channels';
    this.renderChannelSubscriptionChips();
    this.videoGrid.style.display = 'none';
    this.videoGrid.innerHTML = '';
    this.showEmpty(false);
    this.scraperPanel.style.display = '';
    await this.loadChannelsPage();
  },

  async loadChannelsPage() {
    this.showLoading(true);
    this.scraperStatus.textContent = 'Loading channels...';
    try {
      const [scraperChannels, mytubeChannels] = await Promise.all([
        api.getScraperChannels(),
        api.getChannels('all'),
      ]);
      this.scraperChannels = scraperChannels;
      this.mytubeChannelsByName = new Map(
        mytubeChannels.map((ch) => [(ch.name || '').trim().toLowerCase(), ch])
      );
      const configNames = new Set(scraperChannels.map((ch) => (ch.name || '').trim().toLowerCase()));
      this.unconfiguredChannels = [...this.mytubeChannelsByName.entries()]
        .filter(([key]) => !configNames.has(key))
        .map(([, ch]) => ch);
      const count = scraperChannels.length;
      const extra = this.unconfiguredChannels.length;
      let status = `${count} ${count === 1 ? 'channel' : 'channels'} in the scraper config.`;
      if (extra) status += ` ${extra} downloaded ${extra === 1 ? 'channel is' : 'channels are'} not in the config yet.`;
      this.scraperStatus.textContent = `${status} Changes apply on the scraper's next run.`;
    } catch (err) {
      this.scraperChannels = [];
      this.unconfiguredChannels = [];
      this.scraperStatus.textContent = err.message || 'Failed to load channels';
    } finally {
      this.showLoading(false);
    }
    this.renderChannelRows();
  },

  renderChannelRows() {
    const filter = this.channelSubscriptionFilter;
    const configRows = this.scraperChannels.map((channel) => ({
      channel,
      match: this.mytubeChannelsByName.get((channel.name || '').trim().toLowerCase()) || null,
    }));
    const downloadedRows = this.unconfiguredChannels.map((match) => ({
      channel: {
        name: match.name,
        url: /^UC[\w-]{22}$/.test(match.channel_id) ? `https://www.youtube.com/channel/${match.channel_id}` : '',
        unconfigured: true,
      },
      match,
    }));
    const allRows = [...configRows, ...downloadedRows];
    const rows = allRows.filter(({ match }) => {
      const subscribed = Boolean(match && match.subscribed);
      if (filter === 'subscribed') return subscribed;
      if (filter === 'unsubscribed') return !subscribed;
      return true;
    });

    this.scraperList.innerHTML = '';
    if (rows.length === 0) {
      if (allRows.length === 0) {
        this.showEmpty(true, 'No channels yet', 'Add a channel to have the scraper download it.');
      } else {
        const emptyMessages = {
          subscribed: ['No subscribed channels', 'Subscribe to a channel to see its videos in your feed.'],
          unsubscribed: ['No unsubscribed channels', 'You are subscribed to every channel.'],
        };
        const [title, subtitle] = emptyMessages[filter] || ['No channels', ''];
        this.showEmpty(true, title, subtitle);
      }
      return;
    }
    this.showEmpty(false);
    rows.forEach(({ channel, match }) => {
      this.scraperList.appendChild(this.createChannelRow(channel, match));
    });
  },

  renderChannelSubscriptionChips() {
    const options = [['all', 'All'], ['subscribed', 'Subscribed'], ['unsubscribed', 'Unsubscribed']];
    this.filterChips.innerHTML = options.map(([value, label]) => `
      <div class="chip ${this.channelSubscriptionFilter === value ? 'active' : ''}" data-subscription="${value}">${label}</div>
    `).join('');

    this.filterChips.querySelectorAll('.chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        this.channelSubscriptionFilter = chip.dataset.subscription;
        this.renderChannelSubscriptionChips();
        this.renderChannelRows();
      });
    });
  },

  createChannelRow(channel, match) {
    const subscribed = Boolean(match && match.subscribed);
    const row = document.createElement('li');
    row.className = 'scraper-row';

    const identity = document.createElement(match ? 'a' : 'div');
    identity.className = 'scraper-row-identity';
    if (match) identity.href = `#channel/${encodeURIComponent(match.channel_id)}`;

    const avatar = document.createElement('div');
    avatar.className = 'channel-avatar';
    this.populateAvatarElement(avatar, channel.name, match ? match.thumbnail_url : null);

    const text = document.createElement('div');
    text.className = 'scraper-row-text';
    const name = document.createElement('div');
    name.className = 'scraper-row-name';
    name.textContent = channel.name;
    const meta = document.createElement('div');
    meta.className = 'scraper-row-meta';
    meta.textContent = this.channelRowMeta(channel, match);
    text.append(name, meta);
    identity.append(avatar, text);

    const actions = document.createElement('div');
    actions.className = 'scraper-row-actions';

    const bellBtn = document.createElement('button');
    bellBtn.type = 'button';
    bellBtn.className = `scraper-icon-btn scraper-bell${subscribed ? ' active' : ''}`;
    bellBtn.innerHTML = subscribed ? this.icons.bell : this.icons.bellOff;
    bellBtn.disabled = !match;
    bellBtn.title = match ? (subscribed ? 'Unsubscribe' : 'Subscribe') : 'Not downloaded yet';
    bellBtn.setAttribute('aria-label', bellBtn.title);
    bellBtn.addEventListener('click', () => this.toggleChannelSubscription(match, channel.name));

    const editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.className = 'scraper-icon-btn';
    editBtn.innerHTML = this.icons.pencil;
    editBtn.title = 'Edit scraper settings';
    editBtn.setAttribute('aria-label', 'Edit scraper settings');
    editBtn.addEventListener('click', () => this.openScraperForm(channel, { isNew: Boolean(channel.unconfigured) }));

    actions.append(bellBtn, editBtn);
    row.append(identity, actions);
    return row;
  },

  channelRowMeta(channel, match) {
    const parts = [];
    if (match) {
      parts.push(`${match.total_videos} ${match.total_videos === 1 ? 'video' : 'videos'}`);
      parts.push(match.latest_upload_date ? `Last video ${this.formatUploadDate(match.latest_upload_date)}` : 'No uploads yet');
    } else {
      parts.push('Not downloaded yet');
    }
    if (channel.unconfigured) parts.push('Not in scraper config');
    if (channel.enabled === false) parts.push('Disabled');
    return parts.join(' • ');
  },

  async toggleChannelSubscription(match, name) {
    if (!match) return;
    try {
      const result = await api.setChannelSubscription(match.channel_id, !match.subscribed);
      match.subscribed = result.subscribed;
      this.showToast(match.subscribed ? `Subscribed to ${name}` : `Unsubscribed from ${name}`);
    } catch (err) {
      console.error('Failed to update subscription:', err);
      this.showToast('Failed to update subscription');
    }
    this.renderChannelRows();
  },

  // =========================================================
  // Scraper Channels Panel (Channels page): manages youtube_scrapper channels.json
  // =========================================================
  openScraperForm(channel = null, { isNew = false } = {}) {
    const defaults = {
      mode: 'video',
      resolution: 1080,
      audio_format: 'm4a',
      voice_language: '',
      subtitle_language: '',
      min_views: 0,
      title_contains: '',
      min_duration_minutes: 5,
      date_days: 5,
      enabled: true,
    };
    const values = { ...defaults, ...(channel || {}) };
    this.scraperForm.reset();
    for (const [key, value] of Object.entries(values)) {
      const field = this.scraperForm.elements.namedItem(key);
      if (!field) continue;
      if (field.type === 'checkbox') {
        field.checked = Boolean(value);
      } else {
        if (field.tagName === 'SELECT') this.ensureSelectOption(field, String(value));
        field.value = String(value);
      }
    }
    const editing = Boolean(channel) && !isNew;
    this.scraperEditingName = editing ? channel.name : null;
    this.scraperSaveBtn.textContent = editing ? 'Save channel' : 'Add channel';
    this.scraperDeleteBtn.style.display = editing ? '' : 'none';
    this.scraperFormError.textContent = '';
    this.scraperForm.style.display = '';
    this.scraperForm.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    this.scraperForm.elements.namedItem('name').focus();
  },

  // Keeps a channels.json value that is not one of the preset options, so it is not lost on save
  ensureSelectOption(select, value) {
    select.querySelectorAll('option[data-custom]').forEach((option) => option.remove());
    if (![...select.options].some((option) => option.value === value)) {
      const option = new Option(value, value);
      option.dataset.custom = '';
      select.add(option);
    }
  },

  closeScraperForm() {
    this.scraperEditingName = null;
    this.scraperForm.reset();
    this.scraperForm.style.display = 'none';
    this.scraperDeleteBtn.style.display = 'none';
    this.scraperFormError.textContent = '';
  },

  async saveScraperChannel(event) {
    event.preventDefault();
    const field = (key) => this.scraperForm.elements.namedItem(key);
    const channel = {
      name: field('name').value.trim(),
      url: field('url').value.trim(),
      mode: field('mode').value,
      resolution: Number(field('resolution').value),
      audio_format: field('audio_format').value,
      voice_language: field('voice_language').value.trim(),
      subtitle_language: field('subtitle_language').value.trim(),
      min_views: Number(field('min_views').value),
      title_contains: field('title_contains').value.trim(),
      min_duration_minutes: Number(field('min_duration_minutes').value),
      date_days: Number(field('date_days').value),
      enabled: field('enabled').checked,
    };
    const isEdit = this.scraperEditingName !== null;
    this.scraperSaveBtn.disabled = true;
    this.scraperFormError.textContent = '';
    try {
      await api.saveScraperChannel(channel, this.scraperEditingName);
      this.showToast(isEdit ? `Saved ${channel.name}` : `Added ${channel.name}`);
      this.closeScraperForm();
      await this.loadChannelsPage();
    } catch (err) {
      this.scraperFormError.textContent = err.message;
    } finally {
      this.scraperSaveBtn.disabled = false;
    }
  },

  async removeScraperChannel(name) {
    if (!name) return;
    const confirmed = confirm(`Remove ${name} from the scraper config? The scraper stops checking it on its next run. Files already downloaded are not deleted.`);
    if (!confirmed) return;
    try {
      await api.deleteScraperChannel(name);
      if (this.scraperEditingName === name) this.closeScraperForm();
      this.showToast(`Removed ${name}`);
      await this.loadChannelsPage();
    } catch (err) {
      this.showToast(err.message || 'Failed to remove channel');
    }
  },

  formatFileSize(bytes) {
    const size = Number(bytes) || 0;
    if (size <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
    const value = size / Math.pow(1024, index);
    return `${index === 0 ? value : value.toFixed(1)} ${units[index]}`;
  },

  // =========================================================
  // 3. Channel Feed View
  // =========================================================
  async renderChannelFeed(append = false) {
    let shouldCheckAutoLoad = false;
    if (!append) {
      this.videoGrid.style.display = 'grid';
      this.videoGrid.innerHTML = '';
      this.renderUnwatchedToggle();
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
        this.youtubeUnwatchedOnly ? 'unwatched' : 'all',
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
        shouldCheckAutoLoad = data.items.length > 0;
      }
    } catch (err) {
      console.error(err);
    } finally {
      this.showLoading(false);
      if (shouldCheckAutoLoad) {
        this.loadMoreIfNeeded();
      }
    }
  },

  // =========================================================
  // 3b. Gone Soon View (oldest subscribed videos, next to be cleaned up)
  // =========================================================
  async renderGoneSoon(append = false) {
    let shouldCheckAutoLoad = false;
    if (!append) {
      this.viewTitle.textContent = 'Gone soon';
      this.renderUnwatchedToggle('<div class="gone-soon-note">Oldest subscribed videos. They are deleted automatically when storage is full.</div>');
      this.videoGrid.style.display = 'grid';
      this.videoGrid.innerHTML = '';
      this.showEmpty(false);
    }

    this.showLoading(true);
    try {
      const data = await api.getGoneSoon(this.feedLimit, this.feedOffset, this.youtubeUnwatchedOnly);
      this.feedHasMore = data.has_more;

      if (!append && data.items.length === 0) {
        this.showEmpty(true, 'Nothing is waiting to be cleaned up.');
      } else {
        this.showEmpty(false);
        data.items.forEach((video) => {
          this.videoGrid.appendChild(this.createVideoCard(video));
        });
        shouldCheckAutoLoad = data.items.length > 0;
      }
    } catch (err) {
      console.error(err);
    } finally {
      this.showLoading(false);
      if (shouldCheckAutoLoad) {
        this.loadMoreIfNeeded();
      }
    }
  },

  // =========================================================
  // 5. Search Results View
  // =========================================================
  async renderSearchResults() {
    this.viewTitle.textContent = `Search: "${this.searchQuery}"`;
    this.filterChips.innerHTML = '';
    this.videoGrid.style.display = 'grid';
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
    } else if (this.currentRoute === '#gone-soon') {
      this.renderGoneSoon(true);
    }
  },

  loadMoreIfNeeded() {
    const isPaginatedBrowse = this.currentRoute === 'home' || this.currentRoute.startsWith('#channel/') || this.currentRoute === '#gone-soon';
    if (!isPaginatedBrowse || this.isLoading || !this.feedHasMore) return;
    if (!this.videoGrid.querySelector('.video-card')) return;
    if (document.documentElement.scrollHeight <= window.innerHeight) {
      this.loadMore();
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

  createVideoCard(video, idPrefix = 'video-card-') {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.id = `${idPrefix}${video.video_id}`;

    const thumbUrl = video.thumbnail_url || `/thumbnails/videos/${video.video_id}.jpg`;
    const channelThumbUrl = video.channel_thumbnail_url || `/thumbnails/channels/${video.channel_id}.jpg`;
    const durStr = Player.formatTime(video.duration);

    let progressPercent = 0;
    if (video.duration > 0 && video.playback_position > 0 && !video.watched) {
      progressPercent = Math.min(100, (video.playback_position / video.duration) * 100);
    }

    const title = cleanVideoTitle(video.title);
    const uploadTimeAgo = this.formatUploadDate(video.upload_date);

    card.innerHTML = `
      <div class="thumbnail-box">
        <img src="${thumbUrl}" loading="lazy" alt="${this.escapeHtml(title)}">
        <span class="duration-badge">${durStr}</span>
        ${video.watched ? `<span class="watched-badge">WATCHED</span>` : ''}
        ${progressPercent > 0 ? `<div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${progressPercent}%;"></div></div>` : ''}
      </div>
      <div class="video-meta">
        <div class="channel-avatar"></div>
        <div class="video-info">
          <h3 class="video-title">${this.escapeHtml(title)}</h3>
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
    const menuHeight = 48;

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

  showToast(message) {    if (!this.toastEl) return;
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

  // Upload dates are stored as YYYY-MM-DD; returning the string as-is avoids the UTC shift of new Date().
  formatUploadDate(dateStr) {
    if (!dateStr) return '';
    return String(dateStr).slice(0, 10);
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

    this.renderUnwatchedToggle('', document.getElementById('movies-filter-chips'));
    this.showLoading(true);
    try {
      const data = await api.getMoviesHome(this.youtubeUnwatchedOnly ? 'unwatched' : 'all');
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
