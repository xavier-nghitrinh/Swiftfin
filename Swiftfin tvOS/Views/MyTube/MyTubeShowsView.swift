//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

// swiftlint:disable hard_coded_display_string

import FactoryKit
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
                                LazyHStack(spacing: 30) {
                                    ForEach(home.continueWatching) { item in
                                        if let episode = item.currentEpisode {
                                            MyTubeVideoCard(video: episode.asVideoItem)
                                                .frame(width: 420)
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
                LazyHStack(spacing: 30) {
                    ForEach(shows) { show in
                        Button {
                            router.route(to: .myTubeShowDetail(show: show))
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                MyTubeArtworkView(
                                    imagePath: show.backdropUrl ?? show.posterUrl,
                                    placeholderSystemName: "tv"
                                )
                                .aspectRatio(16.0 / 9.0, contentMode: .fit)
                                .clipShape(RoundedRectangle(cornerRadius: 12))

                                Text(show.title)
                                    .font(.callout)
                                    .fontWeight(.semibold)
                                    .lineLimit(2)
                                    .multilineTextAlignment(.leading)
                                    .foregroundStyle(.primary)
                            }
                            .frame(width: 420, alignment: .leading)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.card)
                    }
                }
                .padding(.horizontal, 50)
                .padding(.vertical, 10)
            }
        }
    }
}

struct MyTubeShowDetailView: View {

    let show: MyTubeShow

    @State
    private var detail: MyTubeShowDetail?

    @State
    private var selectedSeason: Int = 1

    @State
    private var isLoading = false

    private let columns = [
        GridItem(.flexible(), spacing: 40),
        GridItem(.flexible(), spacing: 40),
        GridItem(.flexible(), spacing: 40)
    ]

    private func loadDetail() async {
        guard !isLoading else { return }
        isLoading = true

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
                selectedSeason = currentlyWatching?.seasonNumber
                    ?? seasons.first(where: { $0.seasonNumber == 1 })?.seasonNumber
                    ?? seasons[0].seasonNumber
            }
        } catch {
            print("Failed to load show detail: \(error)")
        }

        isLoading = false
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                ZStack(alignment: .leading) {
                    MyTubeArtworkView(
                        imagePath: detail?.backdropUrl ?? show.backdropUrl ?? show.posterUrl,
                        placeholderSystemName: "tv"
                    )
                    .frame(maxWidth: .infinity)
                    .frame(height: 380)
                    .overlay {
                        LinearGradient(
                            colors: [.black.opacity(0.15), .black.opacity(0.95)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    }

                    HStack(alignment: .bottom, spacing: 30) {
                        MyTubeArtworkView(
                            imagePath: detail?.posterUrl ?? show.posterUrl ?? show.backdropUrl,
                            placeholderSystemName: "tv"
                        )
                        .frame(width: 180, height: 270)
                        .clipShape(RoundedRectangle(cornerRadius: 12))

                        VStack(alignment: .leading, spacing: 12) {
                            Text(detail?.title ?? show.title)
                                .font(.largeTitle)
                                .fontWeight(.bold)

                            if let overview = detail?.overview ?? show.overview, !overview.isEmpty {
                                Text(overview)
                                    .font(.callout)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(5)
                            }

                            if let seasons = detail?.seasons, seasons.count > 1 {
                                Group {
                                    if seasons.count < 6 {
                                        Picker("Season", selection: $selectedSeason) {
                                            ForEach(seasons) { season in
                                                Text(season.seasonName).tag(season.seasonNumber)
                                            }
                                        }
                                        .pickerStyle(.segmented)
                                    } else {
                                        Picker("Season", selection: $selectedSeason) {
                                            ForEach(seasons) { season in
                                                Text(season.seasonName).tag(season.seasonNumber)
                                            }
                                        }
                                        .pickerStyle(.menu)
                                    }
                                }
                                .padding(.top, 10)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(.horizontal, 50)
                    .padding(.bottom, 28)
                }
                .frame(height: 380)

                if let currentSeason = detail?.seasons.first(where: { $0.seasonNumber == selectedSeason }) {
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
            .padding(.bottom, 60)
        }
        .task {
            await loadDetail()
        }
    }
}
