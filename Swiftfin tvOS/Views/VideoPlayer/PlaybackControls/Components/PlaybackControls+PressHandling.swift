//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import SwiftUI

extension VideoPlayer.PlaybackControls {

    func handlePressEvent(_ press: VideoPlayer.UIContainerViewController.PressEvent) {
        if let isTrackpadTouchActive = press.trackpadTouchIsActive {
            if isTrackpadTouchActive {
                startSpeedBoost(using: .oneThreeQuarter)
            } else {
                stopSpeedBoost()
            }

            press.resolve(.handled)
            return
        }

        if let direction = press.trackpadSeekDirection {
            switch direction {
            case .backward:
                jumpBackward(by: .seconds(5))
            case .forward:
                jumpForward(by: .seconds(5))
            }

            press.resolve(.handled)
            return
        }

        let isSeekPress = press.type == .leftArrow || press.type == .rightArrow

        if isSeekPress, viewState.isOverlayActionFocused {
            press.resolve(.fallback)
            return
        }

        if viewState.presentation == .hidden, viewState.isPresentingOverlayActions {
            if isSeekPress {
                press.resolve(.fallback)
                return
            }

            press.resolve(.fallback)
            return
        }

        if press.phase == .began,
           isSeekPress,
           mediaSession.canSeek,
           !viewState.isPresentingSupplement,
           viewState.presentation == .hidden || viewState.presentation == .progress || viewState.isProgressBarFocused {
            seekingPress = press.type
        }

        // Retain ownership through ended/cancelled, even while the newly shown
        // slider is waiting for the focus engine to process our request.
        if seekingPress == press.type {
            viewState.refreshAutoDismiss()

            switch press.phase {
            case .began:
                if press.type == .rightArrow {
                    startSpeedBoost()
                }

            case .ended:
                if press.type == .rightArrow {
                    stopSpeedBoost(performJump: true)
                } else {
                    jumpBackward()
                }

                seekingPress = nil

            case .cancelled:
                stopSpeedBoost()
                seekingPress = nil

            default:
                break
            }

            press.resolve(.handled)
            return
        }

        viewState.refreshAutoDismiss()
        press.resolve(.fallback)
    }
}
