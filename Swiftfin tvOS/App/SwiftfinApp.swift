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

@main
struct SwiftfinApp: App {

    init() {
        Self.configure()

        UINavigationBar.appearance().titleTextAttributes = [.foregroundColor: UIColor.clear]
    }

    var body: some Scene {
        WindowGroup {
            ThemePreferencesEnvironment {
                OverlayToastView {
                    WithLocalUserAuthentication {
                        MyTubeAppRootView()
                    }
                }
            }
        }
    }
}

private struct MyTubeAppRootView: View {

    @StateObject
    private var rootCoordinator: RootCoordinator = .init()

    var body: some View {
        ZStack {
            switch rootCoordinator.state {
            case .initial:
                ProgressView()
            case .error:
                ErrorView(error: rootCoordinator.error ?? ErrorMessage(L10n.unknownError))
            case .ready:
                MyTubeUserSessionRootView()
            }
        }
        .animation(.linear(duration: 0.1), value: rootCoordinator.state)
        .task {
            rootCoordinator.start()
        }
    }
}

private struct MyTubeUserSessionRootView: View {

    @Environment(\.localUserAuthenticationAction)
    private var authenticationAction

    @InjectedObject(\.userSessionManager)
    private var userSessionManager

    @Default(.Customization.Poster.configuration)
    private var posterConfiguration

    @State
    private var pendingTopShelfURL: URL?

    var body: some View {
        ZStack {
            switch userSessionManager.state {
            case .initial:
                ProgressView()

            case .signedOut:
                NavigationInjectionView(coordinator: .init()) {
                    SelectUserView()
                }

            case .signedIn:
                MyTubeRootView(pendingTopShelfURL: $pendingTopShelfURL)
                    .environment(\.posterConfiguration, posterConfiguration)
                    .id(userSessionManager.currentSession.map(ObjectIdentifier.init))
            }
        }
        .animation(.linear(duration: 0.1), value: userSessionManager.state)
        .task {
            await userSessionManager.start()
        }
        .onOpenURL { url in
            if url.scheme == "mytube", url.host == "play" {
                pendingTopShelfURL = url
                return
            }

            guard let authenticationAction else { return }

            Task {
                await userSessionManager.handleOpenURL(
                    url,
                    authenticationAction: authenticationAction
                )
            }
        }
    }
}

