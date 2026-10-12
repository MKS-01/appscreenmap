package dev.appscreenmap.playground

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/** A second activity (activity coverage), locked to portrait in the manifest (WCAG 1.3.4 demo). */
class ScannerActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Column(
                    Modifier.fillMaxSize().padding(32.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text("Scanner", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.testTag("screen_title"))
                    Text("Point the camera at a code. (Nothing happens: it's a demo.)", Modifier.padding(vertical = 16.dp))
                    Button(onClick = { finish() }, modifier = Modifier.testTag("close_scanner")) { Text("Close scanner") }
                }
            }
        }
    }
}
