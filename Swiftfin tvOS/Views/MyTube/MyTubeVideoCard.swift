//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

// swiftlint:disable hard_coded_display_string

import FactoryKit
import JellyfinAPI
import SwiftUI

enum MyTubeTileMetrics {

    static let width: CGFloat = 420
    static let aspectRatio: CGFloat = 16.0 / 9.0
    static let cornerRadius: CGFloat = 12
    static let titleHeight: CGFloat = 42
    static let metadataHeight: CGFloat = 18
    static let horizontalSpacing: CGFloat = 30

    static var gridColumns: [GridItem] {
        Array(repeating: GridItem(.fixed(width), spacing: horizontalSpacing), count: 4)
    }
}

struct MyTubeTileButton<Content: View>: View {

    private let action: () -> Void
    private let content: (Bool) -> Content

    @FocusState
    private var isFocused: Bool

    init(action: @escaping () -> Void, @ViewBuilder content: @escaping (Bool) -> Content) {
        self.action = action
        self.content = content
    }

    var body: some View {
        Button(action: action) {
            content(isFocused)
        }
        .buttonStyle(.plain)
        .focused($isFocused)
    }
}

struct MyTubeVideoCard: View {

    @Injected(\.currentUserSession)
    private var userSession

    @PlayMedia
    private var playMedia

    @State
    private var video: MyTubeVideo

    @State
    private var isLoading = false

    var onStatusChanged: (() -> Void)?

    init(video: MyTubeVideo, onStatusChanged: (() -> Void)? = nil) {
        self._video = State(initialValue: video)
        self.onStatusChanged = onStatusChanged
    }

    private func play() {
        guard !isLoading, let userSession else { return }
        isLoading = true

        Task { @MainActor in
            defer { isLoading = false }
            do {
                let entry = try await userSession.getFullItem(id: video.jellyfinItemId)
                var config = MediaPlaybackConfiguration()
                if video.playbackPosition > 0, !video.watched {
                    config.startSeconds = .seconds(video.playbackPosition)
                }

                let snapshot = entry.snapshot
                let ticks = snapshot.runTimeTicks ?? 0
                let fallbackDuration = Double(ticks) / 10_000_000.0
                let duration = video.duration > 0 ? video.duration : fallbackDuration

                let intent = PlaybackIntent(item: snapshot, configuration: config)

                MyTubePlaybackTracker.shared.startTracking(
                    videoId: video.videoId,
                    duration: duration
                )

                playMedia(intent: intent)
            } catch {
                print("MyTubeVideoCard: Failed to load item \(video.jellyfinItemId): \(error)")
            }
        }
    }

    private func toggleWatched() {
        let newStatus = !video.watched
        video.watched = newStatus
        if newStatus {
            video.playbackPosition = video.duration
        } else {
            video.playbackPosition = 0
        }

        Task { @MainActor in
            do {
                if newStatus {
                    try await MyTubeClient.shared.markWatched(videoId: video.videoId)
                } else {
                    try await MyTubeClient.shared.markUnwatched(videoId: video.videoId)
                }
                onStatusChanged?()
            } catch {
                print("Failed to toggle watched status: \(error)")
            }
        }
    }

    private func moveToTrash() {
        Task { @MainActor in
            do {
                try await MyTubeClient.shared.moveToTrash(videoId: video.videoId)
                onStatusChanged?()
            } catch {
                print("Failed to move video to trash: \(error)")
            }
        }
    }

    var body: some View {
        MyTubeTileButton(action: play) { isFocused in
            VStack(alignment: .leading, spacing: 8) {
                MyTubeThumbnailView(video: video, isFocused: isFocused)

                VStack(alignment: .leading, spacing: 8) {
                    Text(video.title)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(.primary)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                        .frame(height: MyTubeTileMetrics.titleHeight, alignment: .topLeading)

                    HStack(spacing: 6) {
                        if let channelName = video.channelName, !channelName.isEmpty {
                            Text(channelName)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }

                        if !video.formattedUploadDate.isEmpty {
                            if let channelName = video.channelName, !channelName.isEmpty {
                                Text("•")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Text(video.formattedUploadDate)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                    .frame(height: MyTubeTileMetrics.metadataHeight, alignment: .topLeading)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .contextMenu {
            Button {
                toggleWatched()
            } label: {
                Label(
                    video.watched ? "Mark as Unwatched" : "Mark as Watched",
                    systemImage: video.watched ? "eye.slash" : "checkmark.circle"
                )
            }

            Button(role: .destructive) {
                moveToTrash()
            } label: {
                Label("Move to Trash", systemImage: "trash")
            }
        }
    }
}
