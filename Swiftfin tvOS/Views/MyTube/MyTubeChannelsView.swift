//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import FactoryKit
import SwiftUI

struct MyTubeChannelsView: View {

    @Router
    private var router

    @State
    private var channels: [MyTubeChannel] = []

    @State
    private var isLoading = false

    @State
    private var errorMessage: String?

    private let columns = [
        GridItem(.flexible(), spacing: 40),
        GridItem(.flexible(), spacing: 40),
        GridItem(.flexible(), spacing: 40),
        GridItem(.flexible(), spacing: 40)
    ]

    private func loadChannels() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil

        do {
            channels = try await MyTubeClient.shared.getChannels()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                Text("Channels")
                    .font(.title2)
                    .fontWeight(.bold)
                    .padding(.horizontal, 50)
                    .padding(.top, 20)

                if let errorMessage {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 40))
                            .foregroundStyle(.yellow)
                        Text(errorMessage)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                        Button("Retry") {
                            Task { await loadChannels() }
                        }
                        .buttonStyle(.bordered)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 60)
                }

                if isLoading {
                    HStack {
                        Spacer()
                        ProgressView().scaleEffect(1.2)
                        Spacer()
                    }
                    .padding(.vertical, 60)
                }

                LazyVGrid(columns: columns, spacing: 40) {
                    ForEach(channels) { channel in
                        Button {
                            router.route(to: .myTubeChannelDetail(channel: channel))
                        } label: {
                            VStack(spacing: 12) {
                                ZStack(alignment: .topTrailing) {
                                    ChannelAvatarView(thumbnailUrl: channel.thumbnailUrl, name: channel.name)
                                        .frame(width: 140, height: 140)
                                        .clipShape(Circle())

                                    if channel.unwatchedCount > 0 {
                                        Text("\(channel.unwatchedCount)")
                                            .font(.caption2)
                                            .fontWeight(.bold)
                                            .foregroundStyle(.white)
                                            .padding(.horizontal, 8)
                                            .padding(.vertical, 4)
                                            .background(Color.red)
                                            .clipShape(Capsule())
                                            .offset(x: 8, y: -4)
                                    }
                                }

                                Text(channel.name)
                                    .font(.callout)
                                    .fontWeight(.semibold)
                                    .lineLimit(1)

                                Text("\(channel.totalVideos) videos")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(.vertical, 16)
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.card)
                    }
                }
                .padding(.horizontal, 50)
            }
            .padding(.bottom, 60)
        }
        .task {
            if channels.isEmpty {
                await loadChannels()
            }
        }
    }
}

private struct ChannelAvatarView: View {

    @Injected(\.currentUserSession)
    private var userSession

    let thumbnailUrl: String?
    let name: String

    private var base64Image: UIImage? {
        guard let thumb = thumbnailUrl, thumb.starts(with: "data:image/") else { return nil }
        guard let commaIndex = thumb.firstIndex(of: ",") else { return nil }
        let b64 = String(thumb[thumb.index(after: commaIndex)...])
        guard let data = Data(base64Encoded: b64, options: .ignoreUnknownCharacters) else { return nil }
        return UIImage(data: data)
    }

    private var imageURL: URL? {
        guard let thumb = thumbnailUrl, !thumb.isEmpty else { return nil }
        if thumb.starts(with: "http://") || thumb.starts(with: "https://") {
            return URL(string: thumb)
        }
        if let host = userSession?.server.effectiveServerURL.host {
            let path = thumb.starts(with: "/") ? thumb : "/" + thumb
            return URL(string: "http://\(host):8000\(path)")
        }
        return nil
    }

    var body: some View {
        if let base64Image {
            Image(uiImage: base64Image)
                .resizable()
                .scaledToFill()
        } else if let imageURL {
            AsyncImage(url: imageURL) { phase in
                switch phase {
                case let .success(img):
                    img.resizable().scaledToFill()
                default:
                    initialsView
                }
            }
        } else {
            initialsView
        }
    }

    private var initialsView: some View {
        ZStack {
            Color.red.opacity(0.8)
            Text(String(name.prefix(1)).uppercased())
                .font(.system(size: 48, weight: .bold))
                .foregroundStyle(.white)
        }
    }
}

struct MyTubeChannelDetailView: View {

    let channel: MyTubeChannel

    @State
    private var selectedFilter: String = "all" // all, unwatched, watched

    @State
    private var videos: [MyTubeVideo] = []

    @State
    private var isLoading = false

    private let columns = [
        GridItem(.flexible(), spacing: 40),
        GridItem(.flexible(), spacing: 40),
        GridItem(.flexible(), spacing: 40)
    ]

    private func loadVideos() async {
        guard !isLoading else { return }
        isLoading = true

        do {
            let res = try await MyTubeClient.shared.getChannelVideos(
                channelId: channel.channelId,
                filter: selectedFilter,
                limit: 100,
                offset: 0
            )
            videos = res.items
        } catch {
            print("Failed to load channel videos: \(error)")
        }

        isLoading = false
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                // Channel Header
                HStack(spacing: 24) {
                    ChannelAvatarView(thumbnailUrl: channel.thumbnailUrl, name: channel.name)
                        .frame(width: 90, height: 90)
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 6) {
                        Text(channel.name)
                            .font(.title)
                            .fontWeight(.bold)

                        Text("\(channel.totalVideos) videos • \(channel.unwatchedCount) unwatched")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    // Filters
                    HStack(spacing: 12) {
                        filterButton(title: "All", filter: "all")
                        filterButton(title: "Unwatched", filter: "unwatched")
                        filterButton(title: "Watched", filter: "watched")
                    }
                }
                .padding(.horizontal, 50)
                .padding(.top, 20)

                // Video Grid
                if isLoading {
                    HStack {
                        Spacer()
                        ProgressView().scaleEffect(1.2)
                        Spacer()
                    }
                    .padding(.vertical, 60)
                } else if videos.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "play.slash")
                            .font(.system(size: 40))
                            .foregroundStyle(.secondary)
                        Text("No videos found with this filter")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 60)
                } else {
                    LazyVGrid(columns: columns, spacing: 40) {
                        ForEach(videos) { vid in
                            MyTubeVideoCard(video: vid) {
                                Task { await loadVideos() }
                            }
                        }
                    }
                    .padding(.horizontal, 50)
                }
            }
            .padding(.bottom, 60)
        }
        .task {
            await loadVideos()
        }
        .onReceive(NotificationCenter.default.publisher(for: .myTubeFeedNeedsRefresh)) { _ in
            Task { @MainActor in
                await loadVideos()
            }
        }
    }

    @ViewBuilder
    private func filterButton(title: String, filter: String) -> some View {
        Button {
            selectedFilter = filter
            Task { await loadVideos() }
        } label: {
            Text(title)
                .font(.callout)
                .fontWeight(selectedFilter == filter ? .bold : .regular)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
        }
        .buttonStyle(.borderedProminent)
        .tint(selectedFilter == filter ? Color.red : Color(white: 0.25))
    }
}
