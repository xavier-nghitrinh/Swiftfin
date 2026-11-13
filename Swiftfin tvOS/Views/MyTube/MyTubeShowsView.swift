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
                    // Continue Watching
                    if !home.continueWatching.isEmpty {
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Continue Watching")
                                .font(.title3)
                                .fontWeight(.bold)
                                .padding(.horizontal, 50)

                            ScrollView(.horizontal, showsIndicators: false) {
                                LazyHStack(spacing: 30) {
                                    ForEach(home.continueWatching) { item in
                                        if let ep = item.currentEpisode {
                                            MyTubeVideoCard(video: ep.asVideoItem)
                                                .frame(width: 420)
                                        }
                                    }
                                }
                                .padding(.horizontal, 50)
                                .padding(.vertical, 10)
                            }
                        }
                    }

                    // Recently Added
                    if !home.recentlyAdded.isEmpty {
                        ShowShelfView(
                            title: "Recently Added",
                            shows: home.recentlyAdded
                        )
                    }

                    // Genres
                    ForEach(home.genres) { shelf in
                        if !shelf.shows.isEmpty {
                            ShowShelfView(
                                title: shelf.genre,
                                shows: shelf.shows
                            )
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
                                ShowPosterView(posterUrl: show.posterUrl ?? show.backdropUrl)
                                    .frame(width: 260, height: 390)
                                    .cornerRadius(12)

                                Text(show.title)
                                    .font(.callout)
                                    .fontWeight(.semibold)
                                    .lineLimit(1)
                                    .padding(.horizontal, 4)
                            }
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
            if let firstSeason = detail?.seasons.first?.seasonNumber {
                selectedSeason = firstSeason
            }
        } catch {
            print("Failed to load show detail: \(error)")
        }

        isLoading = false
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                // Header
                HStack(alignment: .top, spacing: 30) {
                    ShowPosterView(posterUrl: show.posterUrl ?? show.backdropUrl)
                        .frame(width: 220, height: 330)
                        .cornerRadius(12)

                    VStack(alignment: .leading, spacing: 12) {
                        Text(show.title)
                            .font(.largeTitle)
                            .fontWeight(.bold)

                        if let overview = detail?.overview ?? show.overview, !overview.isEmpty {
                            Text(overview)
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .lineLimit(5)
                        }

                        if let seasons = detail?.seasons, seasons.count > 1 {
                            Picker("Season", selection: $selectedSeason) {
                                ForEach(seasons) { s in
                                    Text(s.seasonName).tag(s.seasonNumber)
                                }
                            }
                            .pickerStyle(.segmented)
                            .padding(.top, 10)
                        }
                    }

                    Spacer()
                }
                .padding(.horizontal, 50)
                .padding(.top, 20)

                // Episodes Grid
                if let currentSeason = detail?.seasons.first(where: { $0.seasonNumber == selectedSeason }) {
                    VStack(alignment: .leading, spacing: 20) {
                        Text("\(currentSeason.seasonName) Episodes")
                            .font(.title3)
                            .fontWeight(.bold)
                            .padding(.horizontal, 50)

                        LazyVGrid(columns: columns, spacing: 40) {
                            ForEach(currentSeason.episodes) { ep in
                                MyTubeVideoCard(video: ep.asVideoItem)
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

private struct ShowPosterView: View {

    @Injected(\.currentUserSession)
    private var userSession

    let posterUrl: String?

    private var imageURL: URL? {
        guard let p = posterUrl, !p.isEmpty else { return nil }
        if p.starts(with: "http://") || p.starts(with: "https://") {
            return URL(string: p)
        }
        if let host = userSession?.server.effectiveServerURL.host {
            let path = p.starts(with: "/") ? p : "/" + p
            return URL(string: "http://\(host):8000\(path)")
        }
        return nil
    }

    var body: some View {
        if let imageURL {
            AsyncImage(url: imageURL) { phase in
                switch phase {
                case let .success(img):
                    img.resizable().scaledToFill()
                default:
                    placeholder
                }
            }
        } else {
            placeholder
        }
    }

    private var placeholder: some View {
        ZStack {
            Color(white: 0.2)
            Image(systemName: "tv")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
        }
    }
}
