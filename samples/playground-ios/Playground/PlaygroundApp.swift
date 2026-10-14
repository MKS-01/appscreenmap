import SwiftUI

/// AppScreenMap Playground (iOS): the same scenarios as the Android app, v1 only, first slice.
/// Deliberate accessibility bugs are marked `A11Y BUG (WCAG x.y.z)`. See samples/playground-ios/README.md.
@main
struct PlaygroundApp: App {
    @AppStorage("signed_in") private var signedIn = false

    var body: some Scene {
        WindowGroup {
            if signedIn { MainTabs(signedIn: $signedIn) } else { SignInView(signedIn: $signedIn) }
        }
    }
}

struct MainTabs: View {
    @Binding var signedIn: Bool

    var body: some View {
        TabView {
            HomeView().tabItem { Label("Home", systemImage: "house") }
            SearchView().tabItem { Label("Search", systemImage: "magnifyingglass") }
            LibraryView().tabItem { Label("Library", systemImage: "heart") }
            ProfileView(signedIn: $signedIn).tabItem { Label("Profile", systemImage: "person") }
        }
    }
}
