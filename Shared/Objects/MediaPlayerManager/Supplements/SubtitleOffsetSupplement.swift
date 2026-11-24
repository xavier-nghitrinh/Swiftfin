//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

#if os(tvOS)

import SwiftUI

@MainActor
struct SubtitleOffsetSupplement {

    let id = "PlaybackAdjustment-subtitleOffset"
    let displayTitle = L10n.subtitleOffset

    var preferredFocusID: String {
        "\(VideoPlayer.ViewState.Focus.supplementContent(id)).increaseHalfSecond"
    }
}

extension SubtitleOffsetSupplement: VideoPlayerSupplement {

    @ContentBuilder
    var body: some View {
        OffsetView(focusID: preferredFocusID)
    }

    private struct OffsetView: PresentationView {

        @AdaptiveLayout
        private var viewLayout

        @Environment(VideoPlayer.ViewState.self)
        private var viewState

        @Environment(MediaSession.self)
        private var mediaSession

        let focusID: String

        private var offset: Duration {
            mediaSession.playbackItem?.subtitleOffset ?? .zero
        }

        private func adjust(by milliseconds: Int64) {
            mediaSession.playbackItem?.subtitleOffset = offset + .milliseconds(milliseconds)
        }

        private func offsetButton(_ label: String, milliseconds: Int64) -> some View {
            Button {
                adjust(by: milliseconds)
            } label: {
                Text(verbatim: label)
                    .monospacedDigit()
                    .frame(minWidth: viewLayout.isLarge ? 104 : nil, minHeight: viewLayout.isLarge ? 48 : nil)
            }
            .fixedSize()
        }

        @ContentBuilder
        private var content: some View {
            VStack(spacing: viewLayout.isLarge ? 24 : 12) {
                Text(offset, format: .playbackOffset)
                    .font(viewLayout.isLarge ? .title3.weight(.semibold) : .subheadline.weight(.semibold))
                    .monospacedDigit()
                    .padding(.horizontal, viewLayout.isLarge ? 24 : 16)
                    .padding(.vertical, viewLayout.isLarge ? 12 : 8)
                    .backport
                    .glassEffect(.regular.interactive(false), in: .capsule)

                HStack(spacing: viewLayout.isLarge ? 20 : 8) {
                    offsetButton("-5s", milliseconds: -5000)
                    offsetButton("-0.5s", milliseconds: -500)

                    Button {
                        mediaSession.playbackItem?.subtitleOffset = .zero
                    } label: {
                        Text(L10n.reset)
                            .monospacedDigit()
                            .frame(minWidth: viewLayout.isLarge ? 104 : nil, minHeight: viewLayout.isLarge ? 48 : nil)
                    }
                    .fixedSize()
                    .disabled(offset == .zero)

                    offsetButton("+0.5s", milliseconds: 500)
                        .coordinatedFocus(focusID)

                    offsetButton("+5s", milliseconds: 5000)
                }
                .focusSection()
                .buttonStyle(.capsule)
                .padding(.top, viewLayout.isLarge ? 8 : 4)
            }
            .frame(maxWidth: viewLayout.isLarge ? 1200 : 700)
            .frame(maxWidth: .infinity)
            .edgePadding(.horizontal)
            .padding(.vertical, viewLayout.isLarge ? 24 : 12)
            .padding(.leading, viewState.supplementInsets.leading)
            .padding(.trailing, viewState.supplementInsets.trailing)
            .scrollIfLargerThanContainer()
            .padding(.bottom, viewState.supplementInsets.bottom)
        }

        @ContentBuilder
        var standardView: some View {
            content
        }

        @ContentBuilder
        var largeView: some View {
            content
                .focusSection()
        }
    }
}

#endif
