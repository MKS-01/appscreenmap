import SwiftUI

struct SignInView: View {
    @Binding var signedIn: Bool
    @State private var email = ""
    @State private var password = ""
    @State private var tried = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Sign in to sync your reading list. Any email works: this is a demo.")
                    TextField("Email", text: $email)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityIdentifier("email")
                    SecureField("Password", text: $password)
                        .accessibilityIdentifier("password")
                    if tried && email.isEmpty {
                        Text("Enter your email address").foregroundStyle(.red).accessibilityIdentifier("email_error")
                    }
                }
                Section {
                    Button("Sign in") {
                        tried = true
                        if !email.isEmpty { signedIn = true }
                    }
                    .accessibilityIdentifier("sign_in")
                    NavigationLink("Forgot password?") { ForgotPasswordView() }
                        .accessibilityIdentifier("forgot_password")
                    Button("Continue as guest") { signedIn = true }
                        .accessibilityIdentifier("guest")
                }
            }
            .navigationTitle("Welcome back")
        }
    }
}

struct ForgotPasswordView: View {
    @State private var email = ""

    var body: some View {
        Form {
            // A11Y BUG (WCAG 3.3.7 Redundant Entry): asks again for the email typed on the previous screen.
            TextField("Email", text: $email).accessibilityIdentifier("reset_email")
            NavigationLink("Send reset link") { ResetSentView() }.accessibilityIdentifier("send_reset")
        }
        .navigationTitle("Reset password")
    }
}

struct ResetSentView: View {
    var body: some View {
        Text("We sent a link to your email. Open it to choose a new password.")
            .padding()
            .navigationTitle("Check your inbox")
    }
}
