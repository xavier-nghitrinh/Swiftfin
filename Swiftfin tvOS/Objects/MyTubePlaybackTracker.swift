//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import FactoryKit
import Foundation

@MainActor
final class MyTubePlaybackTracker {

    static let shared = MyTubePlaybackTracker()

    private var currentVideoId: String?
    private var currentDuration: Double = 0
    private var trackingTask: Task<Void, Never>?

    private init() {}

    func startTracking(videoId: String, duration: Double) {
        stopTracking()

        self.currentVideoId = videoId
        self.currentDuration = duration

        trackingTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 3_000_000_000)

                guard let self, let videoId = self.currentVideoId else { break }

                let manager = Container.shared.mediaPlayerManager()
                guard let session = manager.currentSession else {
                    self.finalizePlayback(videoId: videoId)
                    break
                }

                switch session.state {
                case .playback:
                    let pos = session.observedSeconds.seconds
                    let ticks = session.playbackItem?.baseItem.runTimeTicks ?? 0
                    let itemDuration = Double(ticks) / 10_000_000.0
                    let dur = self.currentDuration > 0 ? self.currentDuration : itemDuration

                    if dur > 0, pos > 0 {
                        await MyTubeClient.shared.reportProgress(
                            videoId: videoId,
                            position: pos,
                            duration: dur
                        )
                    }

                case .stopped:
                    let pos = session.observedSeconds.seconds
                    let ticks = session.playbackItem?.baseItem.runTimeTicks ?? 0
                    let itemDuration = Double(ticks) / 10_000_000.0
                    let dur = self.currentDuration > 0 ? self.currentDuration : itemDuration

                    if dur > 0, pos > 0 {
                        await MyTubeClient.shared.reportProgress(
                            videoId: videoId,
                            position: pos,
                            duration: dur
                        )
                    }

                    self.finalizePlayback(videoId: videoId)
                    return

                case .error:
                    self.stopTracking()
                    return

                default:
                    break
                }
            }
        }
    }

    private func finalizePlayback(videoId: String) {
        stopTracking()
        NotificationCenter.default.post(name: .myTubeFeedNeedsRefresh, object: nil)
    }

    func stopTracking() {
        trackingTask?.cancel()
        trackingTask = nil
        currentVideoId = nil
        currentDuration = 0
    }
}
