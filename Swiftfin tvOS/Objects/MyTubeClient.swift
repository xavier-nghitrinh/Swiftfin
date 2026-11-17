//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import FactoryKit
import Foundation

enum MyTubeError: LocalizedError {

    case noActiveServer
    case noActiveUser
    case userNotResolved
    case invalidURL
    case serverError(Int, String)

    var errorDescription: String? {
        switch self {
        case .noActiveServer:
            return "No active Jellyfin server connection found"
        case .noActiveUser:
            return "No active Swiftfin user found"
        case .userNotResolved:
            return "MyTube user is still loading"
        case .invalidURL:
            return "Invalid MyTube server URL"
        case let .serverError(code, message):
            return "MyTube server error (\(code)): \(message)"
        }
    }
}

@MainActor
final class MyTubeClient {

    static let shared = MyTubeClient()

    private let session: URLSession

    private(set) var userId: String?

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        self.session = URLSession(configuration: config)
    }

    // MARK: - User

    /// Resolves the MyTube user for the logged-in Swiftfin user and stores its id for scoped requests.
    func resolveCurrentUser() async throws -> String {
        userId = nil

        guard let username = Container.shared.currentUserSession()?.user.username, !username.isEmpty else {
            throw MyTubeError.noActiveUser
        }

        let base = try baseURL()
        var request = URLRequest(url: base.appendingPathComponent("users").appendingPathComponent("ensure"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["name": username])

        let data = try await execute(request)
        let user = try JSONDecoder().decode(MyTubeUser.self, from: data)
        userId = user.userId
        return user.userId
    }

    private func baseURL() throws -> URL {
        guard let userSession = Container.shared.currentUserSession(),
              let host = userSession.server.effectiveServerURL.host else {
            throw MyTubeError.noActiveServer
        }

        // Port 8000 is default for MyTube backend on the same server as Jellyfin
        guard let url = URL(string: "http://\(host):8000/api") else {
            throw MyTubeError.invalidURL
        }

        return url
    }

    // MARK: - GET Requests

    func getGoneSoon(
        unplayedOnly: Bool = true,
        limit: Int = 20,
        offset: Int = 0
    ) async throws -> MyTubeFeedResponse {
        let base = try baseURL()
        var components = URLComponents(url: base.appendingPathComponent("gone-soon"), resolvingAgainstBaseURL: true)
        components?.queryItems = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "unplayed_only", value: unplayedOnly ? "true" : "false")
        ]

        guard let url = components?.url else { throw MyTubeError.invalidURL }
        return try await fetch(url)
    }

    func getContinueWatching(
        limit: Int = 50,
        offset: Int = 0
    ) async throws -> MyTubeFeedResponse {
        let base = try baseURL()
        var components = URLComponents(url: base.appendingPathComponent("continue-watching"), resolvingAgainstBaseURL: true)
        components?.queryItems = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset))
        ]

        guard let url = components?.url else { throw MyTubeError.invalidURL }
        return try await fetch(url)
    }

    func getHomeFeed(
        unplayedOnly: Bool = true,
        limit: Int = 50,
        offset: Int = 0
    ) async throws -> MyTubeFeedResponse {
        let base = try baseURL()
        var components = URLComponents(url: base.appendingPathComponent("home"), resolvingAgainstBaseURL: true)
        components?.queryItems = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "unplayed_only", value: unplayedOnly ? "true" : "false")
        ]

        guard let url = components?.url else { throw MyTubeError.invalidURL }
        return try await fetch(url)
    }

    func getChannels(subscription: MyTubeChannelSubscriptionFilter = .all) async throws -> [MyTubeChannel] {
        let base = try baseURL()
        var components = URLComponents(url: base.appendingPathComponent("channels"), resolvingAgainstBaseURL: true)
        components?.queryItems = [
            URLQueryItem(name: "subscription", value: subscription.rawValue)
        ]

        guard let url = components?.url else { throw MyTubeError.invalidURL }
        return try await fetch(url)
    }

    func getChannelDetail(channelId: String) async throws -> MyTubeChannel {
        let base = try baseURL()
        let url = base.appendingPathComponent("channels").appendingPathComponent(channelId)
        return try await fetch(url)
    }

    func getChannelVideos(
        channelId: String,
        filter: String = "all",
        limit: Int = 50,
        offset: Int = 0
    ) async throws -> MyTubeFeedResponse {
        let base = try baseURL()
        let pathURL = base.appendingPathComponent("channels").appendingPathComponent(channelId).appendingPathComponent("videos")
        var components = URLComponents(url: pathURL, resolvingAgainstBaseURL: true)
        components?.queryItems = [
            URLQueryItem(name: "filter_type", value: filter),
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset))
        ]

        guard let url = components?.url else { throw MyTubeError.invalidURL }
        return try await fetch(url)
    }

    func getMoviesHome() async throws -> MyTubeMoviesHome {
        let base = try baseURL()
        let url = base.appendingPathComponent("movies").appendingPathComponent("home")
        return try await fetch(url)
    }

    func getMovieDetail(movieId: String) async throws -> MyTubeMovie {
        let base = try baseURL()
        let url = base.appendingPathComponent("movies").appendingPathComponent(movieId)
        return try await fetch(url)
    }

    func getShowsHome() async throws -> MyTubeShowsHome {
        let base = try baseURL()
        let url = base.appendingPathComponent("shows").appendingPathComponent("home")
        return try await fetch(url)
    }

    func getShowDetail(showId: String) async throws -> MyTubeShowDetail {
        let base = try baseURL()
        let url = base.appendingPathComponent("shows").appendingPathComponent(showId)
        return try await fetch(url)
    }

    func search(query: String) async throws -> [MyTubeVideo] {
        let base = try baseURL()
        var components = URLComponents(url: base.appendingPathComponent("search"), resolvingAgainstBaseURL: true)
        components?.queryItems = [
            URLQueryItem(name: "q", value: query)
        ]

        guard let url = components?.url else { throw MyTubeError.invalidURL }
        return try await fetch(url)
    }

    // MARK: - Actions (POST / DELETE)

    func reportProgress(videoId: String, position: Double, duration: Double) async {
        do {
            let base = try baseURL()
            let url = base.appendingPathComponent("videos").appendingPathComponent(videoId).appendingPathComponent("progress")

            var request = try scopedRequest(url, method: "POST")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")

            let payload: [String: Double] = [
                "position": position,
                "duration": duration
            ]
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)

            _ = try await session.data(for: request)
        } catch {
            // Non-fatal progress reporting error
            print("MyTube reportProgress error: \(error.localizedDescription)")
        }
    }

    func markWatched(videoId: String) async throws {
        let base = try baseURL()
        let url = base.appendingPathComponent("videos").appendingPathComponent(videoId).appendingPathComponent("watched")
        let request = try scopedRequest(url, method: "POST")
        _ = try await execute(request)
    }

    func markUnwatched(videoId: String) async throws {
        let base = try baseURL()
        let url = base.appendingPathComponent("videos").appendingPathComponent(videoId).appendingPathComponent("unwatched")
        let request = try scopedRequest(url, method: "POST")
        _ = try await execute(request)
    }

    func setChannelSubscription(channelId: String, subscribed: Bool) async throws {
        let base = try baseURL()
        let url = base.appendingPathComponent("channels").appendingPathComponent(channelId).appendingPathComponent("subscription")
        var request = try scopedRequest(url, method: "PUT")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["subscribed": subscribed])
        _ = try await execute(request)
    }

    func deletePermanently(videoId: String) async throws {
        let base = try baseURL()
        let url = base.appendingPathComponent("videos").appendingPathComponent(videoId)
        let request = try scopedRequest(url, method: "DELETE")
        _ = try await execute(request)
    }

    func triggerScan() async throws {
        let base = try baseURL()
        let url = base.appendingPathComponent("admin").appendingPathComponent("scan")
        let request = try scopedRequest(url, method: "POST")
        _ = try await execute(request)
    }

    // MARK: - Helpers

    private func scopedRequest(_ url: URL, method: String = "GET") throws -> URLRequest {
        guard let userId else { throw MyTubeError.userNotResolved }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue(userId, forHTTPHeaderField: "X-MyTube-User")
        return request
    }

    private func fetch<T: Decodable>(_ url: URL) async throws -> T {
        let request = try scopedRequest(url)
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw MyTubeError.serverError(-1, "Invalid response")
        }

        guard 200 ..< 300 ~= httpResponse.statusCode else {
            let message = String(data: data, encoding: .utf8) ?? "HTTP \(httpResponse.statusCode)"
            throw MyTubeError.serverError(httpResponse.statusCode, message)
        }

        let decoder = JSONDecoder()
        return try decoder.decode(T.self, from: data)
    }

    private func execute(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw MyTubeError.serverError(-1, "Invalid response")
        }

        guard 200 ..< 300 ~= httpResponse.statusCode else {
            let message = String(data: data, encoding: .utf8) ?? "HTTP \(httpResponse.statusCode)"
            throw MyTubeError.serverError(httpResponse.statusCode, message)
        }

        return data
    }
}
