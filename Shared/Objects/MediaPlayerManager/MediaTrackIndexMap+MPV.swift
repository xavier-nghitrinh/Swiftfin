//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import Foundation
import JellyfinAPI
import MPVUI

extension MediaTrackIndexMap {

    /// FFmpeg indexes match the original representation when using libavformat, while other
    /// demuxers (such as mpv's native MKV demuxer) may use different numbering or omit `ff-index`.
    /// Transcodes are mapped only to the requested audio stream.
    static func mpv(
        mediaStreams: [MediaStream],
        tracks: [MPVMediaTrack],
        isTranscoding: Bool,
        selectedAudioStreamIndex: Int?
    ) -> MediaTrackIndexMap {
        var map = MediaTrackIndexMap()

        for (streamType, trackType) in [(MediaStreamType.audio, MPVTrackType.audio), (.subtitle, .subtitle)] {
            let embeddedStreams = mediaStreams
                .filter { $0.type == streamType && $0.isExternal != true }
                .sorted { ($0.index ?? Int.max) < ($1.index ?? Int.max) }
            let streams = embeddedStreams.filter { !$0.isSidecarSubtitle }
            let internalTracks = tracks
                .filter { $0.type == trackType && !$0.isExternal }
                .sorted { $0.mpvID < $1.mpvID }

            if isTranscoding {
                if streamType == .audio, let index = selectedAudioStreamIndex, let track = internalTracks.first {
                    map.setPlayerIndex(track.mpvID, for: index)
                }

                continue
            }

            var unmatchedStreams = streams
            var remaining = internalTracks

            // Pass 1: Exact `sourceStreamIndex` match only when all reported source indices fall
            // within Jellyfin's embedded stream index set for this type (avoiding shifted-index collisions).
            let embeddedIndices = Set(embeddedStreams.compactMap(\.index))
            let reportedSourceIndices = Set(internalTracks.compactMap(\.sourceStreamIndex))

            if !reportedSourceIndices.isEmpty, reportedSourceIndices.isSubset(of: embeddedIndices) {
                var nextUnmatched: [MediaStream] = []

                for stream in unmatchedStreams {
                    guard let index = stream.index else { continue }

                    let exact = remaining.filter { $0.sourceStreamIndex == index }
                    if exact.count == 1, let track = exact.first {
                        map.setPlayerIndex(track.mpvID, for: index)
                        remaining.removeAll { $0.id == track.id }
                    } else {
                        nextUnmatched.append(stream)
                    }
                }

                unmatchedStreams = nextUnmatched
            }

            // Pass 2: Unique metadata match across codec, normalized language, title, and dispositions.
            if !unmatchedStreams.isEmpty, !remaining.isEmpty {
                var nextUnmatched: [MediaStream] = []

                for stream in unmatchedStreams {
                    guard let index = stream.index else { continue }

                    let matches = remaining.filter { isMetadataCompatible(stream: stream, track: $0) }

                    if matches.count == 1, let track = matches.first {
                        map.setPlayerIndex(track.mpvID, for: index)
                        remaining.removeAll { $0.id == track.id }
                    } else {
                        nextUnmatched.append(stream)
                    }
                }

                unmatchedStreams = nextUnmatched
            }

            // Pass 3: Container-order fallback for tracks sharing metadata (e.g. main + commentary).
            if !unmatchedStreams.isEmpty, !remaining.isEmpty {
                if unmatchedStreams.count == remaining.count {
                    for (stream, track) in zip(unmatchedStreams, remaining) {
                        guard let index = stream.index else { continue }
                        map.setPlayerIndex(track.mpvID, for: index)
                    }
                } else {
                    for stream in unmatchedStreams {
                        guard let index = stream.index else { continue }

                        if let position = remaining.firstIndex(where: { isMetadataCompatible(stream: stream, track: $0) }) {
                            let track = remaining.remove(at: position)
                            map.setPlayerIndex(track.mpvID, for: index)
                        }
                    }
                }
            }
        }

        for stream in mediaStreams.sidecarSubtitles {
            if let index = stream.index,
               let track = tracks
                .first(where: { $0.type == .subtitle && $0.isExternal && $0.clientID == MPVTrackIdentity.subtitleID(index) }) {
                map.setPlayerIndex(track.mpvID, for: index)
            }
        }

        return map
    }

    private static func isMetadataCompatible(stream: MediaStream, track: MPVMediaTrack) -> Bool {
        if let codec = stream.codec,
           let native = track.codec,
           MPVTrackIdentity.codecName(codec) != MPVTrackIdentity.codecName(native) {
            return false
        }

        if let language = normalizedLanguage(stream.language),
           let native = normalizedLanguage(track.language),
           language != native {
            return false
        }

        if let title = normalizedTitle(stream.title),
           let native = normalizedTitle(track.title),
           title != native {
            return false
        }

        if stream.isHearingImpaired == true && !track.isHearingImpaired {
            return false
        }

        return true
    }

    private static func normalizedLanguage(_ language: String?) -> String? {
        guard let trimmed = language?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else {
            return nil
        }

        let canonical = Locale.canonicalLanguageIdentifier(from: trimmed)
        guard let code = Locale.Language(identifier: canonical).languageCode,
              code.identifier != "und",
              code.identifier != "zxx"
        else {
            return nil
        }

        return code.identifier(.alpha2) ?? code.identifier(.alpha3)
    }

    private static func normalizedTitle(_ title: String?) -> String? {
        guard let trimmed = title?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else {
            return nil
        }

        return trimmed.lowercased()
    }
}
