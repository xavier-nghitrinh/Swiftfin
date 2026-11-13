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
    var aspectRatio: CGFloat = MyTubeTileMetrics.aspectRatio

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
        GeometryReader { geometry in
            ZStack(alignment: .bottom) {
                imageContent
                    .frame(width: geometry.size.width, height: geometry.size.height)
                    .clipped()
                    .background(Color.black.opacity(0.4))

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
                    VStack {
                        Spacer()
                        ZStack(alignment: .leading) {
                            Rectangle()
                                .fill(Color.white.opacity(0.3))
                                .frame(height: 5)

                            Rectangle()
                                .fill(Color.red)
                                .frame(width: geometry.size.width * video.progressFraction, height: 5)
                        }
                    }
                }
            }
        }
        .aspectRatio(aspectRatio, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: MyTubeTileMetrics.cornerRadius))
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

struct MyTubeDetailHeader<Actions: View>: View {

    let title: String
    let placeholderSystemName: String
    let posterPath: String?
    let backdropPath: String?
    let rating: Double?
    let metadata: [String]
    let genres: [String]
    let overview: String?
    private let actions: Actions

    init(
        title: String,
        placeholderSystemName: String,
        posterPath: String?,
        backdropPath: String?,
        rating: Double?,
        metadata: [String],
        genres: [String],
        overview: String?,
        @ViewBuilder actions: () -> Actions
    ) {
        self.title = title
        self.placeholderSystemName = placeholderSystemName
        self.posterPath = posterPath
        self.backdropPath = backdropPath
        self.rating = rating
        self.metadata = metadata
        self.genres = genres
        self.overview = overview
        self.actions = actions()
    }

    var body: some View {
        HStack(alignment: .bottom, spacing: 32) {
            MyTubeArtworkView(imagePath: posterPath, placeholderSystemName: placeholderSystemName)
                .frame(width: 220, height: 330)
                .clipShape(RoundedRectangle(cornerRadius: 10))

            VStack(alignment: .leading, spacing: 18) {
                Text(title)
                    .font(.largeTitle.bold())
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 10) {
                    if let rating {
                        Label {
                            Text(rating, format: .number.precision(.fractionLength(1)))
                        } icon: {
                            Image(systemName: "star.fill")
                                .foregroundStyle(.yellow)
                        }
                    }

                    ForEach(Array(metadata.enumerated()), id: \.offset) { _, value in
                        Text(value)
                    }

                    ForEach(genres, id: \.self) { genre in
                        Text(genre)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(.white.opacity(0.14), in: Capsule())
                    }
                }
                .font(.callout)
                .foregroundStyle(.white.opacity(0.92))

                if let overview, !overview.isEmpty {
                    Text(overview)
                        .font(.callout)
                        .lineSpacing(5)
                        .foregroundStyle(.white.opacity(0.9))
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(spacing: 16) {
                    actions
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 50)
        .padding(.vertical, 40)
        .frame(maxWidth: .infinity, minHeight: 540, alignment: .bottomLeading)
        .background {
            GeometryReader { geometry in
                MyTubeArtworkView(imagePath: backdropPath, placeholderSystemName: placeholderSystemName)
                    .frame(width: geometry.size.width, height: geometry.size.height)
                    .overlay(Color.black.opacity(0.42))
                    .overlay {
                        LinearGradient(
                            colors: [.black.opacity(0.15), .black.opacity(0.78)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
