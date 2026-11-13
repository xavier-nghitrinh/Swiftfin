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

struct MyTubeShowsView: View {

    @State
    private var data: MyTubeShowsHome?

    @State
    private var isLoading = false

    @State
    private var errorMessage: String?

    private func loadShows() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil

        do {
            data = try await MyTubeClient.shared.getShowsHome()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 40) {
                Text("Shows")
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
                            Task { await loadShows() }
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

                if let home = data {
                    if !home.continueWatching.isEmpty {
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Continue Watching")
                                .font(.title3)
                                .fontWeight(.bold)
                                .padding(.horizontal, 50)

                            ScrollView(.horizontal, showsIndicators: false) {
                                LazyHStack(spacing: MyTubeTileMetrics.horizontalSpacing) {
                                    ForEach(home.continueWatching) { item in
                                        if let episode = item.currentEpisode {
                                            MyTubeVideoCard(video: episode.asVideoItem)
                                                .frame(width: MyTubeTileMetrics.width)
                                        }
                                    }
                                }
                                .padding(.horizontal, 50)
                                .padding(.vertical, 30)
                            }
                        }
                    }

                    if !home.recentlyAdded.isEmpty {
                        ShowShelfView(title: "Recently Added", shows: home.recentlyAdded)
                    }

                    ForEach(home.genres) { shelf in
                        if !shelf.shows.isEmpty {
                            ShowShelfView(title: shelf.genre, shows: shelf.shows)
                        }
                    }
                }
            }
            .padding(.bottom, 60)
        }
        .task {
            if data == nil {
                await loadShows()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .myTubeFeedNeedsRefresh)) { _ in
            Task { @MainActor in
                await loadShows()
            }
        }
    }
}

private struct ShowShelfView: View {

    @Router
    private var router

    let title: String
    let shows: [MyTubeShow]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(title)
                .font(.title3)
                .fontWeight(.bold)
                .padding(.horizontal, 50)

            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: MyTubeTileMetrics.horizontalSpacing) {
                    ForEach(shows) { show in
                        MyTubeTileButton(action: {
                            router.route(to: .myTubeShowDetail(show: show))
                        }) { isFocused in
                            VStack(alignment: .leading, spacing: 8) {
                                MyTubeArtworkView(
                                    imagePath: show.backdropUrl ?? show.posterUrl,
                                    placeholderSystemName: "tv"
                                )
                                .aspectRatio(MyTubeTileMetrics.aspectRatio, contentMode: .fit)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                                .overlay {
                                    RoundedRectangle(cornerRadius: MyTubeTileMetrics.cornerRadius)
                                        .stroke(isFocused ? Color.white : .clear, lineWidth: 2)
                                        .allowsHitTesting(false)
                                }

                                Text(show.title)
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                    .lineLimit(2)
                                    .multilineTextAlignment(.leading)
                                    .foregroundStyle(.primary)
                                    .frame(height: MyTubeTileMetrics.titleHeight, alignment: .topLeading)

                                Color.clear
                                    .frame(height: MyTubeTileMetrics.metadataHeight)
                            }
                            .frame(width: MyTubeTileMetrics.width, alignment: .leading)
                        }
                    }
                }
                .padding(.horizontal, 50)
                .padding(.vertical, 10)
            }
        }
    }
}

struct MyTubeShowDetailView: View {

    @Injected(\.currentUserSession)
    private var userSession

    @PlayMedia
    private var playMedia

    let show: MyTubeShow

    @State
    private var detail: MyTubeShowDetail?

    @State
    private var selectedSeason: Int = 1

    @State
    private var isLoading = false

    @State
    private var isPlaying = false

    @State
    private var detailError: String?

    @State
    private var actionError: String?

    private let columns = MyTubeTileMetrics.gridColumns

    private func loadDetail() async {
        guard !isLoading else { return }
        isLoading = true
        detailError = nil

        do {
            detail = try await MyTubeClient.shared.getShowDetail(showId: show.showId)
            if let seasons = detail?.seasons, !seasons.isEmpty {
                let currentlyWatching = seasons
                    .flatMap(\.episodes)
                    .filter { !$0.watched && $0.playbackPosition > 0 }
                    .max { lhs, rhs in
                        lhs.seasonNumber == rhs.seasonNumber
                            ? lhs.episodeNumber < rhs.episodeNumber
                            : lhs.seasonNumber < rhs.seasonNumber
                    }
                let nextEpisodeInProgress = detail?.nextEpisode.flatMap {
                    !$0.watched && $0.playbackPosition > 0 ? $0 : nil
                }
                selectedSeason = nextEpisodeInProgress?.seasonNumber
                    ?? currentlyWatching?.seasonNumber
                    ?? seasons.first(where: { $0.seasonNumber == 1 })?.seasonNumber
                    ?? seasons[0].seasonNumber
            }
        } catch {
            detailError = error.localizedDescription
        }

        isLoading = false
    }

    private func playNextEpisode() {
        guard !isPlaying, let episode = detail?.nextEpisode else { return }
        guard let userSession else {
            actionError = MyTubeError.noActiveServer.localizedDescription
            return
        }

        isPlaying = true
        Task { @MainActor in
            defer { isPlaying = false }
            do {
                let video = episode.asVideoItem
                let entry = try await userSession.getFullItem(id: video.jellyfinItemId)
                var configuration = MediaPlaybackConfiguration()
                if video.playbackPosition > 0, !video.watched {
                    configuration.startSeconds = .seconds(video.playbackPosition)
                }

                let snapshot = entry.snapshot
                let fallbackDuration = Double(snapshot.runTimeTicks ?? 0) / 10_000_000.0
                let duration = video.duration > 0 ? video.duration : fallbackDuration
                MyTubePlaybackTracker.shared.startTracking(videoId: video.videoId, duration: duration)
                playMedia(intent: PlaybackIntent(item: snapshot, configuration: configuration))
            } catch {
                actionError = error.localizedDescription
            }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                MyTubeDetailHeader(
                    title: detail?.title ?? show.title,
                    placeholderSystemName: "tv",
                    posterPath: detail?.posterUrl ?? show.posterUrl,
                    backdropPath: detail?.backdropUrl ?? show.backdropUrl ?? show.posterUrl,
                    rating: detail?.communityRating,
                    metadata: [
                        detail?.startYear.map(String.init),
                        detail.map { "\($0.totalEpisodes) episodes" }
                    ].compactMap { $0 },
                    genres: Array((detail?.genres ?? []).prefix(3)),
                    overview: detail?.overview ?? show.overview
                ) {
                    if let episode = detail?.nextEpisode {
                        Button(action: playNextEpisode) {
                            Label(
                                isPlaying
                                    ? "Loading..."
                                    : (episode.playbackPosition > 15 && !episode.watched ? "Resume" : "Play Next Episode"),
                                systemImage: "play.fill"
                            )
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.red)
                        .disabled(isPlaying)
                    }
                }

                if let detailError {
                    Text("Show details could not be loaded: \(detailError)")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 50)
                }

                if let seasons = detail?.seasons, !seasons.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Seasons")
                            .font(.title3)
                            .fontWeight(.bold)
                            .padding(.horizontal, 50)

                        MyTubeSeasonTabs(seasons: seasons, selection: $selectedSeason)
                    }

                    if let currentSeason = seasons.first(where: { $0.seasonNumber == selectedSeason }) {
                        VStack(alignment: .leading, spacing: 20) {
                            Text("\(currentSeason.seasonName) Episodes")
                                .font(.title3)
                                .fontWeight(.bold)
                                .padding(.horizontal, 50)

                            LazyVGrid(columns: columns, spacing: 40) {
                                ForEach(currentSeason.episodes) { episode in
                                    MyTubeVideoCard(video: episode.asVideoItem)
                                }
                            }
                            .padding(.horizontal, 50)
                        }
                    }
                }
            }
            .padding(.bottom, 60)
        }
        .task {
            await loadDetail()
        }
        .alert("MyTube", isPresented: Binding(
            get: { actionError != nil },
            set: { if !$0 { actionError = nil } }
        )) {
            Button("OK", role: .cancel) {
                actionError = nil
            }
        } message: {
            Text(actionError ?? "")
        }
    }
}

private struct MyTubeSeasonTabs: View {

    let seasons: [MyTubeSeason]
    @Binding var selection: Int

    @FocusState
    private var focusedSeason: Int?

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(seasons) { season in
                        Button {
                            selection = season.seasonNumber
                        } label: {
                            Text(season.seasonName)
                                .font(.callout.weight(.semibold))
                                .padding(.horizontal, 20)
                                .padding(.vertical, 12)
                                .background(
                                    selection == season.seasonNumber ? Color.red : Color.white.opacity(0.12),
                                    in: Capsule()
                                )
                                .overlay {
                                    Capsule()
                                        .stroke(
                                            focusedSeason == season.seasonNumber ? Color.white : .clear,
                                            lineWidth: 2
                                        )
                                }
                        }
                        .buttonStyle(.plain)
                        .focusEffectDisabled()
                        .focused($focusedSeason, equals: season.seasonNumber)
                        .id(season.seasonNumber)
                    }
                }
                .padding(.horizontal, 50)
                .padding(.vertical, 12)
            }
            .focusSection()
            .onAppear {
                proxy.scrollTo(selection, anchor: .center)
            }
            .onChange(of: selection) { _, selectedSeason in
                withAnimation {
                    proxy.scrollTo(selectedSeason, anchor: .center)
                }
            }
        }
    }
}
