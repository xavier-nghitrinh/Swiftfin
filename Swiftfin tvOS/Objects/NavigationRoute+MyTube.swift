//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import SwiftUI

extension NavigationRoute {

    static func myTubeChannelDetail(channel: MyTubeChannel) -> NavigationRoute {
        NavigationRoute(id: "myTubeChannelDetail-\(channel.channelId)") {
            MyTubeChannelDetailView(channel: channel)
        }
    }

    static func myTubeShowDetail(show: MyTubeShow) -> NavigationRoute {
        NavigationRoute(id: "myTubeShowDetail-\(show.showId)") {
            MyTubeShowDetailView(show: show)
        }
    }

    static func myTubeMovieDetail(movie: MyTubeMovie, relatedMovies: [MyTubeMovie]) -> NavigationRoute {
        NavigationRoute(id: "myTubeMovieDetail-\(movie.movieId)") {
            MyTubeMovieDetailView(movie: movie, relatedMovies: relatedMovies)
        }
    }

    static var swiftfinHome: NavigationRoute {
        NavigationRoute(id: "swiftfinHome") {
            MainTabView()
        }
    }
}
