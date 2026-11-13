//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

// swiftlint:disable hard_coded_display_string

import Defaults
import FactoryKit
import JellyfinAPI
import SwiftUI

struct MyTubeRootView: View {

    @Binding
    private var pendingTopShelfURL: URL?

    @Injected(\.currentUserSession)
    private var userSession

    @PlayMedia
    private var playMedia

    enum MyTubeTab: String, CaseIterable, Identifiable {
        case subscriptions
        case channels
        case movies
        case shows
        case search
        case trash
        case swiftfin
        case settings

        var id: String { rawValue }
    }

    @Default(.Customization.tabBarPlacement)
    private var tabBarPlacement

    @State
    private var selectedTab: MyTubeTab = .subscriptions

    @State
    private var topShelfError: String?

    @State
    private var isRefreshingTopShelf = false

    init(pendingTopShelfURL: Binding<URL?>) {
        self._pendingTopShelfURL = pendingTopShelfURL
    }

    private func refreshTopShelf() async {
        guard !isRefreshingTopShelf else { return }
        guard let host = userSession?.server.effectiveServerURL.host else { return }

        var components = URLComponents()
        components.scheme = "http"
        components.host = host
        components.port = 8000
        guard let imageBaseURL = components.url else { return }

        isRefreshingTopShelf = true
        defer { isRefreshingTopShelf = false }

        do {
            let movies = try await MyTubeClient.shared.getMoviesHome()
            let shows = try await MyTubeClient.shared.getShowsHome()
            try MyTubeTopShelfCache.update(
                movies: movies,
                shows: shows,
                imageBaseURL: imageBaseURL
            )
        } catch {
            print("MyTube Top Shelf refresh failed: \(error.localizedDescription)")
        }
    }

    private func playTopShelfItem(from url: URL) {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let queryItems = components.queryItems,
              let videoId = queryItems.first(where: { $0.name == "videoId" })?.value,
              let jellyfinItemId = queryItems.first(where: { $0.name == "jellyfinItemId" })?.value,
              let positionString = queryItems.first(where: { $0.name == "position" })?.value,
              let position = Double(positionString),
              let durationString = queryItems.first(where: { $0.name == "duration" })?.value,
              let duration = Double(durationString) else {
            topShelfError = "The selected Continue Watching item is invalid."
            return
        }

        guard let userSession else {
            topShelfError = MyTubeError.noActiveServer.localizedDescription
            return
        }

        Task { @MainActor in
            do {
                let entry = try await userSession.getFullItem(id: jellyfinItemId)
                var configuration = MediaPlaybackConfiguration()
                if position > 0 {
                    configuration.startSeconds = .seconds(position)
                }

                let snapshot = entry.snapshot
                let itemDuration = Double(snapshot.runTimeTicks ?? 0) / 10_000_000.0
                MyTubePlaybackTracker.shared.startTracking(
                    videoId: videoId,
                    duration: duration > 0 ? duration : itemDuration
                )
                playMedia(intent: PlaybackIntent(item: snapshot, configuration: configuration))
            } catch {
                topShelfError = error.localizedDescription
            }
        }
    }

    @StateObject
    private var subscriptionsCoordinator = NavigationCoordinator()

    @StateObject
    private var channelsCoordinator = NavigationCoordinator()

    @StateObject
    private var moviesCoordinator = NavigationCoordinator()

    @StateObject
    private var showsCoordinator = NavigationCoordinator()

    @StateObject
    private var searchCoordinator = NavigationCoordinator()

    @StateObject
    private var trashCoordinator = NavigationCoordinator()

    @StateObject
    private var settingsCoordinator = NavigationCoordinator()

    @ContentBuilder
    private var tabViewContent: some View {
        TabView(selection: $selectedTab) {
            // 1. Subscriptions (Home Feed)
            SwiftUI.Tab(value: MyTubeTab.subscriptions) {
                NavigationInjectionView(coordinator: subscriptionsCoordinator) {
                    MyTubeFeedView()
                }
            } label: {
                Label("Subscriptions", systemImage: "play.rectangle.fill")
            }

            // 2. Channels
            SwiftUI.Tab(value: MyTubeTab.channels) {
                NavigationInjectionView(coordinator: channelsCoordinator) {
                    MyTubeChannelsView()
                }
            } label: {
                Label("Channels", systemImage: "person.2.fill")
            }

            // 3. Movies
            SwiftUI.Tab(value: MyTubeTab.movies) {
                NavigationInjectionView(coordinator: moviesCoordinator) {
                    MyTubeMoviesView()
                }
            } label: {
                Label("Movies", systemImage: "film.fill")
            }

            // 4. Shows
            SwiftUI.Tab(value: MyTubeTab.shows) {
                NavigationInjectionView(coordinator: showsCoordinator) {
                    MyTubeShowsView()
                }
            } label: {
                Label("Shows", systemImage: "tv.fill")
            }

            // 5. Search
            SwiftUI.Tab(value: MyTubeTab.search, role: .search) {
                NavigationInjectionView(coordinator: searchCoordinator) {
                    MyTubeSearchView()
                }
            } label: {
                Label("Search", systemImage: "magnifyingglass")
            }

            // 6. Trash
            SwiftUI.Tab(value: MyTubeTab.trash) {
                NavigationInjectionView(coordinator: trashCoordinator) {
                    MyTubeTrashView()
                }
            } label: {
                Label("Trash", systemImage: "trash.fill")
            }

            // 7. Swiftfin (Fallback to original Swiftfin home)
            SwiftUI.Tab(value: MyTubeTab.swiftfin) {
                MainTabView()
            } label: {
                Label("Swiftfin", systemImage: "square.grid.2x2")
            }

            // 8. Settings
            SwiftUI.Tab(value: MyTubeTab.settings) {
                NavigationInjectionView(coordinator: settingsCoordinator) {
                    SettingsView()
                }
            } label: {
                Label("Settings", systemImage: "gearshape")
            }
        }
    }

    var body: some View {
        Group {
            switch tabBarPlacement {
            case .sidebar:
                tabViewContent
                    .tabViewStyle(.sidebarAdaptable)
            case .tabBar:
                tabViewContent
                    .tabViewStyle(.tabBarOnly)
            }
        }
        .task {
            await refreshTopShelf()
            if let url = pendingTopShelfURL {
                pendingTopShelfURL = nil
                playTopShelfItem(from: url)
            }
        }
        .onChange(of: pendingTopShelfURL) { _, url in
            guard let url else { return }
            pendingTopShelfURL = nil
            playTopShelfItem(from: url)
        }
        .onReceive(NotificationCenter.default.publisher(for: .myTubeFeedNeedsRefresh)) { _ in
            Task { @MainActor in
                await refreshTopShelf()
            }
        }
        .alert("MyTube", isPresented: Binding(
            get: { topShelfError != nil },
            set: { if !$0 { topShelfError = nil } }
        )) {
            Button("OK", role: .cancel) {
                topShelfError = nil
            }
        } message: {
            Text(topShelfError ?? "")
        }
    }
}
