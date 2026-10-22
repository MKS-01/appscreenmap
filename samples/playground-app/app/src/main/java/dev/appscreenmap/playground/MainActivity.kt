@file:OptIn(ExperimentalComposeUiApi::class)

package dev.appscreenmap.playground

import android.content.Context
import android.content.SharedPreferences
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId

/**
 * AppScreenMap Playground: a small app built to exercise every crawler feature on purpose.
 * Screens are listed in samples/playground-app/README.md with the scenario each one demonstrates.
 * Deliberate accessibility bugs are marked `A11Y BUG (WCAG x.y.z)`; v2 fixes some of them.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = getSharedPreferences("playground", Context.MODE_PRIVATE)
        setContent {
            MaterialTheme {
                // Expose Compose test tags as resource ids, so crawlers and Maestro get stable selectors.
                Box(Modifier.fillMaxSize().semantics { testTagsAsResourceId = true }) {
                    PlaygroundApp(prefs)
                }
            }
        }
    }
}

sealed interface Route {
    data object SignIn : Route
    data object ForgotPassword : Route
    data object ResetSent : Route
    data object Home : Route
    data object Search : Route
    data object Library : Route
    data object Profile : Route
    data class Article(val id: Int) : Route
    data class SearchResults(val query: String) : Route
    data object Reports : Route
    data object Gallery : Route
    data object Account : Route
    data object Notifications : Route
    data object TextSize : Route
    data object Help : Route
    data object Feedback : Route
    data object Terms : Route
    data object Developer : Route
    data object Network : Route
    data object WhatsNew : Route
}

val TABS = listOf(Route.Home, Route.Search, Route.Library, Route.Profile)

/** A tiny navigation stack: no navigation library, so the demo has no extra dependencies. */
class Nav(start: Route) {
    val stack = mutableStateListOf(start)
    val current: Route get() = stack.last()

    fun go(route: Route) {
        stack.add(route)
    }

    fun back(): Boolean {
        if (stack.size <= 1) return false
        stack.removeAt(stack.lastIndex)
        return true
    }

    fun reset(route: Route) {
        stack.clear()
        stack.add(route)
    }
}

@Composable
fun PlaygroundApp(prefs: SharedPreferences) {
    val nav = remember { Nav(if (prefs.getBoolean("signed_in", false)) Route.Home else Route.SignIn) }
    BackHandler(enabled = nav.stack.size > 1) { nav.back() }
    val current = nav.current
    Scaffold(bottomBar = { if (current in TABS) BottomBar(current, nav) }) { padding ->
        // A11Y BUG (WCAG 2.4.11 Focus Not Obscured): v1 lets the Home feed scroll under the bottom bar
        // (no bottom padding), so the last card's controls can sit fully behind it.
        val contentPadding =
            if (current == Route.Home && !BuildConfig.V2) PaddingValues(top = padding.calculateTopPadding()) else padding
        Box(Modifier.padding(contentPadding)) {
            when (current) {
                Route.SignIn -> SignInScreen(nav, prefs)
                Route.ForgotPassword -> ForgotPasswordScreen(nav)
                Route.ResetSent -> ResetSentScreen(nav)
                Route.Home -> HomeScreen(nav)
                Route.Search -> SearchScreen(nav)
                Route.Library -> LibraryScreen(nav)
                Route.Profile -> ProfileScreen(nav, prefs)
                is Route.Article -> ArticleScreen(nav, current.id)
                is Route.SearchResults -> SearchResultsScreen(nav, current.query)
                Route.Reports -> ReportsScreen(nav)
                Route.Gallery -> GalleryScreen(nav)
                Route.Account -> AccountScreen(nav)
                Route.Notifications -> NotificationsScreen(nav)
                Route.TextSize -> TextSizeScreen(nav)
                Route.Help -> HelpScreen(nav)
                Route.Feedback -> FeedbackScreen(nav)
                Route.Terms -> TermsScreen(nav)
                Route.Developer -> DeveloperScreen(nav)
                Route.Network -> NetworkScreen(nav)
                Route.WhatsNew -> WhatsNewScreen(nav)
            }
        }
    }
}

private data class Tab(val route: Route, val label: String, val icon: ImageVector, val tag: String)

@Composable
private fun BottomBar(current: Route, nav: Nav) {
    val tabs =
        listOf(
            Tab(Route.Home, "Home", Icons.Default.Home, "tab_home"),
            Tab(Route.Search, "Search", Icons.Default.Search, "tab_search"),
            Tab(Route.Library, "Library", Icons.Default.Favorite, "tab_library"),
            Tab(Route.Profile, "Profile", Icons.Default.Person, "tab_profile"),
        )
    // A11Y BUG (WCAG 3.2.3 Consistent Navigation): in v1 the Search tab shows the bar in a different order.
    val ordered = if (current == Route.Search && !BuildConfig.V2) listOf(tabs[1], tabs[0], tabs[2], tabs[3]) else tabs
    NavigationBar(Modifier.testTag("bottom_nav")) {
        ordered.forEach { tab ->
            NavigationBarItem(
                selected = current == tab.route,
                onClick = { if (current != tab.route) nav.reset(tab.route) },
                icon = { Icon(tab.icon, contentDescription = null) },
                label = { Text(tab.label) },
                modifier = Modifier.testTag(tab.tag),
            )
        }
    }
}
