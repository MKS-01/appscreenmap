import SwiftUI

struct Article: Identifiable, Hashable {
    let id: Int
    let site: String
    let title: String
    let minutes: Int
}

let ARTICLES: [Article] = [
    Article(id: 1, site: "playground.dev", title: "Getting started with the Playground", minutes: 3),
    Article(id: 2, site: "notes.example", title: "Why every screen should have a title", minutes: 4),
    Article(id: 3, site: "design.example", title: "Touch targets: 44 pt is the floor", minutes: 5),
    Article(id: 4, site: "perf.example", title: "A slow screen is a bug, even when it works", minutes: 6),
    Article(id: 5, site: "a11y.example", title: "Label in name: say what you see", minutes: 2),
    Article(id: 6, site: "notes.example", title: "The long title that does not fit on a single line of a phone screen at all", minutes: 7),
    Article(id: 7, site: "design.example", title: "Consistent navigation, one bar everywhere", minutes: 3),
    Article(id: 8, site: "perf.example", title: "Frames, hitches and the 16 millisecond budget", minutes: 8),
    Article(id: 9, site: "playground.dev", title: "Forms that do not ask twice", minutes: 4),
    Article(id: 10, site: "a11y.example", title: "Dragging is optional, buttons are not", minutes: 3),
    Article(id: 11, site: "notes.example", title: "Orientation: let people turn their phone", minutes: 2),
    Article(id: 12, site: "playground.dev", title: "That's the end of the feed", minutes: 1),
]

struct HomeView: View {
    var body: some View {
        NavigationStack {
            List(ARTICLES) { a in
                NavigationLink(value: a) { ArticleCard(article: a) }
                    .accessibilityIdentifier("article_card")
            }
            .accessibilityIdentifier("feed")
            .navigationTitle("Discover")
            .navigationDestination(for: Article.self) { ArticleView(article: $0) }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink { HelpView() } label: { Image(systemName: "info.circle") }
                        .accessibilityLabel("Help")
                        .accessibilityIdentifier("help")
                }
            }
        }
    }
}

struct ArticleCard: View {
    let article: Article
    @State private var saved = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(article.site).font(.caption)
            // A11Y BUG (WCAG 1.4.4 Resize Text): one line, truncated; long titles lose content at large text sizes.
            Text(article.title).font(.headline).lineLimit(1)
            HStack(spacing: 6) {
                Text("\(article.minutes) min read").font(.footnote)
                Spacer()
                // A11Y BUG (WCAG 2.5.8 Target Size + 4.1.2 Name): 20 pt icons 6 pt apart; the bookmark has no label.
                Image(systemName: saved ? "heart.fill" : "heart")
                    .resizable().frame(width: 20, height: 18)
                    .onTapGesture { saved.toggle() }
                    .accessibilityAddTraits(.isButton)
                    .accessibilityIdentifier("bookmark")
                Image(systemName: "square.and.arrow.up")
                    .resizable().scaledToFit().frame(width: 20, height: 20)
                    .onTapGesture {}
                    .accessibilityLabel("Share")
                    .accessibilityAddTraits(.isButton)
                    .accessibilityIdentifier("share")
            }
        }
    }
}

struct ArticleView: View {
    let article: Article

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text(article.title).font(.title2).accessibilityIdentifier("article_title")
                Text("\(article.site) · \(article.minutes) min read").font(.caption)
                Rectangle().fill(Color(red: 0.89, green: 0.91, blue: 0.95)).frame(height: 160)
                // A11Y BUG (WCAG 1.4.3 Contrast): light grey caption on white.
                Text("Photo: Playground archive").font(.footnote).foregroundStyle(Color(white: 0.78))
                ForEach(1...3, id: \.self) { i in
                    Text("Paragraph \(i). This article is placeholder text so every article shares the same layout. The crawler should treat all article pages as one template with variants.")
                }
                // A11Y BUG (WCAG 2.5.3 Label in Name): shows "Listen" but is announced as "Play audio".
                Button("Listen") {}
                    .buttonStyle(.borderedProminent)
                    .accessibilityLabel("Play audio")
                    .accessibilityIdentifier("listen")
            }
            .padding()
        }
        .navigationTitle("Article")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct HelpView: View {
    var body: some View {
        List {
            NavigationLink("Contact support") { FeedbackView() }.accessibilityIdentifier("contact_support")
            Text("Answers to common questions live here.")
        }
        .navigationTitle("Help")
    }
}

struct FeedbackView: View {
    @State private var message = ""

    var body: some View {
        Form {
            // A11Y BUG (WCAG 3.3.2 Labels or Instructions): the message field has no label or hint.
            TextField("", text: $message, axis: .vertical).accessibilityIdentifier("message")
            Button("Submit") {}.accessibilityIdentifier("submit")
        }
        .navigationTitle("Feedback")
    }
}
