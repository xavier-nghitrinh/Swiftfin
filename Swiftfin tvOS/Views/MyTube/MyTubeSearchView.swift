//
// Swiftfin is subject to the terms of the Mozilla Public
// License, v2.0. If a copy of the MPL was not distributed with this
// file, you can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Jellyfin & Jellyfin Contributors
//

// swiftlint:disable hard_coded_display_string

import SwiftUI

struct MyTubeSearchView: View {

    @State
    private var searchQuery: String = ""

    @State
    private var results: [MyTubeVideo] = []

    @State
    private var isLoading = false

    private let columns = MyTubeTileMetrics.gridColumns

    private func performSearch(query: String) async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            results = []
            return
        }

        isLoading = true
        do {
            results = try await MyTubeClient.shared.search(query: trimmed)
        } catch {
            print("Search error: \(error)")
        }
        isLoading = false
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                Text("Search MyTube")
                    .font(.title2)
                    .fontWeight(.bold)
                    .padding(.horizontal, 50)
                    .padding(.top, 20)

                if isLoading {
                    HStack {
                        Spacer()
                        ProgressView().scaleEffect(1.2)
                        Spacer()
                    }
                    .padding(.vertical, 60)
                } else if !searchQuery.isEmpty, results.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 40))
                            .foregroundStyle(.secondary)
                        Text("No results for \"\(searchQuery)\"")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 60)
                } else {
                    LazyVGrid(columns: columns, spacing: 40) {
                        ForEach(results) { vid in
                            MyTubeVideoCard(video: vid)
                        }
                    }
                    .padding(.horizontal, 50)
                    .focusEffectDisabled()
                }
            }
            .padding(.bottom, 60)
        }
        .searchable(text: $searchQuery, prompt: "Search videos, movies, shows, or channels")
        .onChange(of: searchQuery) { _, newValue in
            Task {
                try? await Task.sleep(nanoseconds: 300_000_000)
                if newValue == searchQuery {
                    await performSearch(query: newValue)
                }
            }
        }
    }
}
