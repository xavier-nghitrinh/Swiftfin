//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import Defaults
import Foundation
import SwiftUI

extension VideoPlayer.PlaybackControls {

    func startSpeedBoost(using speed: PlaybackSpeed? = nil) {
        guard mediaSession.canControlPlayback, !isSpeedBoosting, speedBoostTimer == nil else { return }

        viewState.setInteraction(.speedBoost, active: true)

        if let speed {
            applySpeedBoost(speed)
            return
        }

        speedBoostTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: false) { [self] _ in
            // This timer is scheduled on the main actor's run loop.
            MainActor.assumeIsolated {
                let multiplier = Defaults[.VideoPlayer.Gesture.longPressSpeedMultiplier]
                applySpeedBoost(multiplier)
            }
        }
    }

    private func applySpeedBoost(_ speed: PlaybackSpeed) {
        isSpeedBoosting = true
        viewState.originalPlaybackRate = mediaSession.rate
        mediaSession.rate = speed.rawValue
    }

    func stopSpeedBoost(performJump: Bool = false) {
        speedBoostTimer?.invalidate()
        speedBoostTimer = nil
        viewState.setInteraction(.speedBoost, active: false)

        if isSpeedBoosting {
            if let originalRate = viewState.originalPlaybackRate {
                mediaSession.rate = originalRate
            }

            viewState.originalPlaybackRate = nil
            isSpeedBoosting = false
            return
        }

        if performJump {
            jumpForward()
        }
    }

    func jumpForward(by interval: Duration? = nil) {
        let interval = interval ?? jumpForwardInterval.rawValue
        guard mediaSession.seek(by: interval) else { return }
        viewState.jumpProgressObserver.jumpForward()

        toaster.present(
            Text(
                interval * viewState.jumpProgressObserver.jumps,
                format: .minuteSecondsAbbreviated
            ),
            systemName: "goforward"
        )
    }

    func jumpBackward(by interval: Duration? = nil) {
        let interval = interval ?? jumpBackwardInterval.rawValue
        guard mediaSession.seek(by: .zero - interval) else { return }
        viewState.jumpProgressObserver.jumpBackward()

        toaster.present(
            Text(
                interval * viewState.jumpProgressObserver.jumps,
                format: .minuteSecondsAbbreviated
            ),
            systemName: "gobackward"
        )
    }
}
