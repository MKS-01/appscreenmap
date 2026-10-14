import SwiftUI

struct SearchView: View {
    @State private var query = ""

    var body: some View {
        NavigationStack {
            List(["accessibility", "performance", "forms"], id: \.self) { term in
                Button(term) { query = term }
            }
            .navigationTitle("Search")
            .searchable(text: $query, prompt: "Search articles")
        }
    }
}

struct LibraryView: View {
    @State private var tab = 0

    var body: some View {
        NavigationStack {
            VStack {
                Picker("Section", selection: $tab) {
                    Text("Downloads").tag(0)
                    Text("History").tag(1)
                }
                .pickerStyle(.segmented)
                .padding()
                Spacer()
                Text(tab == 0 ? "No downloads yet" : "Nothing read yet")
                Spacer()
            }
            .navigationTitle("Library")
        }
    }
}

struct ProfileView: View {
    @Binding var signedIn: Bool

    var body: some View {
        NavigationStack {
            List {
                VStack(alignment: .leading) {
                    Text("Alex Reader").font(.title3)
                    Text("alex@playground.dev").font(.subheadline)
                }
                NavigationLink("Account settings") { AccountView() }.accessibilityIdentifier("profile_row")
                NavigationLink("Help") { HelpView() }.accessibilityIdentifier("profile_row")
                // Matches the crawler's blocked_text, so it is never tapped.
                Button("Log out") { signedIn = false }.accessibilityIdentifier("profile_row")
            }
            .navigationTitle("Profile")
        }
    }
}

struct AccountView: View {
    @State private var email = "alex@playground.dev"

    var body: some View {
        Form {
            // Same email asked again: WCAG 3.3.7 Redundant Entry.
            TextField("Email", text: $email).accessibilityIdentifier("account_email")
            Button("Save") {}.accessibilityIdentifier("save")
            Button("Delete account", role: .destructive) {}.accessibilityIdentifier("delete_account")
        }
        .navigationTitle("Account settings")
    }
}
