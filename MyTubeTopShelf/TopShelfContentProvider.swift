//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import Foundation
import TVServices

final class TopShelfContentProvider: TVTopShelfContentProvider {

    private struct Entry: Decodable {

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

    override func loadTopShelfContent(completionHandler: @escaping ((any TVTopShelfContent)?) -> Void) {
        guard let defaults = UserDefaults(suiteName: "group.org.jellyfin.swiftfin"),
              let data = defaults.data(forKey: "mytube.continue-watching"),
              let entries = try? JSONDecoder().decode([Entry].self, from: data),
              !entries.isEmpty else {
            completionHandler(nil)
            return
        }

        let items = entries.map { entry in
            let item = TVTopShelfSectionedItem(identifier: entry.id)
            item.title = entry.title
            item.imageShape = .hdtv
            item.playbackProgress = entry.playbackProgress
            item.setImageURL(entry.imageURL, for: [.screenScale1x, .screenScale2x])

            if let actionURL = playURL(for: entry) {
                item.playAction = TVTopShelfAction(url: actionURL)
            }

            return item
        }

        let section = TVTopShelfItemCollection(items: items)
        section.title = "Continue Watching"
        completionHandler(TVTopShelfSectionedContent(sections: [section]))
    }

    private func playURL(for entry: Entry) -> URL? {
        var components = URLComponents()
        components.scheme = "mytube"
        components.host = "play"
        components.queryItems = [
            URLQueryItem(name: "videoId", value: entry.id),
            URLQueryItem(name: "jellyfinItemId", value: entry.jellyfinItemId),
            URLQueryItem(name: "position", value: String(entry.position)),
            URLQueryItem(name: "duration", value: String(entry.duration))
        ]
        return components.url
    }
}
