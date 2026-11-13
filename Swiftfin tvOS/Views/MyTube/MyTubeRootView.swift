//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import Defaults
import FactoryKit
import SwiftUI

struct MyTubeRootView: View {

    enum Tab: String, CaseIterable, Identifiable {
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
    private var selectedTab: Tab = .subscriptions

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
            Tab(value: Tab.subscriptions) {
                NavigationInjectionView(coordinator: subscriptionsCoordinator) {
                    MyTubeFeedView()
                }
            } label: {
                Label("Subscriptions", systemImage: "play.rectangle.fill")
            }

            // 2. Channels
            Tab(value: Tab.channels) {
                NavigationInjectionView(coordinator: channelsCoordinator) {
                    MyTubeChannelsView()
                }
            } label: {
                Label("Channels", systemImage: "person.2.fill")
            }

            // 3. Movies
            Tab(value: Tab.movies) {
                NavigationInjectionView(coordinator: moviesCoordinator) {
                    MyTubeMoviesView()
                }
            } label: {
                Label("Movies", systemImage: "film.fill")
            }

            // 4. Shows
            Tab(value: Tab.shows) {
                NavigationInjectionView(coordinator: showsCoordinator) {
                    MyTubeShowsView()
                }
            } label: {
                Label("Shows", systemImage: "tv.fill")
            }

            // 5. Search
            Tab(value: Tab.search, role: .search) {
                NavigationInjectionView(coordinator: searchCoordinator) {
                    MyTubeSearchView()
                }
            } label: {
                Label("Search", systemImage: "magnifyingglass")
            }

            // 6. Trash
            Tab(value: Tab.trash) {
                NavigationInjectionView(coordinator: trashCoordinator) {
                    MyTubeTrashView()
                }
            } label: {
                Label("Trash", systemImage: "trash.fill")
            }

            // 7. Swiftfin (Fallback to original Swiftfin home)
            Tab(value: Tab.swiftfin) {
                MainTabView()
            } label: {
                Label("Swiftfin", systemImage: "square.grid.2x2")
            }

            // 8. Settings
            Tab(value: Tab.settings) {
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
    }
}
