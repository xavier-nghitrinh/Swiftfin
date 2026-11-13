//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

// swiftlint:disable hard_coded_display_string

import SwiftUI

struct MyTubeFeedView: View {

    @Router
    private var router

    @State
    private var unplayedOnly: Bool = true

    @State
    private var videos: [MyTubeVideo] = []

    @State
    private var total: Int = 0

    @State
    private var offset: Int = 0

    @State
    private var hasMore: Bool = false

    @State
    private var isLoading: Bool = false

    @State
    private var isSyncing: Bool = false

    @State
    private var errorMessage: String?

    private let columns = [
        GridItem(.flexible(), spacing: 40),
        GridItem(.flexible(), spacing: 40),
        GridItem(.flexible(), spacing: 40)
    ]

    private func loadFeed(reset: Bool = false) async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil

        let currentOffset = reset ? 0 : offset

        do {
            let res = try await MyTubeClient.shared.getHomeFeed(
                unplayedOnly: unplayedOnly,
                limit: 45,
                offset: currentOffset
            )

            if reset {
                videos = res.items
            } else {
                videos.append(contentsOf: res.items)
            }

            total = res.total
            offset = currentOffset + res.items.count
            hasMore = res.hasMore
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    private func syncLibrary() {
        guard !isSyncing else { return }
        isSyncing = true

        Task { @MainActor in
            defer { isSyncing = false }
            do {
                try await MyTubeClient.shared.triggerScan()
                await loadFeed(reset: true)
            } catch {
                print("Failed to trigger scan: \(error)")
            }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                // Header & Filter Bar
                HStack(alignment: .center, spacing: 20) {
                    Text("Subscription Feed")
                        .font(.title2)
                        .fontWeight(.bold)

                    // Filter Chips
                    HStack(spacing: 12) {
                        Button {
                            unplayedOnly = true
                            Task { await loadFeed(reset: true) }
                        } label: {
                            Text("Unwatched")
                                .font(.callout)
                                .fontWeight(unplayedOnly ? .bold : .regular)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(unplayedOnly ? Color.red : Color(white: 0.25))

                        Button {
                            unplayedOnly = false
                            Task { await loadFeed(reset: true) }
                        } label: {
                            Text("All Videos")
                                .font(.callout)
                                .fontWeight(!unplayedOnly ? .bold : .regular)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(!unplayedOnly ? Color.red : Color(white: 0.25))
                    }

                    Spacer()

                    // Action buttons: Sync, Swiftfin, Settings
                    HStack(spacing: 16) {
                        Button {
                            syncLibrary()
                        } label: {
                            HStack(spacing: 8) {
                                if isSyncing {
                                    ProgressView()
                                        .scaleEffect(0.8)
                                } else {
                                    Image(systemName: "arrow.triangle.2.circlepath")
                                }
                                Text(isSyncing ? "Syncing..." : "Sync")
                                    .font(.callout)
                            }
                        }
                        .buttonStyle(.bordered)
                        .disabled(isSyncing)

                        Button {
                            router.route(to: .swiftfinHome)
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: "square.grid.2x2")
                                Text("Swiftfin")
                                    .font(.callout)
                            }
                        }
                        .buttonStyle(.bordered)

                        Button {
                            router.route(to: .settings)
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: "gearshape")
                                Text("Settings")
                                    .font(.callout)
                            }
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding(.horizontal, 50)
                .padding(.top, 20)

                // Error State
                if let errorMessage {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 40))
                            .foregroundStyle(.yellow)
                        Text(errorMessage)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                        Button("Retry") {
                            Task { await loadFeed(reset: true) }
                        }
                        .buttonStyle(.bordered)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 60)
                }

                // Empty State
                if !isLoading, videos.isEmpty, errorMessage == nil {
                    VStack(spacing: 12) {
                        Image(systemName: "play.slash")
                            .font(.system(size: 50))
                            .foregroundStyle(.secondary)
                        Text("No videos found")
                            .font(.headline)
                        Text(unplayedOnly ? "You're all caught up!" : "No videos in subscription feed.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 80)
                }

                // Video Grid
                LazyVGrid(columns: columns, spacing: 40) {
                    ForEach(videos) { vid in
                        MyTubeVideoCard(video: vid) {
                            // On status change (e.g. marked watched or trashed)
                            if unplayedOnly {
                                videos.removeAll(where: { $0.videoId == vid.videoId })
                            }
                        }
                        .onAppear {
                            if vid.id == videos.last?.id, hasMore, !isLoading {
                                Task { await loadFeed(reset: false) }
                            }
                        }
                    }
                }
                .padding(.horizontal, 50)

                if isLoading {
                    HStack {
                        Spacer()
                        ProgressView()
                            .scaleEffect(1.2)
                        Spacer()
                    }
                    .padding(.vertical, 40)
                }
            }
            .padding(.bottom, 60)
        }
        .task {
            if videos.isEmpty {
                await loadFeed(reset: true)
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .myTubeFeedNeedsRefresh)) { _ in
            Task { @MainActor in
                await loadFeed(reset: true)
            }
        }
    }
}
