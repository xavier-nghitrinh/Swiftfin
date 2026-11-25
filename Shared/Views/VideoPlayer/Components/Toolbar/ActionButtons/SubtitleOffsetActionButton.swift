//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import SwiftUI

extension VideoPlayer.PlaybackControls.Toolbar.ActionButtons {

    struct SubtitleOffset: View {

        @Environment(ViewState.self)
        private var viewState
        @Environment(MediaSession.self)
        private var mediaSession

        private var offset: Duration {
            mediaSession.playbackItem?.subtitleOffset ?? .zero
        }

        private func adjust(by milliseconds: Int64) {
            mediaSession.playbackItem?.subtitleOffset = offset + .milliseconds(milliseconds)
        }

        private func offsetButton(_ label: String, milliseconds: Int64) -> some View {
            Button(label) {
                adjust(by: milliseconds)
            }
        }

        #if os(tvOS)
        @ContentBuilder
        var body: some View {
            Menu(L10n.subtitleOffset, systemImage: VideoPlayerActionButton.subtitleOffset.systemImage) {
                Group {
                    Text(offset, format: .playbackOffset)

                    offsetButton("-5s", milliseconds: -5000)
                    offsetButton("-0.5s", milliseconds: -500)

                    Button(L10n.reset) {
                        mediaSession.playbackItem?.subtitleOffset = .zero
                    }
                    .disabled(offset == .zero)

                    offsetButton("+0.5s", milliseconds: 500)
                    offsetButton("+5s", milliseconds: 5000)
                }
                // Keep the menu open so repeated adjustments don't reopen it.
                .menuActionDismissBehavior(.disabled)

                if mediaSession.playbackItem?.supportsSecondarySubtitles == true {
                    Button {
                        viewState.presentGuestSupplement(PlaybackAdjustmentSupplement.secondarySubtitleOffset)
                    } label: {
                        Text(L10n.secondarySubtitleOffset)

                        Text(mediaSession.playbackItem?.secondarySubtitleOffset ?? .zero, format: .playbackOffset)
                    }
                }
            }
            .menuOrder(.fixed)
        }
        #else
        @ViewContextContains(.isInMenu)
        private var isInMenu

        @ContentBuilder
        private var primaryOffsetButton: some View {
            Button {
                viewState.presentGuestSupplement(PlaybackAdjustmentSupplement.subtitleOffset)
            } label: {
                if isInMenu {
                    Text(L10n.subtitleOffset)

                    Text(offset, format: .playbackOffset)
                } else {
                    Label(
                        L10n.subtitleOffset,
                        systemImage: VideoPlayerActionButton.subtitleOffset.systemImage
                    )
                }
            }
        }

        @ContentBuilder
        var body: some View {
            if mediaSession.playbackItem?.supportsSecondarySubtitles == true {
                Menu(L10n.subtitleOffset, systemImage: VideoPlayerActionButton.subtitleOffset.systemImage) {
                    primaryOffsetButton

                    Button {
                        viewState.presentGuestSupplement(PlaybackAdjustmentSupplement.secondarySubtitleOffset)
                    } label: {
                        Text(L10n.secondarySubtitleOffset)

                        Text(mediaSession.playbackItem?.secondarySubtitleOffset ?? .zero, format: .playbackOffset)
                    }
                }
                .menuOrder(.fixed)
            } else {
                primaryOffsetButton
            }
        }
        #endif
    }
}
