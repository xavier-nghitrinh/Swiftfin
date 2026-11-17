//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

// swiftlint:disable hard_coded_display_string

import SwiftUI

struct MyTubeGoneSoonView: View {

    @AppStorage("myTubeUnwatchedOnly")
    private var unplayedOnly: Bool = true

    let isActive: Bool

    init(isActive: Bool = false) {
        self.isActive = isActive
    }

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
    private var errorMessage: String?

    private let columns = MyTubeTileMetrics.gridColumns
    private let pageSize = 20

    private func loadPage(reset: Bool = false) async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil

        let currentOffset = reset ? 0 : offset

        do {
            let res = try await MyTubeClient.shared.getGoneSoon(
                unplayedOnly: unplayedOnly,
                limit: pageSize,
                offset: currentOffset
            )

            // Server order is oldest first, so keep it as-is.
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

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                HStack(alignment: .center, spacing: 20) {
                    Image(systemName: "trash.fill")
                        .font(.title2)
                        .foregroundStyle(.red)

                    Text("Gone Soon")
                        .font(.title2)
                        .fontWeight(.bold)

                    if total > 0 {
                        Text("\(total) videos")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    HStack(spacing: 12) {
                        Button {
                            unplayedOnly = true
                            Task { await loadPage(reset: true) }
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
                            Task { await loadPage(reset: true) }
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
                }
                .padding(.horizontal, 50)
                .padding(.top, 20)

                Text("These videos are the oldest in your subscriptions and will be deleted automatically when space runs low. Watch them before they go.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 50)

                if let errorMessage {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 40))
                            .foregroundStyle(.yellow)
                        Text(errorMessage)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                        Button("Retry") {
                            Task { await loadPage(reset: true) }
                        }
                        .buttonStyle(.bordered)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 60)
                }

                if !isLoading, videos.isEmpty, errorMessage == nil {
                    VStack(spacing: 12) {
                        Image(systemName: "checkmark.circle")
                            .font(.system(size: 50))
                            .foregroundStyle(.secondary)
                        Text("Nothing is scheduled for deletion")
                            .font(.headline)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 80)
                }

                LazyVGrid(columns: columns, spacing: 40) {
                    ForEach(videos) { vid in
                        MyTubeVideoCard(video: vid)
                            .onAppear {
                                if vid.id == videos.last?.id, hasMore, !isLoading {
                                    Task { await loadPage(reset: false) }
                                }
                            }
                    }
                }
                .padding(.horizontal, 50)
                .focusEffectDisabled()

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
            await loadPage(reset: true)
        }
        .onChange(of: isActive) { _, active in
            guard active else { return }
            Task { @MainActor in
                await loadPage(reset: true)
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .myTubeFeedNeedsRefresh)) { _ in
            Task { @MainActor in
                await loadPage(reset: true)
            }
        }
    }
}
