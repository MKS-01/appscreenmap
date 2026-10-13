// AppScreenMap security audit: observation-only Frida hooks for an Android app. For builds you own or may test.
//
//   frida -U -f <package> -l frida-observe.js > frida.log        # spawn it, then use the app (or crawl it)
//   appscreenmap security <run> --frida-log frida.log
//
// It prints one JSON line per observation and changes nothing: no pinning bypass, no request rewriting.
//   cleartext  the app opened a plain http:// URL (host only, never the path or query)
//   pinning    OkHttp opened a TLS connection to <host>; "pinned" says whether any certificate pin is configured
// A hook that can't attach (the app doesn't use OkHttp, the class is obfuscated) is reported as "hook-failed".
// Not covered yet: iOS, Retrofit-less stacks such as HttpsURLConnection-only apps, WebView traffic.

Java.perform(function () {
  var seen = {};
  function emit(o) {
    o.asm = 1;
    console.log(JSON.stringify(o));
  }
  function once(key, o) {
    if (!seen[key]) {
      seen[key] = 1;
      emit(o);
    }
  }
  function hostOf(url) {
    var m = /^[a-z][a-z0-9+.\-]*:\/\/([^\/:?#]+)/i.exec(String(url));
    return m ? m[1] : null;
  }

  try {
    var URL = Java.use("java.net.URL");
    URL.$init.overload("java.lang.String").implementation = function (spec) {
      var url = String(spec);
      var host = hostOf(url);
      if (host && /^http:\/\//i.test(url)) once("clear:" + host, { check: "cleartext", host: host });
      return this.$init(spec);
    };
  } catch (e) {
    emit({ check: "hook-failed", what: "java.net.URL", error: String(e) });
  }

  try {
    var Pinner = Java.use("okhttp3.CertificatePinner");
    // OkHttp calls check() on every TLS handshake, even with the default (empty) pinner.
    Pinner.check.overload("java.lang.String", "java.util.List").implementation = function (host, certs) {
      var pins = -1;
      try {
        pins = this.pins.value.size();
      } catch (e) {}
      if (pins < 0) {
        // Can't tell (an obfuscated build): say so instead of guessing "not pinned".
        once("pins-unreadable", { check: "hook-failed", what: "CertificatePinner.pins (field not readable)" });
      } else {
        once("pin:" + host, { check: "pinning", host: String(host), pins: pins, pinned: pins > 0 });
      }
      return this.check(host, certs);
    };
  } catch (e) {
    emit({ check: "hook-failed", what: "okhttp3.CertificatePinner", error: String(e) });
  }
});
