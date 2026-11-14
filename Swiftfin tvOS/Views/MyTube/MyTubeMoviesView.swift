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
                LazyHStack(spacing: MyTubeTileMetrics.horizontalSpacing) {
                    ForEach(movies) { movie in
                        MyTubeTileButton(action: {
                            router.route(to: .myTubeMovieDetail(movie: movie, relatedMovies: movies))
                        }) { isFocused in
                            VStack(alignment: .leading, spacing: 8) {
                                MyTubeThumbnailView(video: movie.asVideoItem, isFocused: isFocused)

                                Text(movie.title)
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                    .lineLimit(2)
                                    .multilineTextAlignment(.leading)
                                    .foregroundStyle(.primary)
                                    .frame(height: MyTubeTileMetrics.titleHeight, alignment: .topLeading)

                                HStack(spacing: 8) {
                                    if let releaseYear = movie.releaseYear {
                                        Text(String(releaseYear))
                                    }
                                }
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .frame(height: MyTubeTileMetrics.metadataHeight, alignment: .topLeading)
                            }
                            .frame(width: MyTubeTileMetrics.width, alignment: .leading)
                        }
                    }
                }
                .padding(.horizontal, 50)
                .padding(.vertical, 30)
            }
            .focusEffectDisabled()
        }
    }
}

struct MyTubeMovieDetailView: View {

    @Router
    private var router

    @Injected(\.currentUserSession)
    private var userSession

    @PlayMedia
    private var playMedia

    let movie: MyTubeMovie
    let relatedMovies: [MyTubeMovie]

    @State
    private var movieDetail: MyTubeMovie?

    @State
    private var isLoading = false

    @State
    private var isUpdatingStatus = false

    @State
    private var isMovingToTrash = false

    @State
    private var actionError: String?

    @State
    private var detailError: String?

    private var displayMovie: MyTubeMovie {
        movieDetail ?? movie
    }

    private var recommendations: [MyTubeMovie] {
        let detailedRecommendations = movieDetail?.recommendations ?? []
        let source = detailedRecommendations.isEmpty ? relatedMovies : detailedRecommendations
        return source.filter { $0.movieId != movie.movieId }
    }

    private func loadMovieDetail() async {
        do {
            movieDetail = try await MyTubeClient.shared.getMovieDetail(movieId: movie.movieId)
        } catch {
            detailError = error.localizedDescription
        }
    }

    private func play() {
        guard !isLoading else { return }
        guard let userSession else {
            actionError = MyTubeError.noActiveServer.localizedDescription
            return
        }
        isLoading = true

        Task { @MainActor in
            defer { isLoading = false }
            do {
                let video = displayMovie.asVideoItem
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

    private func toggleWatched() {
        guard !isUpdatingStatus, !isMovingToTrash else { return }
        let markWatched = !displayMovie.watched
        let movieId = displayMovie.movieId
        isUpdatingStatus = true

        Task { @MainActor in
            defer { isUpdatingStatus = false }
            do {
                if markWatched {
                    try await MyTubeClient.shared.markWatched(videoId: movieId)
                } else {
                    try await MyTubeClient.shared.markUnwatched(videoId: movieId)
                }

                var updatedMovie = displayMovie
                updatedMovie.watched = markWatched
                updatedMovie.playbackPosition = markWatched ? updatedMovie.duration : 0
                movieDetail = updatedMovie
                NotificationCenter.default.post(name: .myTubeFeedNeedsRefresh, object: nil)
            } catch {
                actionError = error.localizedDescription
            }
        }
    }

    private func moveToTrash() {
        guard !isMovingToTrash, !isUpdatingStatus else { return }
        isMovingToTrash = true
        Task { @MainActor in
            defer { isMovingToTrash = false }
            do {
                try await MyTubeClient.shared.moveToTrash(videoId: displayMovie.movieId)
                NotificationCenter.default.post(name: .myTubeFeedNeedsRefresh, object: nil)
                router.dismiss()
            } catch {
                actionError = error.localizedDescription
            }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 36) {
                MyTubeDetailHeader(
                    title: displayMovie.title,
                    placeholderSystemName: "film",
                    posterPath: displayMovie.posterUrl,
                    backdropPath: displayMovie.backdropUrl ?? displayMovie.posterUrl,
                    rating: displayMovie.communityRating,
                    metadata: [
                        displayMovie.releaseYear.map(String.init),
                        displayMovie.asVideoItem.formattedDuration
                    ].compactMap { $0 }.filter { !$0.isEmpty },
                    genres: Array(displayMovie.genres.prefix(3)),
                    overview: displayMovie.overview
                ) {
                    Button(action: play) {
                        Label(
                            isLoading
                                ? "Loading..."
                                : (displayMovie.playbackPosition > 15 && !displayMovie.watched ? "Resume" : "Play"),
                            systemImage: "play.fill"
                        )
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
                    .disabled(isLoading)

                    Button(action: toggleWatched) {
                        Label(
                            displayMovie.watched ? "Mark Unwatched" : "Mark Watched",
                            systemImage: displayMovie.watched ? "eye.slash" : "checkmark"
                        )
                    }
                    .buttonStyle(.bordered)
                    .disabled(isUpdatingStatus || isMovingToTrash)

                    Button(role: .destructive, action: moveToTrash) {
                        Label("Trash", systemImage: "trash")
                    }
                    .buttonStyle(.bordered)
                    .disabled(isUpdatingStatus || isMovingToTrash)
                }

                if let detailError {
                    Text("Additional movie details could not be loaded: \(detailError)")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 50)
                }

                if !recommendations.isEmpty {
                    MovieShelfView(title: "More Like This", movies: recommendations)
                }
            }
            .padding(.bottom, 60)
        }
        .task {
            await loadMovieDetail()
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
