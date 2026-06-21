/**
 * Supabase client singleton.
 *
 * Reads REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY from the
 * environment. Exports null when either variable is missing so the rest of
 * the app can degrade gracefully (auth disabled, health endpoint still works).
 *
 * Never import the service-role key here — this file is browser-side code.
 */
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn(
    "[ScreenSolve] Supabase not configured. " +
      "Set REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY to enable authentication."
  );
}

export const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey)
    : null;
