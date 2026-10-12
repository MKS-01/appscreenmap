@file:OptIn(ExperimentalMaterial3Api::class)

package dev.appscreenmap.playground

import android.Manifest
import android.content.Intent
import android.content.SharedPreferences
import android.net.Uri
import android.os.Build
import android.webkit.WebView
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.delay

private val V2 = BuildConfig.V2

data class ArticleData(val id: Int, val site: String, val title: String, val minutes: Int)

val ARTICLES =
    listOf(
        ArticleData(1, "playground.dev", "Getting started with the Playground", 3),
        ArticleData(2, "notes.example", "Why every screen should have a title", 4),
        ArticleData(3, "design.example", "Touch targets: 24 dp is the floor, 48 dp is the goal", 5),
        ArticleData(4, "perf.example", "A slow screen is a bug, even when it works", 6),
        ArticleData(5, "a11y.example", "Label in name: say what you see", 2),
        ArticleData(6, "notes.example", "The long title that does not fit on a single line of a phone screen at all", 7),
        ArticleData(7, "design.example", "Consistent navigation, one bar everywhere", 3),
        ArticleData(8, "perf.example", "Frames, jank and the 16 millisecond budget", 8),
        ArticleData(9, "playground.dev", "Forms that do not ask twice", 4),
        ArticleData(10, "a11y.example", "Dragging is optional, buttons are not", 3),
        ArticleData(11, "notes.example", "Orientation: let people turn their phone", 2),
        ArticleData(12, "playground.dev", "That's the end of the feed", 1),
    )

// ── shared pieces ───────────────────────────────────────────────────────────

@Composable
private fun Bar(title: String, nav: Nav?, actions: @Composable () -> Unit = {}) {
    TopAppBar(
        title = { Text(title, Modifier.testTag("screen_title")) },
        navigationIcon = {
            if (nav != null && nav.stack.size > 1) {
                IconButton(onClick = { nav.back() }, modifier = Modifier.testTag("navigate_up")) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Navigate up")
                }
            }
        },
        actions = { actions() },
    )
}

@Composable
private fun Page(content: @Composable () -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) { content() }
}

// ── sign in ─────────────────────────────────────────────────────────────────

@Composable
fun SignInScreen(nav: Nav, prefs: SharedPreferences) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var tried by remember { mutableStateOf(false) }
    Column {
        Bar("Welcome back", null)
        Page {
            Text("Sign in to sync your reading list. Any email works: this is a demo.")
            OutlinedTextField(
                value = email,
                onValueChange = { email = it },
                label = { Text("Email") },
                isError = tried && email.isBlank(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                modifier = Modifier.fillMaxWidth().testTag("email"),
            )
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                modifier = Modifier.fillMaxWidth().testTag("password"),
            )
            if (tried && email.isBlank()) {
                Text("Enter your email address", color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("email_error"))
            }
            Button(
                onClick = {
                    tried = true
                    if (email.isNotBlank()) {
                        prefs.edit().putBoolean("signed_in", true).apply()
                        nav.reset(Route.Home)
                    }
                },
                // v2 renames and recolours the button: shows up as "changed" in the visual diff.
                colors = if (V2) ButtonDefaults.buttonColors(containerColor = Color(0xFF00695C)) else ButtonDefaults.buttonColors(),
                modifier = Modifier.fillMaxWidth().testTag("sign_in"),
            ) { Text(if (V2) "Log in" else "Sign in") }
            TextButton(onClick = { nav.go(Route.ForgotPassword) }, modifier = Modifier.testTag("forgot_password")) {
                Text("Forgot password?")
            }
            TextButton(
                onClick = {
                    prefs.edit().putBoolean("signed_in", true).apply()
                    nav.reset(Route.Home)
                },
                modifier = Modifier.testTag("guest"),
            ) { Text("Continue as guest") }
        }
    }
}

@Composable
fun ForgotPasswordScreen(nav: Nav) {
    var email by remember { mutableStateOf("") }
    Column {
        Bar("Reset password", nav)
        Page {
            // A11Y BUG (WCAG 3.3.7 Redundant Entry): asks again for the email typed on the previous screen.
            Text("Enter your email again and we'll send a reset link.")
            OutlinedTextField(
                value = email,
                onValueChange = { email = it },
                label = { Text("Email") },
                modifier = Modifier.fillMaxWidth().testTag("reset_email"),
            )
            Button(onClick = { if (email.isNotBlank()) nav.go(Route.ResetSent) }, modifier = Modifier.testTag("send_reset")) {
                Text("Send reset link")
            }
        }
    }
}

@Composable
fun ResetSentScreen(nav: Nav) {
    Column {
        Bar("Check your inbox", nav)
        Page {
            Text("If an account exists, a reset link is on its way.")
            Button(onClick = { nav.reset(Route.SignIn) }, modifier = Modifier.testTag("back_to_sign_in")) { Text("Back to sign in") }
        }
    }
}

// ── home ────────────────────────────────────────────────────────────────────

@Composable
fun HomeScreen(nav: Nav) {
    Column {
        Bar(if (V2) "For you" else "Discover", nav) {
            // Help sits top-right here but mid-list on Profile (WCAG 3.2.6 Consistent Help demo).
            IconButton(onClick = { nav.go(Route.Help) }, modifier = Modifier.testTag("help")) {
                Icon(Icons.Default.Info, contentDescription = "Help")
            }
        }
        LazyColumn(Modifier.fillMaxSize().testTag("feed"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { nav.go(Route.Reports) }, modifier = Modifier.testTag("open_reports")) { Text("Reports") }
                    OutlinedButton(onClick = { nav.go(Route.Gallery) }, modifier = Modifier.testTag("open_gallery")) { Text("Gallery") }
                }
            }
            items(ARTICLES, key = { it.id }) { a -> ArticleCard(a) { nav.go(Route.Article(a.id)) } }
        }
    }
}

@Composable
private fun ArticleCard(a: ArticleData, open: () -> Unit) {
    var saved by remember { mutableStateOf(false) }
    Card(Modifier.fillMaxWidth().padding(horizontal = 16.dp).clickable(onClick = open).testTag("article_card")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(a.site, style = MaterialTheme.typography.labelMedium)
            // A11Y BUG (WCAG 1.4.4 Resize Text): one line, ellipsized; long titles lose content.
            Text(a.title, style = MaterialTheme.typography.titleMedium, maxLines = if (V2) 3 else 1, overflow = TextOverflow.Ellipsis)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("${a.minutes} min read", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                // A11Y BUG (WCAG 2.5.8 Target Size + 4.1.2 Name): 20 dp icons 6 dp apart; v1's bookmark has no label.
                val size = if (V2) 48.dp else 20.dp
                Icon(
                    if (saved) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                    contentDescription = if (V2) (if (saved) "Remove bookmark" else "Bookmark") else null,
                    modifier = Modifier.size(size).clickable { saved = !saved }.testTag("bookmark"),
                )
                Icon(
                    Icons.Default.Share,
                    contentDescription = "Share",
                    modifier = Modifier.size(size).clickable { }.testTag("share"),
                )
            }
        }
    }
}

@Composable
fun ArticleScreen(nav: Nav, id: Int) {
    val a = ARTICLES.first { it.id == id }
    Column {
        Bar("Article", nav)
        Page {
            Text(a.title, style = MaterialTheme.typography.headlineSmall, modifier = Modifier.testTag("article_title"))
            Text("${a.site} · ${a.minutes} min read", style = MaterialTheme.typography.labelMedium)
            Box(Modifier.fillMaxWidth().height(160.dp).background(Color(0xFFE3E7F1)))
            // A11Y BUG (WCAG 1.4.3 Contrast): light grey caption on white in v1.
            Text("Photo: Playground archive", color = if (V2) Color(0xFF5F6368) else Color(0xFFC8C8C8), style = MaterialTheme.typography.bodySmall)
            repeat(3) { i ->
                Text(
                    "Paragraph ${i + 1}. This article is placeholder text so every article shares the same layout. " +
                        "The crawler should treat all article pages as one template with variants.",
                )
            }
            // A11Y BUG (WCAG 2.5.3 Label in Name): shows "Listen" but is announced as "Play audio" in v1.
            Button(
                onClick = { },
                modifier = Modifier.testTag("listen").semantics { contentDescription = if (V2) "Listen to this article" else "Play audio" },
            ) { Text("Listen") }
        }
    }
}

// ── search ──────────────────────────────────────────────────────────────────

@Composable
fun SearchScreen(nav: Nav) {
    var query by remember { mutableStateOf("") }
    Column {
        Bar("Search", nav)
        Page {
            OutlinedTextField(
                value = query,
                onValueChange = {
                    query = it
                    // A11Y BUG (WCAG 3.2.2 On Input): v1 jumps to results while you're still typing.
                    if (!V2 && it.trim().length >= 3) nav.go(Route.SearchResults(it.trim()))
                },
                label = { Text("Search articles") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { if (query.isNotBlank()) nav.go(Route.SearchResults(query.trim())) }),
                modifier = Modifier.fillMaxWidth().testTag("search_field"),
            )
            if (V2) {
                Button(onClick = { if (query.isNotBlank()) nav.go(Route.SearchResults(query.trim())) }, modifier = Modifier.testTag("search_go")) {
                    Text("Search")
                }
            }
            Text("Popular", style = MaterialTheme.typography.titleSmall)
            listOf("touch targets", "contrast", "performance").forEach { term ->
                ListItem(
                    headlineContent = { Text(term) },
                    modifier = Modifier.clickable { nav.go(Route.SearchResults(term)) }.testTag("popular_search"),
                )
            }
        }
    }
}

@Composable
fun SearchResultsScreen(nav: Nav, query: String) {
    val results = ARTICLES.filter { it.title.contains(query.split(" ").first(), ignoreCase = true) }.ifEmpty { ARTICLES.take(3) }
    Column {
        Bar("Results", nav)
        LazyColumn(Modifier.fillMaxSize()) {
            item { Text("Showing results for \"$query\"", Modifier.padding(16.dp)) }
            items(results, key = { it.id }) { a ->
                ListItem(
                    headlineContent = { Text(a.title) },
                    supportingContent = { Text(a.site) },
                    modifier = Modifier.clickable { nav.go(Route.Article(a.id)) }.testTag("result"),
                )
                HorizontalDivider()
            }
        }
    }
}

// ── library ─────────────────────────────────────────────────────────────────

@Composable
fun LibraryScreen(nav: Nav) {
    var tab by remember { mutableIntStateOf(0) }
    Column {
        Bar("Library", nav)
        PrimaryTabRow(selectedTabIndex = tab) {
            Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Downloads") }, modifier = Modifier.testTag("tab_downloads"))
            Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("History") }, modifier = Modifier.testTag("tab_history"))
        }
        if (tab == 0) {
            Column(Modifier.fillMaxSize().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text("No downloads yet", style = MaterialTheme.typography.titleMedium)
                Text("Articles you download show up here.", Modifier.padding(vertical = 8.dp))
                Button(onClick = { nav.reset(Route.Home) }, modifier = Modifier.testTag("browse")) { Text("Browse articles") }
            }
        } else {
            LazyColumn(Modifier.fillMaxSize()) {
                items(ARTICLES.take(5), key = { it.id }) { a ->
                    ListItem(
                        headlineContent = { Text(a.title) },
                        supportingContent = { Text("Read yesterday") },
                        modifier = Modifier.clickable { nav.go(Route.Article(a.id)) }.testTag("history_item"),
                    )
                }
            }
        }
    }
}

// ── profile ─────────────────────────────────────────────────────────────────

@Composable
fun ProfileScreen(nav: Nav, prefs: SharedPreferences) {
    val context = LocalContext.current
    var rateOpen by remember { mutableStateOf(false) }
    Column {
        Bar("Profile", nav)
        LazyColumn(Modifier.fillMaxSize()) {
            item {
                Column(Modifier.padding(20.dp)) {
                    Text("Alex Reader", style = MaterialTheme.typography.titleLarge)
                    Text("alex@playground.dev", style = MaterialTheme.typography.bodyMedium)
                }
            }
            val rows =
                buildList {
                    add("Account settings" to { nav.go(Route.Account) })
                    add("Notifications" to { nav.go(Route.Notifications) })
                    add("Text size" to { nav.go(Route.TextSize) })
                    add("Help" to { nav.go(Route.Help) })
                    add("Terms of use" to { nav.go(Route.Terms) })
                    // Opens the browser: the crawler's stay-in-app pinning blocks it.
                    add("Privacy policy" to { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com/privacy"))) })
                    if (V2) add("What's new" to { nav.go(Route.WhatsNew) }) else add("Rate us" to { rateOpen = true })
                    add("Developer options" to { nav.go(Route.Developer) })
                    // Matches the crawler's blocked_text, so it is never tapped.
                    add("Log out" to { prefs.edit().putBoolean("signed_in", false).apply(); nav.reset(Route.SignIn) })
                }
            items(rows, key = { it.first }) { (label, action) ->
                ListItem(headlineContent = { Text(label) }, modifier = Modifier.clickable(onClick = action).testTag("profile_row"))
                HorizontalDivider()
            }
        }
    }
    if (rateOpen) {
        AlertDialog(
            onDismissRequest = { rateOpen = false },
            title = { Text("Enjoying Playground?") },
            text = { Text("A dialog, so the crawler records a dialog pattern.") },
            confirmButton = { TextButton(onClick = { rateOpen = false }, modifier = Modifier.testTag("rate_yes")) { Text("Rate 5 stars") } },
            dismissButton = { TextButton(onClick = { rateOpen = false }, modifier = Modifier.testTag("rate_no")) { Text("Not now") } },
        )
    }
}

@Composable
fun AccountScreen(nav: Nav) {
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var saved by remember { mutableStateOf(false) }
    Column {
        Bar("Account settings", nav)
        Page {
            OutlinedTextField(name, { name = it }, label = { Text("Display name") }, modifier = Modifier.fillMaxWidth().testTag("display_name"))
            OutlinedTextField(email, { email = it }, label = { Text("Email") }, modifier = Modifier.fillMaxWidth().testTag("account_email"))
            // Same id as Feedback's "Submit" button (WCAG 3.2.4 Consistent Identification demo).
            Button(onClick = { saved = true }, modifier = Modifier.testTag("primary_action")) { Text("Save") }
            if (saved) Text("Saved", modifier = Modifier.testTag("saved_note"))
            Spacer(Modifier.height(24.dp))
            OutlinedButton(onClick = { }, modifier = Modifier.testTag("delete_account")) { Text("Delete account") }
        }
    }
}

@Composable
fun NotificationsScreen(nav: Nav) {
    var articles by remember { mutableStateOf(true) }
    var digest by remember { mutableStateOf(false) }
    var allowed by remember { mutableStateOf(false) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed = it }
    Column {
        Bar("Notifications", nav)
        Page {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("New articles", Modifier.weight(1f))
                Switch(checked = articles, onCheckedChange = { articles = it }, modifier = Modifier.testTag("switch_articles"))
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Weekly digest", Modifier.weight(1f))
                Switch(checked = digest, onCheckedChange = { digest = it }, modifier = Modifier.testTag("switch_digest"))
            }
            Button(
                onClick = { if (Build.VERSION.SDK_INT >= 33) launcher.launch(Manifest.permission.POST_NOTIFICATIONS) else allowed = true },
                modifier = Modifier.testTag("allow_notifications"),
            ) { Text("Allow notifications") }
            if (allowed) Text("Notifications are on")
        }
    }
}

@Composable
fun TextSizeScreen(nav: Nav) {
    var size by remember { mutableFloatStateOf(16f) }
    Column {
        Bar("Text size", nav)
        Page {
            // A11Y REVIEW (WCAG 2.5.7 Dragging Movements): a slider; v2 adds buttons as an alternative.
            Text("Preview text at ${size.toInt()} sp", style = MaterialTheme.typography.bodyLarge)
            Slider(value = size, onValueChange = { size = it }, valueRange = 12f..28f, modifier = Modifier.testTag("text_size_slider"))
            if (V2) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { size = (size - 1).coerceAtLeast(12f) }, modifier = Modifier.testTag("smaller")) { Text("Smaller") }
                    OutlinedButton(onClick = { size = (size + 1).coerceAtMost(28f) }, modifier = Modifier.testTag("larger")) { Text("Larger") }
                }
            }
        }
    }
}

@Composable
fun HelpScreen(nav: Nav) {
    Column {
        Bar("Help", nav)
        Page {
            listOf(
                "How do I save an article?" to "Tap the heart on any card.",
                "Where are my downloads?" to "Library, then Downloads.",
                "Is any of this real?" to "No. It's a playground for AppScreenMap.",
            ).forEach { (q, a) ->
                Text(q, style = MaterialTheme.typography.titleSmall)
                Text(a)
            }
            Button(onClick = { nav.go(Route.Feedback) }, modifier = Modifier.testTag("contact_support")) { Text("Contact support") }
        }
    }
}

@Composable
fun FeedbackScreen(nav: Nav) {
    var message by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var sent by remember { mutableStateOf(false) }
    Column {
        Bar("Feedback", nav)
        Page {
            Text("Tell us what to improve.")
            // A11Y BUG (WCAG 3.3.2 Labels or Instructions): v1's message field has no label or hint.
            OutlinedTextField(
                value = message,
                onValueChange = { message = it },
                label = if (V2) ({ Text("Your message") }) else null,
                modifier = Modifier.fillMaxWidth().height(120.dp).testTag("feedback_message"),
            )
            OutlinedTextField(email, { email = it }, label = { Text("Your email") }, modifier = Modifier.fillMaxWidth().testTag("feedback_email"))
            Button(onClick = { sent = true }, modifier = Modifier.testTag("primary_action")) { Text("Submit") }
            if (sent) Text("Thanks! We read everything.")
        }
    }
}

@Composable
fun TermsScreen(nav: Nav) {
    Column {
        Bar("Terms of use", nav)
        AndroidView(
            factory = { ctx -> WebView(ctx).apply { loadUrl("file:///android_asset/terms.html") } },
            modifier = Modifier.fillMaxSize().testTag("terms_webview"),
        )
    }
}

@Composable
fun DeveloperScreen(nav: Nav) {
    val context = LocalContext.current
    Column {
        Bar("Developer options", nav)
        Page {
            Text("Tools for testing the crawler.")
            Button(
                onClick = { context.startActivity(Intent(context, ScannerActivity::class.java)) },
                modifier = Modifier.testTag("open_scanner"),
            ) { Text("Open scanner") }
            // Crash detection demo: the crawler records the crash with its logcat and relaunches.
            Button(
                onClick = { throw IllegalStateException("Playground: intentional crash for the AppScreenMap demo") },
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                modifier = Modifier.testTag("crash"),
            ) { Text("Crash the app") }
        }
    }
}

@Composable
fun WhatsNewScreen(nav: Nav) {
    Column {
        Bar("What's new", nav)
        Page {
            listOf(
                "Reports load four times faster.",
                "Bookmark and share buttons are bigger and labelled.",
                "Search waits for you to finish typing.",
                "The Gallery scrolls smoothly.",
            ).forEach { Text("• $it") }
        }
    }
}

// ── performance scenarios ───────────────────────────────────────────────────

@Composable
fun ReportsScreen(nav: Nav) {
    var loading by remember { mutableStateOf(true) }
    LaunchedEffect(Unit) {
        // Slow screen demo: v1 "fetches" for 2.5 s, v2 for 0.6 s. The crawler times it until content draws.
        delay(if (V2) 600 else 2500)
        loading = false
    }
    Column {
        Bar("Reports", nav)
        if (loading) {
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                CircularProgressIndicator(Modifier.testTag("loading"))
                Text("Loading reports…", Modifier.padding(16.dp))
            }
        } else {
            Page {
                listOf("Articles read" to "42", "Minutes listened" to "318", "Bookmarks" to "7", "Streak" to "5 days").forEach { (k, v) ->
                    Row {
                        Text(k, Modifier.weight(1f))
                        Text(v, style = MaterialTheme.typography.titleMedium)
                    }
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
fun GalleryScreen(nav: Nav) {
    var tick by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) {
        // Jank demo: v1 does ~35 ms of work on the UI thread for 45 frames after opening.
        if (!V2) repeat(45) { withFrameNanos { }; tick++ }
    }
    if (!V2 && tick in 1..44) Thread.sleep(35)
    Column {
        Bar("Gallery", nav)
        LazyVerticalGrid(GridCells.Fixed(3), Modifier.fillMaxSize().padding(8.dp).testTag("gallery_grid")) {
            items((1..30).toList(), key = { it }) { i ->
                Box(
                    Modifier.padding(4.dp).aspectRatio(1f).background(Color(0xFF3949AB).copy(alpha = 0.25f + (i % 4) * 0.18f)),
                    contentAlignment = Alignment.Center,
                ) { Text("$i ${if (tick % 2 == 0) "" else " "}", color = Color.White) }
            }
        }
    }
}
