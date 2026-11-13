//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

import FactoryKit
import SwiftUI

struct MyTubeTrashView: View {

    @State
    private var items: [MyTubeTrashItem] = []

    @State
    private var isLoading = false

    @State
    private var errorMessage: String?

    private func loadTrash() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil

        do {
            items = try await MyTubeClient.shared.getTrash()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    private func restoreItem(_ item: MyTubeTrashItem) {
        Task { @MainActor in
            do {
                try await MyTubeClient.shared.restoreFromTrash(videoId: item.videoId)
                items.removeAll(where: { $0.videoId == item.videoId })
                NotificationCenter.default.post(name: .myTubeFeedNeedsRefresh, object: nil)
            } catch {
                print("Failed to restore item: \(error)")
            }
        }
    }

    private func deletePermanently(_ item: MyTubeTrashItem) {
        Task { @MainActor in
            do {
                try await MyTubeClient.shared.deletePermanently(videoId: item.videoId)
                items.removeAll(where: { $0.videoId == item.videoId })
            } catch {
                print("Failed to permanently delete item: \(error)")
            }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Trash")
                        .font(.title2)
                        .fontWeight(.bold)
                    Text("Items are retained for 30 days before permanent deletion from storage.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 50)
                .padding(.top, 20)

                if let errorMessage {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 40))
                            .foregroundStyle(.yellow)
                        Text(errorMessage)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                        Button("Retry") {
                            Task { await loadTrash() }
                        }
                        .buttonStyle(.bordered)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 60)
                }

                if isLoading {
                    HStack {
                        Spacer()
                        ProgressView().scaleEffect(1.2)
                        Spacer()
                    }
                    .padding(.vertical, 60)
                } else if items.isEmpty, errorMessage == nil {
                    VStack(spacing: 12) {
                        Image(systemName: "trash.slash")
                            .font(.system(size: 50))
                            .foregroundStyle(.secondary)
                        Text("Trash is empty")
                            .font(.headline)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 80)
                } else {
                    VStack(spacing: 20) {
                        ForEach(items) { item in
                            TrashRowView(
                                item: item,
                                onRestore: { restoreItem(item) },
                                onDeletePermanently: { deletePermanently(item) }
                            )
                        }
                    }
                    .padding(.horizontal, 50)
                }
            }
            .padding(.bottom, 60)
        }
        .task {
            if items.isEmpty {
                await loadTrash()
            }
        }
    }
}

private struct TrashRowView: View {

    @Injected(\.currentUserSession)
    private var userSession

    let item: MyTubeTrashItem
    let onRestore: () -> Void
    let onDeletePermanently: () -> Void

    @State
    private var showDeleteAlert = false

    private var imageURL: URL? {
        guard let thumb = item.thumbnailUrl, !thumb.isEmpty else { return nil }
        if thumb.starts(with: "http://") || thumb.starts(with: "https://") {
            return URL(string: thumb)
        }
        if let host = userSession?.server.effectiveServerURL.host {
            let path = thumb.starts(with: "/") ? thumb : "/" + thumb
            return URL(string: "http://\(host):8000\(path)")
        }
        return nil
    }

    var body: some View {
        HStack(spacing: 24) {
            // Thumbnail
            ZStack {
                if let imageURL {
                    AsyncImage(url: imageURL) { phase in
                        switch phase {
                        case let .success(img):
                            img.resizable().scaledToFill()
                        default:
                            Color(white: 0.2)
                        }
                    }
                } else {
                    Color(white: 0.2)
                }
            }
            .frame(width: 200, height: 112)
            .cornerRadius(8)
            .clipped()

            // Metadata
            VStack(alignment: .leading, spacing: 6) {
                Text(item.title)
                    .font(.headline)
                    .lineLimit(2)

                HStack(spacing: 12) {
                    if let ch = item.channelName {
                        Text(ch)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }

                    if let days = item.daysUntilDeletion {
                        Text("• Deletes in \(days) days")
                            .font(.callout)
                            .foregroundStyle(.red)
                    }
                }
            }

            Spacer()

            // Actions
            HStack(spacing: 16) {
                Button {
                    onRestore()
                } label: {
                    Label("Restore", systemImage: "arrow.uturn.backward")
                }
                .buttonStyle(.bordered)

                Button(role: .destructive) {
                    showDeleteAlert = true
                } label: {
                    Label("Delete Now", systemImage: "trash")
                }
                .buttonStyle(.bordered)
                .tint(.red)
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.05))
        .cornerRadius(12)
        .alert("Permanently Delete?", isPresented: $showDeleteAlert) {
            Button("Delete Immediately", role: .destructive) {
                onDeletePermanently()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This will permanently delete the media file from your storage. This cannot be undone.")
        }
    }
}
