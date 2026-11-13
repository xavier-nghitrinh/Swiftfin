/**
 * MyTube Player Module
 * Inline YouTube-style video player streaming directly from Jellyfin
 * Features:
 *  - Direct MKV stream + hls.js fMP4 stream (for multi-audio switching) + iPad H.264 HLS
 *  - Multiple audio streams selector with real language names from .info.json
 *  - Custom WebVTT subtitle parser & single clean overlay renderer (no double subtitles)
 *  - Playback speed & Hold-to-speed x1.8 with badge
 *  - Unified touch tap behavior on Android & iPhone (tap to show/hide controls, center button to play/pause)
 *  - Background playback on lockscreen (MediaSession API)
 *  - Auto-mark watched sync (< 30s remaining)
 */

const Player = {
  // Elements
  container: null,
  video: null,
  overlay: null,
  bottomBar: null,
  subtitleOverlay: null,
  titleEl: null,
  seekbar: null,
  seekbarContainer: null,
  timeDisplay: null,
  playBtn: null,
  overlayPlayBtn: null,
  playIcon: null,
  overlayPlayIcon: null,
  qualityBtn: null,
  audioBtn: null,
  subBtn: null,
  speedBtn: null,
  castBtn: null,
  fullscreenBtn: null,
  fullscreenIcon: null,
  qualityMenu: null,
  audioMenu: null,
  subMenu: null,
  speedMenu: null,

  // State
  isActive: false,
  isPseudoFs: false,
  wantPlaying: false,
  currentQuality: 'auto',
  lastHideTime: 0,
  autoResumedOnHide: false,
  hlsInstance: null,
  currentVideo: null,
  playbackData: null,
  selectedAudioIndex: null,
  selectedSubIndex: -1,
  currentSubMeta: null,
  subtitleCues: [],
  basePlaybackRate: 1.0,
  isHoldingSpeed: false,
  justFinishedHold: false,
  isHoveringControls: false,
  lastPointerType: 'mouse',
  wasOverlayVisibleOnDown: true,
  holdTimer: null,
  progressSyncInterval: null,
  overlayHideTimeout: null,
  onWatchedAutoTriggered: null,

  // Double-tap & Tap state
  doubleTapLeft: null,
  doubleTapRight: null,
  doubleTapLeftText: null,
  doubleTapRightText: null,
  lastTapTime: 0,
  lastTapZone: null,
  singleTapTimer: null,
  consecutiveTapCount: 0,
  doubleTapIndicatorTimer: null,

  init() {
    this.container = document.getElementById('player-container');
    this.video = document.getElementById('video-player');
    this.overlay = document.getElementById('player-overlay');
    this.bottomBar = document.getElementById('player-bottom-bar');
    this.doubleTapLeft = document.getElementById('double-tap-left');
    this.doubleTapRight = document.getElementById('double-tap-right');
    this.doubleTapLeftText = document.getElementById('double-tap-left-text');
    this.doubleTapRightText = document.getElementById('double-tap-right-text');
    this.subtitleOverlay = document.getElementById('player-subtitle-overlay');
    this.titleEl = document.getElementById('player-title');
    this.seekbar = document.getElementById('player-seekbar');
    this.seekbarContainer = this.seekbar ? this.seekbar.parentElement : null;
    this.timeDisplay = document.getElementById('player-time-display');
    this.playBtn = document.getElementById('player-play-btn');
    this.overlayPlayBtn = document.getElementById('overlay-play-btn');
    this.playIcon = document.getElementById('play-pause-icon');
    this.overlayPlayIcon = document.getElementById('overlay-play-icon');
    this.qualityBtn = document.getElementById('player-quality-btn');
    this.audioBtn = document.getElementById('player-audio-btn');
    this.subBtn = document.getElementById('player-sub-btn');
    this.speedBtn = document.getElementById('player-speed-btn');
    this.castBtn = document.getElementById('player-cast-btn');
    this.fullscreenBtn = document.getElementById('player-fullscreen-btn');
    this.fullscreenIcon = document.getElementById('fullscreen-icon');
    this.qualityMenu = document.getElementById('quality-menu');
    this.audioMenu = document.getElementById('audio-menu');
    this.subMenu = document.getElementById('sub-menu');
    this.speedMenu = document.getElementById('speed-menu');

    this.bindEvents();
    this.setupExternalPlayback();
  },

  blessFromUserGesture() {
    // Unlock HTMLMediaElement user-gesture restrictions synchronously during tap
    if (!this.video || this.isActive) return;
    try {
      this.video.muted = false;
      this.video.load();
    } catch (e) {}
  },

  isIOSOrSafari() {
    const ua = navigator.userAgent || '';
    const isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const isSafari = /^((?!chrome|android).)*safari/i.test(ua);
    return isIOS || isSafari;
  },

  canPlayAV1() {
    if (!this.video || typeof this.video.canPlayType !== 'function') return false;
    const support = this.video.canPlayType('video/mp4; codecs="av01.0.05M.08"');
    return support === 'probably' || support === 'maybe';
  },

  bindEvents() {
    document.getElementById('player-close-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      if (this.isFullscreen()) {
        this.exitFullscreen();
        return;
      }
      if (window.App) window.App.goBack();
    });

    const togglePlay = (e) => {
      if (e) e.stopPropagation();
      if (this.justFinishedHold) return;
      if (this.video.paused) {
        this.wantPlaying = true;
        this.video.play().catch(console.warn);
      } else {
        this.wantPlaying = false;
        this.video.pause();
      }
    };

    // Bottom bar play/pause button always toggles immediately
    this.playBtn.addEventListener('click', togglePlay);

    // Center big play/pause button: on touch devices, only toggle play if overlay was already visible when finger touched down
    this.overlayPlayBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (this.justFinishedHold) return;
      if (this.lastPointerType === 'touch' && !this.wasOverlayVisibleOnDown) {
        this.showOverlay();
        return;
      }
      togglePlay();
    });

    this.video.addEventListener('play', () => {
      this.wantPlaying = true;
      this.updatePlayState(true);
      this.updateMediaSessionPosition();
    });

    this.video.addEventListener('pause', () => {
      // Prevent unwanted interruption when pressing mobile Sleep/Lock button
      const isVisibilityAutoPause = (
        this.isActive &&
        this.wantPlaying &&
        !this.video.ended &&
        !this.autoResumedOnHide &&
        (document.hidden || (Date.now() - this.lastHideTime < 1500))
      );
      if (isVisibilityAutoPause) {
        this.autoResumedOnHide = true;
        this.video.play().then(() => {
          this.updatePlayState(true);
        }).catch(() => {
          setTimeout(() => {
            if (this.isActive && this.wantPlaying && this.video.paused) {
              this.video.play().catch(() => this.updatePlayState(false));
            }
          }, 80);
        });
        return;
      }
      this.updatePlayState(false);
    });

    this.video.addEventListener('ratechange', () => this.updateMediaSessionPosition());
    this.video.addEventListener('timeupdate', () => this.onTimeUpdate());
    this.video.addEventListener('loadedmetadata', () => this.onLoadedMetadata());
    this.video.addEventListener('ended', () => this.onEnded());
    this.video.addEventListener('error', (e) => this.onError(e));

    // Track screen lock / background transitions so browser auto-pause on <video> can be resumed immediately
    const recordHideState = () => {
      if (this.isActive && !this.video.paused) {
        this.wantPlaying = true;
        this.lastHideTime = Date.now();
        this.autoResumedOnHide = false;
      }
    };
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        recordHideState();
      } else {
        this.autoResumedOnHide = false;
      }
    });
    window.addEventListener('pagehide', recordHideState);

    // Attach native <track> ONLY when entering iOS native fullscreen so PC never shows duplicate subtitles
    this.video.addEventListener('webkitbeginfullscreen', () => {
      if (this.selectedSubIndex >= 0 && this.currentSubMeta) {
        this.attachNativeTrack(this.currentSubMeta);
      }
    });
    this.video.addEventListener('webkitendfullscreen', () => {
      this.removeNativeTracks();
    });

    this.seekbar.addEventListener('input', (e) => {
      e.stopPropagation();
      const dur = this.video.duration || (this.playbackData?.duration || 0);
      const targetTime = (parseFloat(this.seekbar.value) / 100) * dur;
      if (!isNaN(targetTime)) {
        this.video.currentTime = targetTime;
      }
      this.showOverlay();
    });

    this.setupRotatedSeekbar();

    document.addEventListener('fullscreenchange', () => this.updateFullscreenIcon());
    document.addEventListener('webkitfullscreenchange', () => this.updateFullscreenIcon());
    window.addEventListener('resize', () => this.updatePseudoOrientation());
    window.addEventListener('orientationchange', () => {
      setTimeout(() => this.updatePseudoOrientation(), 60);
    });

    document.getElementById('player-rewind-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      this.video.currentTime = Math.max(0, this.video.currentTime - 10);
      this.showOverlay();
    });
    document.getElementById('player-forward-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      const dur = this.video.duration || (this.playbackData?.duration || 0);
      this.video.currentTime = Math.min(dur, this.video.currentTime + 10);
      this.showOverlay();
    });

    this.fullscreenBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleFullscreen();
    });

    document.getElementById('player-center-zone').addEventListener('dblclick', (e) => {
      if (this.lastPointerType === 'mouse' && (e.target === document.getElementById('player-center-zone') || e.target === this.video)) {
        this.toggleFullscreen();
      }
    });

    if (this.qualityBtn) {
      this.qualityBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.toggleDropdown(this.qualityMenu);
      });
    }
    this.audioBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleDropdown(this.audioMenu);
    });
    this.subBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleDropdown(this.subMenu);
    });
    this.speedBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleDropdown(this.speedMenu);
    });

    this.speedMenu.querySelectorAll('.menu-item').forEach((item) => {
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        const speed = parseFloat(item.dataset.speed);
        this.setSpeed(speed);
        this.closeAllDropdowns();
      });
    });

    // Desktop Mouse-only hover detection (ignores simulated touch mousemove on Android!)
    this.container.addEventListener('pointermove', (e) => {
      if (e.pointerType === 'mouse') {
        this.showOverlay();
      }
    });
    this.container.addEventListener('pointerenter', (e) => {
      if (e.pointerType === 'mouse') {
        this.showOverlay();
      }
    });
    this.container.addEventListener('pointerleave', (e) => {
      if (e.pointerType === 'mouse' && !this.video.paused && !this.hasOpenDropdown()) {
        this.hideOverlay();
      }
    });

    this.bottomBar.addEventListener('pointerenter', (e) => {
      if (e.pointerType === 'mouse') {
        this.isHoveringControls = true;
        if (this.overlayHideTimeout) clearTimeout(this.overlayHideTimeout);
      }
    });
    this.bottomBar.addEventListener('pointerleave', (e) => {
      if (e.pointerType === 'mouse') {
        this.isHoveringControls = false;
        this.showOverlay();
      }
    });

    // Unified Tap / Click / Double-Tap on video background
    this.container.addEventListener('click', (e) => {
      if (this.justFinishedHold) return;

      // Ignore clicks on control buttons, sliders, menus
      if (e.target.closest('button, input, .dropdown-menu, .overlay-bottom, .overlay-top')) {
        return;
      }

      const rect = this.container.getBoundingClientRect();
      const relativeX = this.isPseudoLandscape()
        ? (e.clientY - rect.top) / (rect.height || 1)
        : (e.clientX - rect.left) / (rect.width || 1);

      let zone = 'center';
      if (relativeX < 0.38) {
        zone = 'left';
      } else if (relativeX > 0.62) {
        zone = 'right';
      }

      const now = Date.now();
      const timeSinceLastTap = now - this.lastTapTime;
      const maxInterval = (this.consecutiveTapCount > 0) ? 600 : 320;
      const isDoubleTap = (timeSinceLastTap < maxInterval && this.lastTapZone === zone && (zone === 'left' || zone === 'right'));

      if (isDoubleTap) {
        if (this.singleTapTimer) {
          clearTimeout(this.singleTapTimer);
          this.singleTapTimer = null;
        }

        if (this.consecutiveTapCount === 0) {
          this.consecutiveTapCount = 1;
        }
        this.consecutiveTapCount++;

        const step = 10;
        if (zone === 'left') {
          this.video.currentTime = Math.max(0, this.video.currentTime - step);
        } else {
          const dur = this.video.duration || (this.playbackData?.duration || 0);
          this.video.currentTime = Math.min(dur, this.video.currentTime + step);
        }
        this.onTimeUpdate();

        this.showDoubleTapFeedback(zone, (this.consecutiveTapCount - 1) * 10);

        if (this.lastPointerType === 'touch') {
          this.hideOverlay();
        }

        this.lastTapTime = now;
        this.lastTapZone = zone;
        return;
      }

      // Center zone tap: execute immediately without delay
      if (zone === 'center') {
        if (this.singleTapTimer) {
          clearTimeout(this.singleTapTimer);
          this.singleTapTimer = null;
        }
        this.consecutiveTapCount = 0;
        this.lastTapTime = now;
        this.lastTapZone = 'center';

        if (this.lastPointerType === 'touch') {
          if (!this.wasOverlayVisibleOnDown) {
            this.showOverlay();
          } else {
            this.hideOverlay();
          }
        } else {
          togglePlay();
        }
        return;
      }

      // First tap in left or right zone: wait briefly for potential second tap
      if (this.singleTapTimer) {
        clearTimeout(this.singleTapTimer);
        this.singleTapTimer = null;
      }
      this.consecutiveTapCount = 0;
      this.lastTapTime = now;
      this.lastTapZone = zone;

      const wasVisible = this.wasOverlayVisibleOnDown;
      const pointerType = this.lastPointerType;

      this.singleTapTimer = setTimeout(() => {
        this.singleTapTimer = null;
        this.consecutiveTapCount = 0;

        if (pointerType === 'touch') {
          if (!wasVisible) {
            this.showOverlay();
          } else {
            this.hideOverlay();
          }
        } else {
          togglePlay();
        }
      }, 260);
    });

    this.setupHoldToSpeed();

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.dropdown-menu') && !e.target.closest('.btn-icon')) {
        this.closeAllDropdowns();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (!this.isActive) return;
      if (document.activeElement && ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

      if (e.key === ' ' || e.key === 'k') {
        e.preventDefault();
        togglePlay();
      } else if (e.key === 'ArrowLeft' || e.key === 'j') {
        e.preventDefault();
        this.video.currentTime = Math.max(0, this.video.currentTime - 10);
        this.showOverlay();
      } else if (e.key === 'ArrowRight' || e.key === 'l') {
        e.preventDefault();
        const dur = this.video.duration || (this.playbackData?.duration || 0);
        this.video.currentTime = Math.min(dur, this.video.currentTime + 10);
        this.showOverlay();
      } else if (e.key === 'f') {
        e.preventDefault();
        this.toggleFullscreen();
      } else if (e.key === 'Escape' && this.isPseudoFs) {
        e.preventDefault();
        this.exitPseudoFullscreen();
      }
    });
  },

  setupRotatedSeekbar() {
    if (!this.seekbarContainer || !this.seekbar) return;
    let scrubbing = false;

    const scrubAt = (clientY) => {
      const rect = this.seekbar.getBoundingClientRect();
      if (!rect.height) return;
      const ratio = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
      this.seekbar.value = (ratio * 100).toFixed(2);
      const dur = this.video.duration || (this.playbackData?.duration || 0);
      if (dur > 0) {
        this.video.currentTime = ratio * dur;
      }
      this.showOverlay();
    };

    this.seekbarContainer.addEventListener('pointerdown', (e) => {
      if (!this.isPseudoLandscape()) return;
      e.stopPropagation();
      scrubbing = true;
      if (e.pointerId !== undefined && this.seekbarContainer.setPointerCapture) {
        try { this.seekbarContainer.setPointerCapture(e.pointerId); } catch (err) {}
      }
      scrubAt(e.clientY);
    });

    this.seekbarContainer.addEventListener('pointermove', (e) => {
      if (!scrubbing || !this.isPseudoLandscape()) return;
      e.stopPropagation();
      scrubAt(e.clientY);
    });

    const stopScrub = (e) => {
      if (!scrubbing) return;
      scrubbing = false;
      if (e && e.pointerId !== undefined && this.seekbarContainer.releasePointerCapture) {
        try { this.seekbarContainer.releasePointerCapture(e.pointerId); } catch (err) {}
      }
    };
    this.seekbarContainer.addEventListener('pointerup', stopScrub);
    this.seekbarContainer.addEventListener('pointercancel', stopScrub);
  },

  setupExternalPlayback() {
    if (!this.castBtn || !this.video) return;

    // 1. Apple AirPlay / Wired External Display Target Picker
    if (window.WebKitPlaybackTargetAvailabilityEvent || typeof this.video.webkitShowPlaybackTargetPicker === 'function') {
      this.video.addEventListener('webkitplaybacktargetavailabilitychanged', (e) => {
        this.castBtn.style.display = (e.availability === 'available') ? 'flex' : 'none';
      });
    }

    // 2. W3C Remote Playback API (Chrome / Android Cast & External Receivers)
    if (this.video.remote && typeof this.video.remote.watchAvailability === 'function') {
      this.video.remote.watchAvailability((available) => {
        this.castBtn.style.display = available ? 'flex' : 'none';
      }).catch(() => {});
    }

    this.castBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (typeof this.video.webkitShowPlaybackTargetPicker === 'function') {
        this.video.webkitShowPlaybackTargetPicker();
      } else if (this.video.remote && typeof this.video.remote.prompt === 'function') {
        this.video.remote.prompt().catch(console.warn);
      }
    });
  },

  showDoubleTapFeedback(zone, totalSeconds) {
    const el = zone === 'left' ? this.doubleTapLeft : this.doubleTapRight;
    const textEl = zone === 'left' ? this.doubleTapLeftText : this.doubleTapRightText;
    const otherEl = zone === 'left' ? this.doubleTapRight : this.doubleTapLeft;

    if (otherEl) {
      otherEl.classList.remove('active');
      otherEl.style.display = 'none';
    }

    if (textEl) {
      textEl.textContent = `${totalSeconds} seconds`;
    }

    if (el) {
      el.style.display = 'flex';
      el.classList.remove('active');
      void el.offsetWidth; // Force reflow to re-trigger animation
      el.classList.add('active');
    }

    if (this.doubleTapIndicatorTimer) {
      clearTimeout(this.doubleTapIndicatorTimer);
    }
    this.doubleTapIndicatorTimer = setTimeout(() => {
      if (el) {
        el.classList.remove('active');
        el.style.display = 'none';
      }
      this.consecutiveTapCount = 0;
    }, 650);
  },

  setupHoldToSpeed() {
    let isPointerDown = false;
    let startX = 0;
    let startY = 0;

    // Completely block native context menus on player to prevent Android's
    // video menu popup ("stream.mkv", "download video", "copy frame") from interrupting hold speed
    const blockContextMenu = (e) => {
      e.preventDefault();
      e.stopPropagation();
      return false;
    };

    this.container.addEventListener('contextmenu', blockContextMenu, { capture: true });
    this.video.addEventListener('contextmenu', blockContextMenu, { capture: true });
    window.addEventListener('contextmenu', (e) => {
      if (this.container && (this.container === e.target || this.container.contains(e.target))) {
        blockContextMenu(e);
      }
    }, { capture: true });

    const startHold = (e) => {
      if (e.button && e.button !== 0) return; // Ignore right-click
      this.lastPointerType = e.pointerType || 'mouse';
      this.wasOverlayVisibleOnDown = this.overlay.classList.contains('show');

      if (
        e.target.closest('.overlay-bottom') ||
        e.target.closest('.overlay-top') ||
        e.target.closest('.dropdown-menu') ||
        (e.target.closest('#overlay-play-btn') && this.wasOverlayVisibleOnDown)
      ) {
        return;
      }

      isPointerDown = true;
      this.justFinishedHold = false;
      startX = e.clientX || 0;
      startY = e.clientY || 0;

      // Capture pointer so Android doesn't hijack touch for gestures/context menu
      if (e.pointerId !== undefined && this.container.setPointerCapture) {
        try {
          this.container.setPointerCapture(e.pointerId);
        } catch (err) {}
      }

      if (this.holdTimer) clearTimeout(this.holdTimer);
      this.holdTimer = setTimeout(() => {
        if (isPointerDown && !this.video.paused) {
          // Cancel any pending single-tap action
          if (this.singleTapTimer) {
            clearTimeout(this.singleTapTimer);
            this.singleTapTimer = null;
          }
          this.isHoldingSpeed = true;
          this.video.playbackRate = 1.8;
          if (navigator.vibrate) {
            try { navigator.vibrate(25); } catch (vErr) {}
          }
        }
      }, 240);
    };

    const endHold = (e) => {
      isPointerDown = false;
      if (this.holdTimer) {
        clearTimeout(this.holdTimer);
        this.holdTimer = null;
      }
      if (e && e.pointerId !== undefined && this.container.releasePointerCapture) {
        try {
          this.container.releasePointerCapture(e.pointerId);
        } catch (err) {}
      }
      if (this.isHoldingSpeed) {
        this.isHoldingSpeed = false;
        this.justFinishedHold = true;
        this.video.playbackRate = this.basePlaybackRate;
        setTimeout(() => {
          this.justFinishedHold = false;
        }, 120);
      }
    };

    const onPointerMove = (e) => {
      if (!isPointerDown) return;
      if (!this.isHoldingSpeed) {
        const dx = Math.abs((e.clientX || 0) - startX);
        const dy = Math.abs((e.clientY || 0) - startY);
        if (dx > 12 || dy > 12) {
          if (this.holdTimer) {
            clearTimeout(this.holdTimer);
            this.holdTimer = null;
          }
        }
      }
    };

    this.container.addEventListener('pointerdown', startHold);
    this.container.addEventListener('pointerup', endHold);
    this.container.addEventListener('pointercancel', endHold);
    this.container.addEventListener('pointermove', onPointerMove);
    this.container.addEventListener('pointerleave', (e) => {
      if (e.pointerType === 'mouse') {
        endHold(e);
      }
    });
  },

  destroyHls() {
    if (this.hlsInstance) {
      try {
        this.hlsInstance.destroy();
      } catch (e) {
        console.warn(e);
      }
      this.hlsInstance = null;
    }
  },

  loadStreamSource(data, resumeTime = 0, autoPlay = true) {
    this.destroyHls();
    const isApple = this.isIOSOrSafari();
    const supportsAV1 = this.canPlayAV1();

    // Case 1: iPhone / iPad / Safari
    if (isApple) {
      // Newer iPhones with hardware AV1 use zero-CPU fMP4 stream copy (hls_url);
      // iPads / older iPhones without AV1 use H.264 transcoded HLS (hls_ios_url)
      const appleStreamUrl = data.use_hls ? data.hls_url : (supportsAV1 ? data.hls_url : data.hls_ios_url);
      this.video.src = appleStreamUrl;
      const onLoaded = () => {
        this.video.removeEventListener('loadedmetadata', onLoaded);
        if (resumeTime > 0) {
          try { this.video.currentTime = resumeTime; } catch (e) {}
        }
        this.video.playbackRate = this.basePlaybackRate;
        if (autoPlay) this.video.play().catch(console.warn);
      };
      this.video.addEventListener('loadedmetadata', onLoaded);
      this.video.load();
      return;
    }

    // Case 2: HLS transcode or audio track or quality preset selected on PC/Android -> Use hls.js with fMP4 HLS stream
    if (data.use_hls && data.hls_url && window.Hls && window.Hls.isSupported()) {
      const hls = new window.Hls({
        enableWorker: true,
        startPosition: resumeTime > 0 ? resumeTime : -1
      });
      this.hlsInstance = hls;
      hls.loadSource(data.hls_url);
      hls.attachMedia(this.video);
      hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
        if (resumeTime > 0) {
          try { this.video.currentTime = resumeTime; } catch (e) {}
        }
        this.video.playbackRate = this.basePlaybackRate;
        if (autoPlay) this.video.play().catch(console.warn);
      });
      hls.on(window.Hls.Events.ERROR, (event, errData) => {
        if (errData.fatal) {
          switch (errData.type) {
            case window.Hls.ErrorTypes.NETWORK_ERROR:
              console.warn('HLS fatal network error, attempting recovery...');
              hls.startLoad();
              break;
            case window.Hls.ErrorTypes.MEDIA_ERROR:
              console.warn('HLS fatal media error, attempting recovery...');
              hls.recoverMediaError();
              break;
            default:
              console.warn('HLS unrecoverable error:', errData);
              this.destroyHls();
              break;
          }
        }
      });
      return;
    }

    // Case 3: Default audio track on PC/Android -> Direct static MKV stream
    this.video.src = data.stream_url;
    const onLoaded = () => {
      this.video.removeEventListener('loadedmetadata', onLoaded);
      if (resumeTime > 0) {
        try { this.video.currentTime = resumeTime; } catch (e) {}
      }
      this.video.playbackRate = this.basePlaybackRate;
      if (autoPlay) this.video.play().catch(console.warn);
    };
    this.video.addEventListener('loadedmetadata', onLoaded);
  },

  startPlayback(playbackData, onWatchedAuto = null) {
    this.stop(true);
    this.isActive = true;
    this.wantPlaying = true;
    this.autoResumedOnHide = false;
    this.onWatchedAutoTriggered = onWatchedAuto;
    this.playbackData = playbackData;
    this.currentVideo = playbackData;
    this.currentQuality = playbackData.current_quality || 'auto';
    this.titleEl.textContent = playbackData.title;
    this.showOverlay();

    this.buildQualityMenu(playbackData.qualities, this.currentQuality);
    this.buildAudioMenu(playbackData.audio_tracks, playbackData.selected_audio_index);
    this.buildSubMenu(playbackData.subtitles);

    const resumePos = (playbackData.playback_position && playbackData.playback_position > 5 && !playbackData.watched)
      ? playbackData.playback_position
      : 0;

    this.loadStreamSource(playbackData, resumePos, true);
    this.setupMediaSession();
    this.startProgressSync();
  },

  onError(e) {
    if (!this.isActive || !this.playbackData) return;
    console.warn('Video element error, checking H.264 HLS fallback:', e);
    const savedTime = this.video.currentTime || 0;
    if (this.isIOSOrSafari() && this.playbackData.hls_ios_url && this.video.src !== this.playbackData.hls_ios_url) {
      this.video.src = this.playbackData.hls_ios_url;
      this.video.load();
      this.video.play().catch(console.warn);
      return;
    }
    if (!this.isIOSOrSafari() && this.playbackData.hls_url && !this.hlsInstance && window.Hls && window.Hls.isSupported()) {
      this.playbackData.use_hls = true;
      this.loadStreamSource(this.playbackData, savedTime, true);
    }
  },

  setupMediaSession() {
    if (!('mediaSession' in navigator) || !this.currentVideo) return;
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: this.currentVideo.title,
        artist: this.currentVideo.channel_name,
        album: 'MyTube',
        artwork: [
          { src: this.currentVideo.thumbnail_url || '/icons/icon-512.png', sizes: '512x512', type: 'image/jpeg' }
        ]
      });

      navigator.mediaSession.setActionHandler('play', () => {
        this.wantPlaying = true;
        this.video.play().catch(console.warn);
      });
      navigator.mediaSession.setActionHandler('pause', () => {
        this.wantPlaying = false;
        this.video.pause();
      });
      navigator.mediaSession.setActionHandler('seekbackward', (details) => {
        this.video.currentTime = Math.max(0, this.video.currentTime - (details.seekOffset || 10));
        this.updateMediaSessionPosition();
      });
      navigator.mediaSession.setActionHandler('seekforward', (details) => {
        const dur = this.video.duration || (this.playbackData?.duration || 0);
        this.video.currentTime = Math.min(dur, this.video.currentTime + (details.seekOffset || 10));
        this.updateMediaSessionPosition();
      });
      navigator.mediaSession.setActionHandler('seekto', (details) => {
        if (details.seekTime !== undefined) {
          this.video.currentTime = details.seekTime;
          this.updateMediaSessionPosition();
        }
      });
    } catch (e) {
      console.warn('MediaSession setup failed:', e);
    }
  },

  updateMediaSessionPosition() {
    if (!('mediaSession' in navigator) || typeof navigator.mediaSession.setPositionState !== 'function') return;
    const dur = this.video.duration || (this.playbackData?.duration || 0);
    const cur = this.video.currentTime || 0;
    if (!dur || !isFinite(dur) || dur <= 0) return;
    try {
      navigator.mediaSession.setPositionState({
        duration: dur,
        playbackRate: this.video.playbackRate || 1.0,
        position: Math.max(0, Math.min(cur, dur))
      });
    } catch (e) {}
  },

  buildQualityMenu(qualities, currentQuality) {
    if (!this.qualityMenu) return;
    this.qualityMenu.innerHTML = '';
    this.currentQuality = currentQuality || 'auto';
    if (!qualities || qualities.length === 0) {
      if (this.qualityBtn) this.qualityBtn.style.display = 'none';
      return;
    }
    if (this.qualityBtn) this.qualityBtn.style.display = 'flex';

    qualities.forEach((q) => {
      const item = document.createElement('div');
      item.className = `menu-item ${q.id === this.currentQuality ? 'selected' : ''}`;
      item.textContent = q.label;
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        this.switchQuality(q.id);
        this.closeAllDropdowns();
      });
      this.qualityMenu.appendChild(item);
    });
  },

  async switchQuality(qualityKey) {
    if (qualityKey === this.currentQuality) return;
    this.currentQuality = qualityKey;
    const currentPos = this.video.currentTime || 0;
    const wasPlaying = !this.video.paused;

    if (window.App) window.App.showToast(`Switching quality to ${qualityKey.toUpperCase()}...`);
    const data = await api.getPlayback(this.currentVideo.video_id, this.selectedAudioIndex, qualityKey);
    if (data) {
      this.playbackData = data;
      this.currentQuality = data.current_quality || qualityKey;
      this.loadStreamSource(data, currentPos, wasPlaying);

      if (this.qualityMenu) {
        this.qualityMenu.querySelectorAll('.menu-item').forEach((item, idx) => {
          const q = data.qualities ? data.qualities[idx] : null;
          item.classList.toggle('selected', q && q.id === this.currentQuality);
        });
      }
    }
  },

  buildAudioMenu(audioTracks, selectedIndex) {
    this.audioMenu.innerHTML = '';
    if (!audioTracks || audioTracks.length === 0) {
      this.audioBtn.style.display = 'none';
      return;
    }
    this.audioBtn.style.display = 'flex';
    this.selectedAudioIndex = selectedIndex ?? audioTracks[0].index;

    audioTracks.forEach((track) => {
      const item = document.createElement('div');
      item.className = `menu-item ${track.index === this.selectedAudioIndex ? 'selected' : ''}`;
      item.textContent = track.title || `${track.language.toUpperCase()} (${track.codec})`;
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        this.switchAudioTrack(track.index);
        this.closeAllDropdowns();
      });
      this.audioMenu.appendChild(item);
    });
  },

  async switchAudioTrack(trackIndex) {
    if (trackIndex === this.selectedAudioIndex) return;
    this.selectedAudioIndex = trackIndex;
    const currentPos = this.video.currentTime || 0;
    const wasPlaying = !this.video.paused;

    if (window.App) window.App.showToast('Switching audio track...');
    const data = await api.getPlayback(this.currentVideo.video_id, trackIndex, this.currentQuality);
    if (data) {
      this.playbackData = data;
      this.loadStreamSource(data, currentPos, wasPlaying);

      this.audioMenu.querySelectorAll('.menu-item').forEach((item, idx) => {
        item.classList.toggle('selected', data.audio_tracks[idx]?.index === trackIndex);
      });
    }
  },

  buildSubMenu(subtitles) {
    this.subMenu.innerHTML = '';
    this.clearSubtitles();

    const offItem = document.createElement('div');
    offItem.className = 'menu-item selected';
    offItem.textContent = 'Subtitles: Off';
    offItem.addEventListener('click', (e) => {
      e.stopPropagation();
      this.switchSubtitle(-1);
      this.closeAllDropdowns();
    });
    this.subMenu.appendChild(offItem);

    if (!subtitles || subtitles.length === 0) return;

    subtitles.forEach((sub) => {
      const item = document.createElement('div');
      item.className = 'menu-item';
      item.textContent = sub.title || sub.language.toUpperCase();
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        this.switchSubtitle(sub.index, sub.url, sub.language, sub.title);
        this.closeAllDropdowns();
      });
      this.subMenu.appendChild(item);
    });
  },

  removeNativeTracks() {
    this.video.querySelectorAll('track').forEach((t) => t.remove());
  },

  attachNativeTrack(meta) {
    this.removeNativeTracks();
    const track = document.createElement('track');
    track.kind = 'subtitles';
    track.label = meta.label;
    track.srclang = meta.lang;
    track.src = meta.url;
    track.default = true;
    this.video.appendChild(track);
  },

  clearSubtitles() {
    this.selectedSubIndex = -1;
    this.currentSubMeta = null;
    this.subtitleCues = [];
    if (this.subtitleOverlay) {
      this.subtitleOverlay.style.display = 'none';
      this.subtitleOverlay.innerHTML = '';
    }
    this.removeNativeTracks();
  },

  async switchSubtitle(index, url = null, lang = 'en', label = 'Subtitle') {
    this.clearSubtitles();
    this.selectedSubIndex = index;

    const items = this.subMenu.querySelectorAll('.menu-item');
    items.forEach((item, i) => {
      if (index === -1) {
        item.classList.toggle('selected', i === 0);
      } else {
        const sub = this.playbackData?.subtitles[i - 1];
        item.classList.toggle('selected', sub && sub.index === index);
      }
    });

    if (index < 0 || !url) return;

    this.currentSubMeta = { index, url, lang, label };

    try {
      const res = await fetch(url);
      if (res.ok) {
        const vttText = await res.text();
        this.subtitleCues = this.parseWebVTT(vttText);
        this.renderActiveSubtitleCue();
      }
    } catch (e) {
      console.warn('Failed to fetch subtitle VTT:', e);
    }
  },

  parseWebVTT(vttText) {
    const cues = [];
    const blocks = vttText.replace(/\r\n/g, '\n').split('\n\n');
    for (const block of blocks) {
      const lines = block.trim().split('\n');
      let timeLineIdx = -1;
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes('-->')) {
          timeLineIdx = i;
          break;
        }
      }
      if (timeLineIdx === -1) continue;

      const timeParts = lines[timeLineIdx].split('-->');
      const start = this.parseVttTimestamp(timeParts[0].trim());
      const end = this.parseVttTimestamp(timeParts[1].trim().split(/\s+/)[0]);
      if (isNaN(start) || isNaN(end) || end <= start) continue;

      const rawText = lines
        .slice(timeLineIdx + 1)
        .join('\n')
        .replace(/<[^>]+>/g, '')
        .replace(/&nbsp;/g, ' ')
        .trim();

      if (!rawText) continue;
      if (end - start < 0.05) continue;

      cues.push({ start, end, text: rawText });
    }
    return cues;
  },

  parseVttTimestamp(ts) {
    const parts = ts.split(':');
    if (parts.length === 3) {
      return parseFloat(parts[0]) * 3600 + parseFloat(parts[1]) * 60 + parseFloat(parts[2].replace(',', '.'));
    } else if (parts.length === 2) {
      return parseFloat(parts[0]) * 60 + parseFloat(parts[1].replace(',', '.'));
    }
    return NaN;
  },

  renderActiveSubtitleCue() {
    if (!this.subtitleOverlay || this.selectedSubIndex < 0 || this.subtitleCues.length === 0) {
      if (this.subtitleOverlay) this.subtitleOverlay.style.display = 'none';
      return;
    }

    const now = this.video.currentTime || 0;
    let activeText = '';
    for (let i = 0; i < this.subtitleCues.length; i++) {
      const c = this.subtitleCues[i];
      if (now >= c.start && now <= c.end) {
        activeText = c.text;
      } else if (c.start > now) {
        break;
      }
    }

    if (activeText) {
      this.subtitleOverlay.style.display = 'block';
      this.subtitleOverlay.innerHTML = `<span>${this.escapeHtml(activeText)}</span>`;
    } else {
      this.subtitleOverlay.style.display = 'none';
    }
  },

  escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  },

  setSpeed(rate) {
    this.basePlaybackRate = rate;
    this.video.playbackRate = rate;
    this.speedMenu.querySelectorAll('.menu-item').forEach((item) => {
      item.classList.toggle('selected', parseFloat(item.dataset.speed) === rate);
    });
  },

  isFullscreen() {
    return Boolean(document.fullscreenElement || document.webkitFullscreenElement || this.isPseudoFs);
  },

  isPseudoLandscape() {
    return Boolean(this.isPseudoFs && this.container && this.container.classList.contains('pseudo-landscape'));
  },

  isVideoLandscape() {
    const vw = this.video?.videoWidth || 16;
    const vh = this.video?.videoHeight || 9;
    return vw >= vh;
  },

  updatePseudoOrientation() {
    if (!this.container) return;
    if (!this.isPseudoFs) {
      this.container.classList.remove('pseudo-landscape');
      return;
    }
    const isViewportPortrait = window.innerHeight > window.innerWidth;
    if (isViewportPortrait && this.isVideoLandscape()) {
      this.container.classList.add('pseudo-landscape');
    } else {
      this.container.classList.remove('pseudo-landscape');
    }
  },

  updateFullscreenIcon() {
    if (!this.fullscreenIcon) return;
    const expandSvg = '<path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>';
    const compressSvg = '<path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/>';
    this.fullscreenIcon.innerHTML = this.isFullscreen() ? compressSvg : expandSvg;
  },

  enterPseudoFullscreen() {
    this.isPseudoFs = true;
    this.container.classList.add('pseudo-fullscreen');
    document.body.classList.add('player-pseudo-fs');
    this.updatePseudoOrientation();
    this.updateFullscreenIcon();
    this.showOverlay();
  },

  exitPseudoFullscreen() {
    this.isPseudoFs = false;
    if (this.container) {
      this.container.classList.remove('pseudo-fullscreen', 'pseudo-landscape');
    }
    document.body.classList.remove('player-pseudo-fs');
    this.updateFullscreenIcon();
  },

  exitFullscreen() {
    if (this.isPseudoFs) {
      this.exitPseudoFullscreen();
      return;
    }
    if (screen.orientation && typeof screen.orientation.unlock === 'function') {
      try { screen.orientation.unlock(); } catch (e) {}
    }
    if (document.exitFullscreen && document.fullscreenElement) {
      document.exitFullscreen().catch(console.warn);
    } else if (document.webkitExitFullscreen && document.webkitFullscreenElement) {
      document.webkitExitFullscreen();
    }
  },

  toggleFullscreen() {
    if (this.isFullscreen()) {
      this.exitFullscreen();
      return;
    }

    // Use standard Element Fullscreen on PC, Android, and iPad;
    // on iPhone (where <div> requestFullscreen is unsupported), use custom pseudo-fullscreen
    // instead of video.webkitEnterFullscreen() so all custom controls & gestures work!
    const reqFs = this.container.requestFullscreen || this.container.webkitRequestFullscreen;
    if (reqFs) {
      try {
        const res = reqFs.call(this.container);
        if (res && typeof res.then === 'function') {
          res.then(() => {
            if (this.isVideoLandscape() && screen.orientation && typeof screen.orientation.lock === 'function') {
              screen.orientation.lock('landscape').catch(() => {});
            }
            this.updateFullscreenIcon();
          }).catch(() => {
            this.enterPseudoFullscreen();
          });
        } else {
          this.updateFullscreenIcon();
        }
      } catch (e) {
        this.enterPseudoFullscreen();
      }
    } else {
      this.enterPseudoFullscreen();
    }
  },

  hasOpenDropdown() {
    return (
      (this.qualityMenu && this.qualityMenu.classList.contains('active')) ||
      this.audioMenu.classList.contains('active') ||
      this.subMenu.classList.contains('active') ||
      this.speedMenu.classList.contains('active')
    );
  },

  toggleDropdown(menu) {
    if (!menu) return;
    const isShowing = menu.classList.contains('active');
    this.closeAllDropdowns();
    if (!isShowing) {
      menu.classList.add('active');
      if (this.overlayHideTimeout) clearTimeout(this.overlayHideTimeout);
    }
  },

  closeAllDropdowns() {
    if (this.qualityMenu) this.qualityMenu.classList.remove('active');
    this.audioMenu.classList.remove('active');
    this.subMenu.classList.remove('active');
    this.speedMenu.classList.remove('active');
  },

  showOverlay() {
    this.overlay.classList.add('show');
    this.container.classList.remove('hide-cursor');
    if (this.overlayHideTimeout) clearTimeout(this.overlayHideTimeout);
    if (!this.video.paused && !this.isHoveringControls && !this.hasOpenDropdown()) {
      this.overlayHideTimeout = setTimeout(() => {
        if (!this.video.paused && !this.isHoveringControls && !this.hasOpenDropdown()) {
          this.hideOverlay();
        }
      }, 3000);
    }
  },

  hideOverlay() {
    this.closeAllDropdowns();
    this.overlay.classList.remove('show');
    if (!this.video.paused) {
      this.container.classList.add('hide-cursor');
    }
  },

  updatePlayState(isPlaying) {
    const playSvg = '<path d="M8 5v14l11-7z"/>';
    const pauseSvg = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
    this.playIcon.innerHTML = isPlaying ? pauseSvg : playSvg;
    this.overlayPlayIcon.innerHTML = isPlaying ? pauseSvg : playSvg;

    if ('mediaSession' in navigator) {
      try {
        navigator.mediaSession.playbackState = isPlaying ? 'playing' : 'paused';
      } catch (e) {}
    }

    if (isPlaying) {
      this.showOverlay();
    } else {
      this.overlay.classList.add('show');
      this.container.classList.remove('hide-cursor');
      if (this.overlayHideTimeout) clearTimeout(this.overlayHideTimeout);
    }
  },

  onTimeUpdate() {
    const cur = this.video.currentTime || 0;
    const dur = this.video.duration || (this.playbackData?.duration || 0);
    if (dur > 0) {
      this.seekbar.value = (cur / dur) * 100;
    }
    this.timeDisplay.textContent = `${this.formatTime(cur)} / ${this.formatTime(dur)}`;
    this.renderActiveSubtitleCue();
  },

  onLoadedMetadata() {
    this.onTimeUpdate();
    this.updatePseudoOrientation();
    this.updateMediaSessionPosition();
  },

  async onEnded() {
    this.wantPlaying = false;
    if (this.currentVideo) {
      const dur = this.video.duration || this.currentVideo.duration || 0;
      const res = await api.reportProgress(this.currentVideo.video_id, dur, dur);
      if (res && res.watched && this.onWatchedAutoTriggered) {
        this.onWatchedAutoTriggered();
      }
    }
  },

  startProgressSync() {
    this.stopProgressSync();
    this.progressSyncInterval = setInterval(async () => {
      const dur = this.video.duration || (this.currentVideo?.duration || 0);
      if (this.currentVideo && !this.video.paused && dur > 0) {
        this.updateMediaSessionPosition();
        const res = await api.reportProgress(
          this.currentVideo.video_id,
          this.video.currentTime,
          dur
        );
        if (res && res.watched && !this.currentVideo.watched) {
          this.currentVideo.watched = true;
          if (this.onWatchedAutoTriggered) {
            this.onWatchedAutoTriggered();
          }
        }
      }
    }, 3000);
  },

  stopProgressSync() {
    if (this.progressSyncInterval) {
      clearInterval(this.progressSyncInterval);
      this.progressSyncInterval = null;
    }
  },

  formatTime(seconds) {
    if (isNaN(seconds) || seconds < 0) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const hours = Math.floor(mins / 60);
    if (hours > 0) {
      const remMins = mins % 60;
      return `${hours}:${remMins < 10 ? '0' : ''}${remMins}:${secs < 10 ? '0' : ''}${secs}`;
    }
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  },

  stop(keepFullscreen = false) {
    this.stopProgressSync();
    this.wantPlaying = false;
    this.autoResumedOnHide = false;
    if (!keepFullscreen && this.isPseudoFs) {
      this.exitPseudoFullscreen();
    }
    if (this.singleTapTimer) {
      clearTimeout(this.singleTapTimer);
      this.singleTapTimer = null;
    }
    if (this.doubleTapIndicatorTimer) {
      clearTimeout(this.doubleTapIndicatorTimer);
      this.doubleTapIndicatorTimer = null;
    }
    if (this.doubleTapLeft) {
      this.doubleTapLeft.classList.remove('active');
      this.doubleTapLeft.style.display = 'none';
    }
    if (this.doubleTapRight) {
      this.doubleTapRight.classList.remove('active');
      this.doubleTapRight.style.display = 'none';
    }
    this.consecutiveTapCount = 0;

    const dur = this.video?.duration || (this.currentVideo?.duration || 0);
    if (this.isActive && this.currentVideo && dur > 0 && this.video.currentTime > 0) {
      api.reportProgress(
        this.currentVideo.video_id,
        this.video.currentTime,
        dur
      );
    }
    if (this.isActive) {
      fetch('/api/videos/stop-encodings', { method: 'POST', keepalive: true }).catch(() => {});
    }
    this.isActive = false;
    this.destroyHls();
    this.clearSubtitles();
    this.video.pause();
    this.video.removeAttribute('src');
    this.video.load();
    this.closeAllDropdowns();
  }
};

window.Player = Player;
