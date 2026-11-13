//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

// swiftlint:disable hard_coded_display_string

import FactoryKit
import SwiftUI

struct MyTubeThumbnailView: View {

    @Injected(\.currentUserSession)
    private var userSession

    let video: MyTubeVideo
    var aspectRatio: CGFloat = 16.0 / 9.0

    @State
    private var base64Image: UIImage?

    private var imageURL: URL? {
        guard let urlStr = video.thumbnailUrl, !urlStr.isEmpty else { return nil }

        if urlStr.starts(with: "http://") || urlStr.starts(with: "https://") {
            return URL(string: urlStr)
        }

        if let host = userSession?.server.effectiveServerURL.host {
            let path = urlStr.starts(with: "/") ? urlStr : "/" + urlStr
            return URL(string: "http://\(host):8000\(path)")
        }

        return nil
    }

    private func decodeBase64IfPresent() {
        guard let thumb = video.thumbnailUrl, thumb.starts(with: "data:image/") else { return }
        guard let commaIndex = thumb.firstIndex(of: ",") else { return }

        let b64 = String(thumb[thumb.index(after: commaIndex)...])
        if let data = Data(base64Encoded: b64, options: .ignoreUnknownCharacters) {
            base64Image = UIImage(data: data)
        }
    }

    @ContentBuilder
    private var imageContent: some View {
        if let base64Image {
            Image(uiImage: base64Image)
                .resizable()
                .scaledToFill()
        } else if let imageURL {
            AsyncImage(url: imageURL) { phase in
                switch phase {
                case let .success(img):
                    img.resizable().scaledToFill()
                case .failure:
                    placeholderView
                case .empty:
                    ZStack {
                        Color.black.opacity(0.3)
                        ProgressView()
                    }
                @unknown default:
                    placeholderView
                }
            }
        } else {
            placeholderView
        }
    }

    @ContentBuilder
    private var placeholderView: some View {
        ZStack {
            Color(white: 0.15)

            Image(systemName: video.mediaType == "movie" ? "film" : (video.mediaType == "show" ? "tv" : "play.rectangle.fill"))
                .font(.system(size: 40))
                .foregroundStyle(Color.red.opacity(0.8))
        }
    }

    var body: some View {
        ZStack(alignment: .bottom) {
            imageContent
                .aspectRatio(aspectRatio, contentMode: .fit)
                .clipped()
                .background(Color.black.opacity(0.4))
                .cornerRadius(12)

            if !video.formattedDuration.isEmpty {
                HStack {
                    Spacer()
                    Text(video.formattedDuration)
                        .font(.caption2)
                        .fontWeight(.semibold)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(Color.black.opacity(0.75))
                        .cornerRadius(6)
                        .padding(8)
                }
            }

            if video.watched {
                VStack {
                    HStack {
                        Spacer()
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark")
                                .font(.system(size: 10, weight: .bold))
                            Text("WATCHED")
                                .font(.system(size: 9, weight: .bold))
                        }
                        .foregroundStyle(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(Color.red.opacity(0.9))
                        .cornerRadius(4)
                        .padding(8)
                    }
                    Spacer()
                }
            }

            if video.isPartiallyWatched {
                GeometryReader { geo in
                    VStack {
                        Spacer()
                        ZStack(alignment: .leading) {
                            Rectangle()
                                .fill(Color.white.opacity(0.3))
                                .frame(height: 5)

                            Rectangle()
                                .fill(Color.red)
                                .frame(width: geo.size.width * video.progressFraction, height: 5)
                        }
                    }
                }
                .frame(height: 5)
                .cornerRadius(2.5)
            }
        }
        .onAppear(perform: decodeBase64IfPresent)
    }
}

struct MyTubeArtworkView: View {

    @Injected(\.currentUserSession)
    private var userSession

    let imagePath: String?
    let placeholderSystemName: String

    @State
    private var base64Image: UIImage?

    private var imageURL: URL? {
        guard let imagePath, !imagePath.isEmpty,
              !imagePath.starts(with: "data:image/") else { return nil }

        if imagePath.starts(with: "http://") || imagePath.starts(with: "https://") {
            return URL(string: imagePath)
        }

        guard let host = userSession?.server.effectiveServerURL.host else { return nil }
        let path = imagePath.starts(with: "/") ? imagePath : "/" + imagePath
        return URL(string: "http://\(host):8000\(path)")
    }

    private func decodeBase64IfPresent() {
        guard let imagePath, imagePath.starts(with: "data:image/"),
              let commaIndex = imagePath.firstIndex(of: ",") else { return }

        let encodedImage = String(imagePath[imagePath.index(after: commaIndex)...])
        guard let data = Data(base64Encoded: encodedImage, options: .ignoreUnknownCharacters) else { return }
        base64Image = UIImage(data: data)
    }

    var body: some View {
        GeometryReader { geometry in
            Group {
                if let base64Image {
                    Image(uiImage: base64Image)
                        .resizable()
                        .scaledToFill()
                } else if let imageURL {
                    AsyncImage(url: imageURL) { phase in
                        switch phase {
                        case let .success(image):
                            image.resizable().scaledToFill()
                        case .empty:
                            ZStack {
                                Color(white: 0.15)
                                ProgressView()
                            }
                        default:
                            placeholder
                        }
                    }
                } else {
                    placeholder
                }
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
            .clipped()
        }
        .onAppear(perform: decodeBase64IfPresent)
    }

    private var placeholder: some View {
        ZStack {
            Color(white: 0.15)
            Image(systemName: placeholderSystemName)
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
        }
    }
}
