//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import Foundation
import TVServices

struct MyTubeTopShelfEntry: Codable, Identifiable {

    let id: String
    let title: String
    let jellyfinItemId: String
    let imageURL: URL
    let position: Double
    let duration: Double
    let playbackProgress: Double

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case jellyfinItemId = "jellyfin_item_id"
        case imageURL = "image_url"
        case position
        case duration
        case playbackProgress = "playback_progress"
    }
}

enum MyTubeTopShelfCache {

    static let appGroupIdentifier = "group.org.jellyfin.swiftfin"

    private static let cacheKey = "mytube.continue-watching"

    private struct Candidate {

        let entry: MyTubeTopShelfEntry
        let updatedAt: String
    }

    static func update(
        movies: MyTubeMoviesHome,
        shows: MyTubeShowsHome,
        imageBaseURL: URL
    ) throws {
        var entries = movies.continueWatching.compactMap { movie in
            makeEntry(
                id: movie.movieId,
                title: movie.title,
                jellyfinItemId: movie.jellyfinItemId,
                imagePath: movie.backdropUrl ?? movie.posterUrl,
                position: movie.playbackPosition,
                duration: movie.duration,
                updatedAt: movie.updatedAt,
                imageBaseURL: imageBaseURL
            )
        }

        entries += shows.continueWatching.compactMap { show in
            guard let episode = show.currentEpisode else { return nil }
            return makeEntry(
                id: episode.episodeId,
                title: "\(show.title) · \(episode.title)",
                jellyfinItemId: episode.jellyfinItemId,
                imagePath: episode.thumbnailUrl ?? show.backdropUrl ?? show.posterUrl,
                position: episode.playbackPosition,
                duration: episode.duration,
                updatedAt: episode.updatedAt,
                imageBaseURL: imageBaseURL
            )
        }

        entries.sort { $0.updatedAt > $1.updatedAt }

        guard let defaults = UserDefaults(suiteName: appGroupIdentifier) else {
            throw MyTubeError.serverError(-1, "The MyTube Top Shelf shared container is unavailable")
        }

        defaults.set(try JSONEncoder().encode(entries.prefix(20).map(\.entry)), forKey: cacheKey)
        TVTopShelfContentProvider.topShelfContentDidChange()
    }

    private static func makeEntry(
        id: String,
        title: String,
        jellyfinItemId: String,
        imagePath: String?,
        position: Double,
        duration: Double,
        updatedAt: String?,
        imageBaseURL: URL
    ) -> Candidate? {
        guard !id.isEmpty, !jellyfinItemId.isEmpty,
              let imagePath, !imagePath.isEmpty,
              !imagePath.hasPrefix("data:image/"),
              let imageURL = URL(string: imagePath, relativeTo: imageBaseURL)?.absoluteURL else {
            return nil
        }

        let progress = duration > 0 ? min(max(position / duration, 0), 1) : 0
        return Candidate(
            entry: MyTubeTopShelfEntry(
                id: id,
                title: title,
                jellyfinItemId: jellyfinItemId,
                imageURL: imageURL,
                position: position,
                duration: duration,
                playbackProgress: progress
            ),
            updatedAt: updatedAt ?? ""
        )
    }
}
