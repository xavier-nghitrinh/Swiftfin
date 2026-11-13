//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

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
                    // Continue Watching
                    if !home.continueWatching.isEmpty {
                        MovieShelfView(
                            title: "Continue Watching",
                            movies: home.continueWatching
                        )
                    }

                    // Recently Added
                    if !home.recentlyAdded.isEmpty {
                        MovieShelfView(
                            title: "Recently Added",
                            movies: home.recentlyAdded
                        )
                    }

                    // Genres
                    ForEach(home.genres) { shelf in
                        if !shelf.movies.isEmpty {
                            MovieShelfView(
                                title: shelf.genre,
                                movies: shelf.movies
                            )
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
                        MyTubeVideoCard(video: movie.asVideoItem)
                            .frame(width: 420)
                    }
                }
                .padding(.horizontal, 50)
                .padding(.vertical, 10)
            }
        }
    }
}
