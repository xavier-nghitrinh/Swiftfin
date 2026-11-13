//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import Foundation

// MARK: - Video Item

struct MyTubeVideo: Identifiable, Hashable, Codable, Sendable {

    var id: String { videoId }

    let videoId: String
    let channelId: String?
    let channelName: String?
    let title: String
    let descriptionText: String?
    let uploadDate: String?
    let duration: Double
    let thumbnailUrl: String?
    let jellyfinItemId: String
    var watched: Bool
    let watchedAt: String?
    var playbackPosition: Double
    let channelThumbnailUrl: String?
    let mediaType: String?

    enum CodingKeys: String, CodingKey {
        case videoId = "video_id"
        case channelId = "channel_id"
        case channelName = "channel_name"
        case title
        case descriptionText = "description"
        case uploadDate = "upload_date"
        case duration
        case thumbnailUrl = "thumbnail_url"
        case jellyfinItemId = "jellyfin_item_id"
        case watched
        case watchedAt = "watched_at"
        case playbackPosition = "playback_position"
        case channelThumbnailUrl = "channel_thumbnail_url"
        case mediaType = "media_type"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        videoId = try container.decode(String.self, forKey: .videoId)
        channelId = try container.decodeIfPresent(String.self, forKey: .channelId)
        channelName = try container.decodeIfPresent(String.self, forKey: .channelName)
        title = (try? container.decode(String.self, forKey: .title)) ?? ""
        descriptionText = try container.decodeIfPresent(String.self, forKey: .descriptionText)
        uploadDate = try container.decodeIfPresent(String.self, forKey: .uploadDate)

        // Resilient duration decoding (can be Double, Int, or missing)
        if let d = try? container.decode(Double.self, forKey: .duration) {
            duration = d
        } else if let i = try? container.decode(Int.self, forKey: .duration) {
            duration = Double(i)
        } else {
            duration = 0
        }

        thumbnailUrl = try container.decodeIfPresent(String.self, forKey: .thumbnailUrl)
        jellyfinItemId = (try? container.decode(String.self, forKey: .jellyfinItemId)) ?? ""

        // Resilient watched decoding (can be Bool, Int 0/1, or missing)
        if let b = try? container.decode(Bool.self, forKey: .watched) {
            watched = b
        } else if let i = try? container.decode(Int.self, forKey: .watched) {
            watched = (i != 0)
        } else {
            watched = false
        }

        watchedAt = try container.decodeIfPresent(String.self, forKey: .watchedAt)

        // Resilient playbackPosition decoding
        if let p = try? container.decode(Double.self, forKey: .playbackPosition) {
            playbackPosition = p
        } else if let i = try? container.decode(Int.self, forKey: .playbackPosition) {
            playbackPosition = Double(i)
        } else {
            playbackPosition = 0
        }

        channelThumbnailUrl = try container.decodeIfPresent(String.self, forKey: .channelThumbnailUrl)
        mediaType = try container.decodeIfPresent(String.self, forKey: .mediaType)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(videoId, forKey: .videoId)
        try container.encodeIfPresent(channelId, forKey: .channelId)
        try container.encodeIfPresent(channelName, forKey: .channelName)
        try container.encode(title, forKey: .title)
        try container.encodeIfPresent(descriptionText, forKey: .descriptionText)
        try container.encodeIfPresent(uploadDate, forKey: .uploadDate)
        try container.encode(duration, forKey: .duration)
        try container.encodeIfPresent(thumbnailUrl, forKey: .thumbnailUrl)
        try container.encode(jellyfinItemId, forKey: .jellyfinItemId)
        try container.encode(watched, forKey: .watched)
        try container.encodeIfPresent(watchedAt, forKey: .watchedAt)
        try container.encode(playbackPosition, forKey: .playbackPosition)
        try container.encodeIfPresent(channelThumbnailUrl, forKey: .channelThumbnailUrl)
        try container.encodeIfPresent(mediaType, forKey: .mediaType)
    }

    var formattedDuration: String {
        guard duration > 0 else { return "" }
        let total = Int(duration)
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let seconds = total % 60
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        } else {
            return String(format: "%d:%02d", minutes, seconds)
        }
    }

    var formattedUploadDate: String {
        guard let uploadDate, !uploadDate.isEmpty else { return "" }
        if uploadDate.count == 8, uploadDate.allSatisfy(\.isNumber) {
            let year = uploadDate.prefix(4)
            let month = uploadDate.dropFirst(4).prefix(2)
            let day = uploadDate.suffix(2)
            return "\(year)-\(month)-\(day)"
        }
        if uploadDate.count >= 10 {
            return String(uploadDate.prefix(10))
        }
        return uploadDate
    }

    var isPartiallyWatched: Bool {
        playbackPosition > 5 && !watched
    }

    var progressFraction: Double {
        guard duration > 0 else { return 0 }
        return min(max(playbackPosition / duration, 0), 1.0)
    }
}

// MARK: - Feed Response

struct MyTubeFeedResponse: Codable, Sendable {

    let items: [MyTubeVideo]
    let total: Int
    let limit: Int
    let offset: Int
    let hasMore: Bool

    enum CodingKeys: String, CodingKey {
        case items
        case total
        case limit
        case offset
        case hasMore = "has_more"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        items = (try? container.decode([MyTubeVideo].self, forKey: .items)) ?? []
        total = (try? container.decode(Int.self, forKey: .total)) ?? items.count
        limit = (try? container.decode(Int.self, forKey: .limit)) ?? 50
        offset = (try? container.decode(Int.self, forKey: .offset)) ?? 0
        hasMore = (try? container.decode(Bool.self, forKey: .hasMore)) ?? false
    }
}

// MARK: - Channel

struct MyTubeChannel: Identifiable, Hashable, Codable, Sendable {

    var id: String { channelId }

    let channelId: String
    let name: String
    let thumbnailUrl: String?
    let totalVideos: Int
    let unwatchedCount: Int
    let latestUploadDate: String?

    enum CodingKeys: String, CodingKey {
        case channelId = "channel_id"
        case name
        case thumbnailUrl = "thumbnail_url"
        case totalVideos = "total_videos"
        case unwatchedCount = "unwatched_count"
        case latestUploadDate = "latest_upload_date"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        channelId = try container.decode(String.self, forKey: .channelId)
        name = (try? container.decode(String.self, forKey: .name)) ?? "Unknown Channel"
        thumbnailUrl = try container.decodeIfPresent(String.self, forKey: .thumbnailUrl)
        totalVideos = (try? container.decode(Int.self, forKey: .totalVideos)) ?? 0
        unwatchedCount = (try? container.decode(Int.self, forKey: .unwatchedCount)) ?? 0
        latestUploadDate = try container.decodeIfPresent(String.self, forKey: .latestUploadDate)
    }
}

// MARK: - Movies Home

struct MyTubeMoviesHome: Codable, Sendable {

    let featured: MyTubeMovie?
    let continueWatching: [MyTubeMovie]
    let recentlyAdded: [MyTubeMovie]
    let genres: [MyTubeMovieGenreShelf]
    let allMovies: [MyTubeMovie]
    let totalMovies: Int

    enum CodingKeys: String, CodingKey {
        case featured
        case continueWatching = "continue_watching"
        case recentlyAdded = "recently_added"
        case genres
        case allMovies = "all_movies"
        case totalMovies = "total_movies"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        featured = try container.decodeIfPresent(MyTubeMovie.self, forKey: .featured)
        continueWatching = (try? container.decode([MyTubeMovie].self, forKey: .continueWatching)) ?? []
        recentlyAdded = (try? container.decode([MyTubeMovie].self, forKey: .recentlyAdded)) ?? []
        genres = (try? container.decode([MyTubeMovieGenreShelf].self, forKey: .genres)) ?? []
        allMovies = (try? container.decode([MyTubeMovie].self, forKey: .allMovies)) ?? []
        totalMovies = (try? container.decode(Int.self, forKey: .totalMovies)) ?? allMovies.count
    }
}

struct MyTubeMovieGenreShelf: Identifiable, Hashable, Codable, Sendable {

    var id: String { genre }
    let genre: String
    let movies: [MyTubeMovie]

    enum CodingKeys: String, CodingKey {
        case genre
        case movies
    }
}

struct MyTubeMovie: Identifiable, Hashable, Codable, Sendable {

    var id: String { movieId }

    let movieId: String
    let title: String
    let overview: String?
    let releaseYear: Int?
    let duration: Double
    let posterUrl: String?
    let backdropUrl: String?
    let jellyfinItemId: String
    var watched: Bool
    var playbackPosition: Double
    let progressPercent: Double?

    enum CodingKeys: String, CodingKey {
        case movieId = "movie_id"
        case title
        case overview
        case releaseYear = "release_year"
        case duration
        case posterUrl = "poster_url"
        case backdropUrl = "backdrop_url"
        case jellyfinItemId = "jellyfin_item_id"
        case watched
        case playbackPosition = "playback_position"
        case progressPercent = "progress_percent"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        movieId = try container.decode(String.self, forKey: .movieId)
        title = (try? container.decode(String.self, forKey: .title)) ?? "Untitled Movie"
        overview = try container.decodeIfPresent(String.self, forKey: .overview)
        releaseYear = try container.decodeIfPresent(Int.self, forKey: .releaseYear)

        if let d = try? container.decode(Double.self, forKey: .duration) {
            duration = d
        } else if let i = try? container.decode(Int.self, forKey: .duration) {
            duration = Double(i)
        } else {
            duration = 0
        }

        posterUrl = try container.decodeIfPresent(String.self, forKey: .posterUrl)
        backdropUrl = try container.decodeIfPresent(String.self, forKey: .backdropUrl)
        jellyfinItemId = (try? container.decode(String.self, forKey: .jellyfinItemId)) ?? ""

        if let b = try? container.decode(Bool.self, forKey: .watched) {
            watched = b
        } else if let i = try? container.decode(Int.self, forKey: .watched) {
            watched = (i != 0)
        } else {
            watched = false
        }

        if let p = try? container.decode(Double.self, forKey: .playbackPosition) {
            playbackPosition = p
        } else if let i = try? container.decode(Int.self, forKey: .playbackPosition) {
            playbackPosition = Double(i)
        } else {
            playbackPosition = 0
        }

        if let pp = try? container.decode(Double.self, forKey: .progressPercent) {
            progressPercent = pp
        } else {
            progressPercent = nil
        }
    }

    var asVideoItem: MyTubeVideo {
        MyTubeVideo(
            videoId: movieId,
            channelId: "movies",
            channelName: nil,
            title: title,
            descriptionText: overview,
            uploadDate: releaseYear.map(String.init),
            duration: duration,
            thumbnailUrl: backdropUrl ?? posterUrl,
            jellyfinItemId: jellyfinItemId,
            watched: watched,
            watchedAt: nil,
            playbackPosition: playbackPosition,
            channelThumbnailUrl: nil,
            mediaType: "movie"
        )
    }
}

private extension MyTubeVideo {

    init(
        videoId: String,
        channelId: String?,
        channelName: String?,
        title: String,
        descriptionText: String?,
        uploadDate: String?,
        duration: Double,
        thumbnailUrl: String?,
        jellyfinItemId: String,
        watched: Bool,
        watchedAt: String?,
        playbackPosition: Double,
        channelThumbnailUrl: String?,
        mediaType: String?
    ) {
        self.videoId = videoId
        self.channelId = channelId
        self.channelName = channelName
        self.title = title
        self.descriptionText = descriptionText
        self.uploadDate = uploadDate
        self.duration = duration
        self.thumbnailUrl = thumbnailUrl
        self.jellyfinItemId = jellyfinItemId
        self.watched = watched
        self.watchedAt = watchedAt
        self.playbackPosition = playbackPosition
        self.channelThumbnailUrl = channelThumbnailUrl
        self.mediaType = mediaType
    }
}

// MARK: - Shows Home

struct MyTubeShowsHome: Codable, Sendable {

    let featured: MyTubeShow?
    let continueWatching: [MyTubeContinueWatchingShow]
    let recentlyAdded: [MyTubeShow]
    let genres: [MyTubeShowGenreShelf]
    let allShows: [MyTubeShow]
    let totalShows: Int

    enum CodingKeys: String, CodingKey {
        case featured
        case continueWatching = "continue_watching"
        case recentlyAdded = "recently_added"
        case genres
        case allShows = "all_shows"
        case totalShows = "total_shows"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        featured = try container.decodeIfPresent(MyTubeShow.self, forKey: .featured)
        continueWatching = (try? container.decode([MyTubeContinueWatchingShow].self, forKey: .continueWatching)) ?? []
        recentlyAdded = (try? container.decode([MyTubeShow].self, forKey: .recentlyAdded)) ?? []
        genres = (try? container.decode([MyTubeShowGenreShelf].self, forKey: .genres)) ?? []
        allShows = (try? container.decode([MyTubeShow].self, forKey: .allShows)) ?? []
        totalShows = (try? container.decode(Int.self, forKey: .totalShows)) ?? allShows.count
    }
}

struct MyTubeShowGenreShelf: Identifiable, Hashable, Codable, Sendable {

    var id: String { genre }
    let genre: String
    let shows: [MyTubeShow]
}

struct MyTubeShow: Identifiable, Hashable, Codable, Sendable {

    var id: String { showId }

    let showId: String
    let title: String
    let overview: String?
    let posterUrl: String?
    let backdropUrl: String?
    let jellyfinItemId: String

    enum CodingKeys: String, CodingKey {
        case showId = "show_id"
        case title
        case overview
        case posterUrl = "poster_url"
        case backdropUrl = "backdrop_url"
        case jellyfinItemId = "jellyfin_item_id"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        showId = try container.decode(String.self, forKey: .showId)
        title = (try? container.decode(String.self, forKey: .title)) ?? "Untitled Show"
        overview = try container.decodeIfPresent(String.self, forKey: .overview)
        posterUrl = try container.decodeIfPresent(String.self, forKey: .posterUrl)
        backdropUrl = try container.decodeIfPresent(String.self, forKey: .backdropUrl)
        jellyfinItemId = (try? container.decode(String.self, forKey: .jellyfinItemId)) ?? ""
    }
}

struct MyTubeContinueWatchingShow: Identifiable, Hashable, Codable, Sendable {

    var id: String { showId }

    let showId: String
    let title: String
    let posterUrl: String?
    let backdropUrl: String?
    let currentEpisode: MyTubeEpisode?
    let playbackPosition: Double
    let duration: Double

    enum CodingKeys: String, CodingKey {
        case showId = "show_id"
        case title
        case posterUrl = "poster_url"
        case backdropUrl = "backdrop_url"
        case currentEpisode = "current_episode"
        case playbackPosition = "playback_position"
        case duration
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        showId = try container.decode(String.self, forKey: .showId)
        title = (try? container.decode(String.self, forKey: .title)) ?? ""
        posterUrl = try container.decodeIfPresent(String.self, forKey: .posterUrl)
        backdropUrl = try container.decodeIfPresent(String.self, forKey: .backdropUrl)
        currentEpisode = try container.decodeIfPresent(MyTubeEpisode.self, forKey: .currentEpisode)

        if let p = try? container.decode(Double.self, forKey: .playbackPosition) {
            playbackPosition = p
        } else {
            playbackPosition = 0
        }

        if let d = try? container.decode(Double.self, forKey: .duration) {
            duration = d
        } else {
            duration = 0
        }
    }
}

struct MyTubeEpisode: Identifiable, Hashable, Codable, Sendable {

    var id: String { episodeId }

    let episodeId: String
    let showId: String
    let showName: String
    let seasonNumber: Int
    let episodeNumber: Int
    let title: String
    let overview: String?
    let duration: Double
    let thumbnailUrl: String?
    let jellyfinItemId: String
    var watched: Bool
    var playbackPosition: Double

    enum CodingKeys: String, CodingKey {
        case episodeId = "episode_id"
        case showId = "show_id"
        case showName = "show_name"
        case seasonNumber = "season_number"
        case episodeNumber = "episode_number"
        case title
        case overview
        case duration
        case thumbnailUrl = "thumbnail_url"
        case jellyfinItemId = "jellyfin_item_id"
        case watched
        case playbackPosition = "playback_position"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        episodeId = try container.decode(String.self, forKey: .episodeId)
        showId = (try? container.decode(String.self, forKey: .showId)) ?? ""
        showName = (try? container.decode(String.self, forKey: .showName)) ?? ""
        seasonNumber = (try? container.decode(Int.self, forKey: .seasonNumber)) ?? 1
        episodeNumber = (try? container.decode(Int.self, forKey: .episodeNumber)) ?? 1
        title = (try? container.decode(String.self, forKey: .title)) ?? "Untitled Episode"
        overview = try container.decodeIfPresent(String.self, forKey: .overview)

        if let d = try? container.decode(Double.self, forKey: .duration) {
            duration = d
        } else {
            duration = 0
        }

        thumbnailUrl = try container.decodeIfPresent(String.self, forKey: .thumbnailUrl)
        jellyfinItemId = (try? container.decode(String.self, forKey: .jellyfinItemId)) ?? ""

        if let b = try? container.decode(Bool.self, forKey: .watched) {
            watched = b
        } else if let i = try? container.decode(Int.self, forKey: .watched) {
            watched = (i != 0)
        } else {
            watched = false
        }

        if let p = try? container.decode(Double.self, forKey: .playbackPosition) {
            playbackPosition = p
        } else {
            playbackPosition = 0
        }
    }

    var asVideoItem: MyTubeVideo {
        MyTubeVideo(
            videoId: episodeId,
            channelId: showId,
            channelName: "\(showName) · S\(seasonNumber):E\(episodeNumber)",
            title: title,
            descriptionText: overview,
            uploadDate: nil,
            duration: duration,
            thumbnailUrl: thumbnailUrl,
            jellyfinItemId: jellyfinItemId,
            watched: watched,
            watchedAt: nil,
            playbackPosition: playbackPosition,
            channelThumbnailUrl: nil,
            mediaType: "episode"
        )
    }
}

// MARK: - Show Detail

struct MyTubeShowDetail: Codable, Sendable {

    let showId: String
    let title: String
    let overview: String?
    let posterUrl: String?
    let backdropUrl: String?
    let seasons: [MyTubeSeason]
    let nextEpisode: MyTubeEpisode?
    let totalEpisodes: Int

    enum CodingKeys: String, CodingKey {
        case showId = "show_id"
        case title
        case overview
        case posterUrl = "poster_url"
        case backdropUrl = "backdrop_url"
        case seasons
        case nextEpisode = "next_episode"
        case totalEpisodes = "total_episodes"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        showId = try container.decode(String.self, forKey: .showId)
        title = (try? container.decode(String.self, forKey: .title)) ?? ""
        overview = try container.decodeIfPresent(String.self, forKey: .overview)
        posterUrl = try container.decodeIfPresent(String.self, forKey: .posterUrl)
        backdropUrl = try container.decodeIfPresent(String.self, forKey: .backdropUrl)
        seasons = (try? container.decode([MyTubeSeason].self, forKey: .seasons)) ?? []
        nextEpisode = try container.decodeIfPresent(MyTubeEpisode.self, forKey: .nextEpisode)
        totalEpisodes = (try? container.decode(Int.self, forKey: .totalEpisodes)) ?? 0
    }
}

struct MyTubeSeason: Identifiable, Hashable, Codable, Sendable {

    var id: Int { seasonNumber }
    let seasonNumber: Int
    let seasonName: String
    let episodes: [MyTubeEpisode]

    enum CodingKeys: String, CodingKey {
        case seasonNumber = "season_number"
        case seasonName = "season_name"
        case episodes
    }
}

// MARK: - Trash Item

struct MyTubeTrashItem: Identifiable, Hashable, Codable, Sendable {

    var id: String { videoId }

    let videoId: String
    let channelId: String?
    let channelName: String?
    let title: String
    let uploadDate: String?
    let duration: Double
    let thumbnailUrl: String?
    let trashAt: String?
    let mediaType: String?
    let daysUntilDeletion: Int?

    enum CodingKeys: String, CodingKey {
        case videoId = "video_id"
        case channelId = "channel_id"
        case channelName = "channel_name"
        case title
        case uploadDate = "upload_date"
        case duration
        case thumbnailUrl = "thumbnail_url"
        case trashAt = "trash_at"
        case mediaType = "media_type"
        case daysUntilDeletion = "days_until_deletion"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        videoId = try container.decode(String.self, forKey: .videoId)
        channelId = try container.decodeIfPresent(String.self, forKey: .channelId)
        channelName = try container.decodeIfPresent(String.self, forKey: .channelName)
        title = (try? container.decode(String.self, forKey: .title)) ?? "Untitled Item"
        uploadDate = try container.decodeIfPresent(String.self, forKey: .uploadDate)

        if let d = try? container.decode(Double.self, forKey: .duration) {
            duration = d
        } else {
            duration = 0
        }

        thumbnailUrl = try container.decodeIfPresent(String.self, forKey: .thumbnailUrl)
        trashAt = try container.decodeIfPresent(String.self, forKey: .trashAt)
        mediaType = try container.decodeIfPresent(String.self, forKey: .mediaType)
        daysUntilDeletion = try container.decodeIfPresent(Int.self, forKey: .daysUntilDeletion)
    }
}

// MARK: - Notifications

extension Notification.Name {

    static let myTubeFeedNeedsRefresh = Notification.Name("myTubeFeedNeedsRefresh")
}
