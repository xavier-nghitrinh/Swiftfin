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

struct MyTubeMoviesView: View {

    @State
    private var data: MyTubeMoviesHome?

    @State
    private var isLoading = false

    @State
    private var errorMessage: String?

    private func loadMovies() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil

        do {
            data = try await MyTubeClient.shared.getMoviesHome()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 40) {
                Text("Movies")
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
                            Task { await loadMovies() }
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
                        MovieShelfView(title: "Continue Watching", movies: home.continueWatching)
                    }

                    if !home.recentlyAdded.isEmpty {
                        MovieShelfView(title: "Recently Added", movies: home.recentlyAdded)
                    }

                    ForEach(home.genres) { shelf in
                        if !shelf.movies.isEmpty {
                            MovieShelfView(title: shelf.genre, movies: shelf.movies)
                        }
                    }
                }
            }
            .padding(.bottom, 60)
        }
        .task {
            if data == nil {
                await loadMovies()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .myTubeFeedNeedsRefresh)) { _ in
            Task { @MainActor in
                await loadMovies()
            }
        }
    }
}

private struct MovieShelfView: View {

    @Router
    private var router

    let title: String
    let movies: [MyTubeMovie]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(title)
                .font(.title3)
                .fontWeight(.bold)
                .padding(.horizontal, 50)

            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 30) {
                    ForEach(movies) { movie in
                        Button {
                            router.route(to: .myTubeMovieDetail(movie: movie, relatedMovies: movies))
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                MyTubeArtworkView(
                                    imagePath: movie.backdropUrl ?? movie.posterUrl,
                                    placeholderSystemName: "film"
                                )
                                .aspectRatio(16.0 / 9.0, contentMode: .fit)
                                .clipShape(RoundedRectangle(cornerRadius: 12))

                                Text(movie.title)
                                    .font(.callout)
                                    .fontWeight(.semibold)
                                    .lineLimit(2)
                                    .multilineTextAlignment(.leading)
                                    .foregroundStyle(.primary)

                                HStack(spacing: 8) {
                                    if let releaseYear = movie.releaseYear {
                                        Text(String(releaseYear))
                                    }
                                    if !movie.asVideoItem.formattedDuration.isEmpty {
                                        Text(movie.asVideoItem.formattedDuration)
                                    }
                                }
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            }
                            .frame(width: 420, alignment: .leading)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.card)
                    }
                }
                .padding(.horizontal, 50)
                .padding(.vertical, 30)
            }
        }
    }
}

struct MyTubeMovieDetailView: View {

    @Injected(\.currentUserSession)
    private var userSession

    @PlayMedia
    private var playMedia

    let movie: MyTubeMovie
    let relatedMovies: [MyTubeMovie]

    @State
    private var isLoading = false

    private func play() {
        guard !isLoading, let userSession else { return }
        isLoading = true

        Task { @MainActor in
            defer { isLoading = false }
            do {
                let video = movie.asVideoItem
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
                print("MyTubeMovieDetailView: Failed to load movie \(movie.jellyfinItemId): \(error)")
            }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 36) {
                ZStack(alignment: .leading) {
                    MyTubeArtworkView(
                        imagePath: movie.backdropUrl ?? movie.posterUrl,
                        placeholderSystemName: "film"
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
                            imagePath: movie.posterUrl ?? movie.backdropUrl,
                            placeholderSystemName: "film"
                        )
                        .frame(width: 180, height: 270)
                        .clipShape(RoundedRectangle(cornerRadius: 12))

                        VStack(alignment: .leading, spacing: 14) {
                            Text(movie.title)
                                .font(.largeTitle)
                                .fontWeight(.bold)

                            HStack(spacing: 12) {
                                if let releaseYear = movie.releaseYear {
                                    Text(String(releaseYear))
                                }
                                if !movie.asVideoItem.formattedDuration.isEmpty {
                                    Text(movie.asVideoItem.formattedDuration)
                                }
                            }
                            .font(.callout)
                            .foregroundStyle(.secondary)

                            if let overview = movie.overview, !overview.isEmpty {
                                Text(overview)
                                    .font(.callout)
                                    .lineLimit(5)
                                    .foregroundStyle(.secondary)
                            }

                            Button(action: play) {
                                Label(isLoading ? "Loading..." : "Play", systemImage: "play.fill")
                                    .font(.headline)
                                    .padding(.horizontal, 22)
                                    .padding(.vertical, 12)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.red)
                            .disabled(isLoading)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(.horizontal, 50)
                    .padding(.bottom, 28)
                }
                .frame(height: 380)

                let related = relatedMovies.filter { $0.movieId != movie.movieId }
                if !related.isEmpty {
                    MovieShelfView(title: "More Like This", movies: related)
                }
            }
            .padding(.bottom, 60)
        }
    }
}
