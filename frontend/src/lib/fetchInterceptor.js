/**
 * Fetch interceptor — attaches the Supabase JWT to every request that targets
 * the ScreenSolve backend API, without modifying any existing component code.
 *
 * Called ONCE at module-load time from App.js via setupFetchInterceptor().
 * Guards against double-patching with the _intercepted flag.
 *
 * Only backend calls (URLs containing REACT_APP_BACKEND_URL or /api/) are
 * affected. All other fetch calls are forwarded unchanged.
 */
import { supabase } from "./supabaseClient";

let _intercepted = false;

export function setupFetchInterceptor() {
  if (_intercepted || !supabase) return;
  _intercepted = true;

  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
  const _original = window.fetch.bind(window);

  window.fetch = async (input, init = {}) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
        ? input.href
        : input.url || "";

    // Only intercept calls to the ScreenSolve backend
    const isBackendCall =
      (BACKEND_URL && url.startsWith(BACKEND_URL)) ||
      url.includes("/api/");

    if (isBackendCall) {
      try {
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (session?.access_token) {
          init = {
            ...init,
            headers: {
              ...(init.headers || {}),
              Authorization: `Bearer ${session.access_token}`,
            },
          };
        }
      } catch {
        // Session retrieval failed — proceed without token
      }
    }

    return _original(input, init);
  };
}
