"""Middleware optionnel pour les cookies et l'authentification en contexte iframe (aperçu sandbox)."""

from __future__ import annotations

import http.cookies
import json
import re
from html import escape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.core import signing

http.cookies.Morsel._reserved.setdefault("partitioned", "Partitioned")
http.cookies.Morsel._flags.add("partitioned")

_AUTH_SALT = "preview-iframe-auth"
_CSRF_SALT = "preview-iframe-csrf"
_MAX_AGE_AUTH = 28800
_MAX_AGE_CSRF = 3600
_FORM_CONTENT_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")
_CSRF_INPUT_RE = re.compile(
    rb'(<input\b[^>]*\bname=["\']csrfmiddlewaretoken["\'][^>]*>)',
    re.IGNORECASE,
)


def _append_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key]
    params.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


def _strip_query_param_from_request(request, key: str) -> None:
    qs = request.META.get("QUERY_STRING", "")
    if f"{key}=" not in qs:
        return
    filtered = [(k, v) for k, v in parse_qsl(qs, keep_blank_values=True) if k != key]
    request.META["QUERY_STRING"] = urlencode(filtered)
    request.__dict__.pop("GET", None)


def _build_preview_script(
    csrf_cookie_name: str,
    pcsrf: str,
    pauth: str,
    is_auth: bool,
    force_fallback: bool,
    clear_auth: bool,
) -> bytes:
    cfg = json.dumps(
        {
            "csrfCookie": csrf_cookie_name,
            "pcsrf": pcsrf,
            "pauth": pauth,
            "isAuth": is_auth,
            "forceFallback": force_fallback,
            "clearAuth": clear_auth,
        }
    )
    script = f"""<script>
(function () {{
  var cfg = {cfg};
  var hasCsrf = document.cookie.split(";").some(function (c) {{
    return c.trim().indexOf(cfg.csrfCookie + "=") === 0;
  }});
  var urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has("_plogout")) {{
    try {{ sessionStorage.removeItem("_pauth"); }} catch (e) {{}}
    if (window.history && window.history.replaceState) {{
      urlParams.delete("_plogout");
      var q0 = urlParams.toString();
      window.history.replaceState(null, "", window.location.pathname + (q0 ? "?" + q0 : "") + window.location.hash);
    }}
  }}
  if (hasCsrf && !cfg.forceFallback) {{
    try {{ sessionStorage.removeItem("_pauth"); }} catch (e) {{}}
    if (urlParams.has("_pauth") && window.history && window.history.replaceState) {{
      urlParams.delete("_pauth");
      var q = urlParams.toString();
      window.history.replaceState(null, "", window.location.pathname + (q ? "?" + q : "") + window.location.hash);
    }}
    return;
  }}

  var activeAuth = "";
  try {{
    if (cfg.clearAuth) {{
      sessionStorage.removeItem("_pauth");
      activeAuth = "";
    }} else if (cfg.isAuth && cfg.pauth) {{
      sessionStorage.setItem("_pauth", cfg.pauth);
      activeAuth = cfg.pauth;
    }} else {{
      activeAuth = sessionStorage.getItem("_pauth") || "";
      if (!cfg.isAuth && activeAuth && !urlParams.has("_pauth")) {{
        var curPath = window.location.pathname || "/accueil/";
        var isLoginPage = (curPath.replace(/\\/+$/, "") === "/login" || curPath.replace(/\\/+$/, "") === "/admin/login");
        var nextPath = urlParams.get("next") || (isLoginPage ? (curPath.indexOf("/admin") === 0 ? "/admin/" : "/accueil/") : curPath);
        if (nextPath.charAt(0) === "/" && nextPath.indexOf("//") !== 0) {{
          var resumeUrl = new URL(nextPath, window.location.origin);
          resumeUrl.searchParams.set("_pauth", activeAuth);
          window.location.replace(resumeUrl.toString());
          return;
        }}
      }}
    }}
  }} catch (e) {{
    activeAuth = cfg.pauth || "";
  }}

  function setHidden(form, name, val) {{
    if (!val) return;
    var input = form.querySelector('input[type="hidden"][name="' + name + '"]');
    if (!input) {{
      input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      form.appendChild(input);
    }}
    input.value = val;
  }}

  function patchForm(form) {{
    if (!(form instanceof HTMLFormElement)) return;
    var method = (form.getAttribute("method") || "get").toLowerCase();
    if (method === "post") {{
      setHidden(form, "_pcsrf", cfg.pcsrf);
      setHidden(form, "_pauth", activeAuth);
    }} else if (activeAuth) {{
      setHidden(form, "_pauth", activeAuth);
    }}
  }}

  function patchLink(a) {{
    if (!activeAuth || !(a instanceof HTMLAnchorElement)) return;
    var raw = a.getAttribute("href");
    if (!raw || raw.charAt(0) === "#" || raw.indexOf("javascript:") === 0 || raw.indexOf("mailto:") === 0 || raw.indexOf("tel:") === 0) return;
    try {{
      var u = new URL(a.href, window.location.href);
      if (u.origin === window.location.origin && !u.searchParams.has("_pauth")) {{
        u.searchParams.set("_pauth", activeAuth);
        a.href = u.toString();
      }}
    }} catch (e) {{}}
  }}

  function patchAll(root) {{
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("form").forEach(patchForm);
    if (activeAuth) root.querySelectorAll("a[href]").forEach(patchLink);
  }}

  patchAll(document);
  document.addEventListener("submit", function (e) {{ patchForm(e.target); }}, true);
  document.addEventListener("click", function (e) {{
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (a) patchLink(a);
  }}, true);

  var origSubmit = HTMLFormElement.prototype.submit;
  HTMLFormElement.prototype.submit = function () {{
    patchForm(this);
    return origSubmit.apply(this, arguments);
  }};

  document.addEventListener("htmx:configRequest", function (e) {{
    if (activeAuth) e.detail.headers["X-Preview-Auth"] = activeAuth;
    if (cfg.pcsrf) e.detail.headers["X-Preview-Csrf"] = cfg.pcsrf;
  }});

  if (window.fetch) {{
    var origFetch = window.fetch;
    window.fetch = function (input, init) {{
      init = init || {{}};
      var headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
      if (activeAuth && !headers.has("X-Preview-Auth")) headers.set("X-Preview-Auth", activeAuth);
      if (cfg.pcsrf && !headers.has("X-Preview-Csrf")) headers.set("X-Preview-Csrf", cfg.pcsrf);
      init.headers = headers;
      return origFetch.call(this, input, init);
    }};
  }}

  if (window.XMLHttpRequest && XMLHttpRequest.prototype.open) {{
    var origOpen = XMLHttpRequest.prototype.open;
    var origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {{
      this._previewUrl = url;
      return origOpen.apply(this, arguments);
    }};
    XMLHttpRequest.prototype.send = function () {{
      try {{
        var target = new URL(this._previewUrl || "", window.location.href);
        if (target.origin === window.location.origin) {{
          if (activeAuth) this.setRequestHeader("X-Preview-Auth", activeAuth);
          if (cfg.pcsrf) this.setRequestHeader("X-Preview-Csrf", cfg.pcsrf);
        }}
      }} catch (e) {{}}
      return origSend.apply(this, arguments);
    }};
  }}

  if (window.MutationObserver && document.body) {{
    new MutationObserver(function (mutations) {{
      mutations.forEach(function (m) {{
        m.addedNodes.forEach(function (n) {{
          if (n.nodeType === 1) {{
            if (n.matches && n.matches("form")) patchForm(n);
            if (n.matches && n.matches("a[href]")) patchLink(n);
            patchAll(n);
          }}
        }});
      }});
    }}).observe(document.body, {{ childList: true, subtree: true }});
  }}
}})();
</script>"""
    return script.encode("utf-8")


class PartitionedIframeCookiesMiddleware:
    """
    Supporte les cookies CHIPS `Partitioned` et un repli signé pour les iframes
    dans lesquelles le navigateur bloque totalement les cookies tiers.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        had_session_cookie = settings.SESSION_COOKIE_NAME in request.COOKIES
        had_csrf_cookie = settings.CSRF_COOKIE_NAME in request.COOKIES
        used_preview_fallback = False
        clear_auth = False

        pauth_raw = request.GET.get("_pauth") or request.headers.get("X-Preview-Auth")
        _strip_query_param_from_request(request, "_pauth")
        if "_plogout" in request.GET:
            clear_auth = True
            _strip_query_param_from_request(request, "_plogout")

        if not pauth_raw and request.method == "POST" and request.content_type in _FORM_CONTENT_TYPES:
            pauth_raw = request.POST.get("_pauth")

        had_pauth_token = bool(pauth_raw)
        if pauth_raw:
            try:
                payload = signing.loads(pauth_raw, salt=_AUTH_SALT, max_age=_MAX_AGE_AUTH)
            except signing.BadSignature:
                payload = None
                clear_auth = True
            if isinstance(payload, dict):
                session_key = payload.get("s") or ""
                csrf_secret = payload.get("c") or ""
                if session_key and not had_session_cookie:
                    request.COOKIES[settings.SESSION_COOKIE_NAME] = session_key
                    used_preview_fallback = True
                if csrf_secret and settings.CSRF_COOKIE_NAME not in request.COOKIES:
                    request.COOKIES[settings.CSRF_COOKIE_NAME] = csrf_secret
                    used_preview_fallback = True

        if settings.CSRF_COOKIE_NAME not in request.COOKIES:
            pcsrf_raw = request.headers.get("X-Preview-Csrf")
            if not pcsrf_raw and request.method == "POST" and request.content_type in _FORM_CONTENT_TYPES:
                pcsrf_raw = request.POST.get("_pcsrf")
            if pcsrf_raw:
                try:
                    csrf_secret = signing.loads(pcsrf_raw, salt=_CSRF_SALT, max_age=_MAX_AGE_CSRF)
                except signing.BadSignature:
                    csrf_secret = ""
                if isinstance(csrf_secret, str) and csrf_secret:
                    request.COOKIES[settings.CSRF_COOKIE_NAME] = csrf_secret
                    used_preview_fallback = True

        response = self.get_response(request)

        for cookie in response.cookies.values():
            if str(cookie.get("samesite", "")).lower() == "none" and cookie.get("secure"):
                cookie["partitioned"] = True

        user = getattr(request, "user", None)
        is_auth = bool(getattr(user, "is_authenticated", False))
        is_logout = request.path.rstrip("/") in ("/logout", "/admin/logout")
        if is_logout or (had_pauth_token and not is_auth):
            clear_auth = True

        session = getattr(request, "session", None)
        session_key = getattr(session, "session_key", None) or ""
        if settings.SESSION_COOKIE_NAME in response.cookies and response.cookies[settings.SESSION_COOKIE_NAME].value:
            session_key = response.cookies[settings.SESSION_COOKIE_NAME].value

        csrf_secret = request.META.get("CSRF_COOKIE") or ""
        if settings.CSRF_COOKIE_NAME in response.cookies and response.cookies[settings.CSRF_COOKIE_NAME].value:
            csrf_secret = response.cookies[settings.CSRF_COOKIE_NAME].value
        if not csrf_secret:
            csrf_secret = request.COOKIES.get(settings.CSRF_COOKIE_NAME, "")

        cookieless_client = used_preview_fallback or (request.method == "POST" and not had_csrf_cookie)
        pauth_out = (
            signing.dumps({"s": session_key, "c": csrf_secret}, salt=_AUTH_SALT) if (is_auth and session_key) else ""
        )

        if 300 <= response.status_code < 400 and "Location" in response:
            location = response["Location"]
            if location.startswith("/") and not location.startswith("//"):
                if clear_auth and (cookieless_client or had_pauth_token):
                    response["Location"] = _append_query_param(location, "_plogout", "1")
                elif cookieless_client and pauth_out:
                    response["Location"] = _append_query_param(location, "_pauth", pauth_out)

        content_type = response.get("Content-Type", "")
        if response.status_code == 200 and "text/html" in content_type and not getattr(response, "streaming", False):
            pcsrf_out = signing.dumps(csrf_secret, salt=_CSRF_SALT) if csrf_secret else ""
            body = response.content

            extra_inputs = b""
            if pcsrf_out:
                extra_inputs += f'<input type="hidden" name="_pcsrf" value="{escape(pcsrf_out)}">'.encode()
            if cookieless_client and pauth_out:
                extra_inputs += f'<input type="hidden" name="_pauth" value="{escape(pauth_out)}">'.encode()
            if extra_inputs:
                body = _CSRF_INPUT_RE.sub(lambda m: m.group(1) + extra_inputs, body)

            snippet = _build_preview_script(
                settings.CSRF_COOKIE_NAME,
                pcsrf_out,
                pauth_out,
                is_auth,
                cookieless_client,
                clear_auth,
            )
            idx = body.lower().rfind(b"</body>")
            if idx != -1:
                body = body[:idx] + snippet + body[idx:]

            response.content = body
            if "Content-Length" in response:
                response["Content-Length"] = str(len(response.content))

        return response
