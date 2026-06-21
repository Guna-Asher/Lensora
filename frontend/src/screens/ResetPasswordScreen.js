/**
 * ResetPasswordScreen — completes the Supabase password-reset flow.
 *
 * Supabase sends a password-reset email with a link containing a token.
 * When the user clicks the link, Supabase redirects to this page and fires
 * a PASSWORD_RECOVERY event via onAuthStateChange. This component listens
 * for that event to enable the password update form.
 *
 * Note: /reset-password must be added to the Supabase project's
 * "Redirect URLs" allowlist in the dashboard.
 */
import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Scan, Lock } from "lucide-react";
import { supabase } from "../lib/supabaseClient";

export default function ResetPasswordScreen() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (!supabase) return;

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") {
        setReady(true);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!supabase) {
      setError("Authentication is not configured.");
      return;
    }
    setLoading(true);
    setError(null);

    const { error: err } = await supabase.auth.updateUser({ password });
    setLoading(false);

    if (err) {
      setError(err.message);
    } else {
      setMessage("Password updated. Redirecting to sign in…");
      setTimeout(() => navigate("/login", { replace: true }), 2000);
    }
  };

  return (
    <div
      className="flex flex-col min-h-screen bg-[#0A0A0A] px-6 py-10"
      data-testid="reset-password-screen"
    >
      {/* Header */}
      <div className="flex flex-col items-center mb-10">
        <div className="mb-4 w-12 h-12 rounded-2xl bg-[#181818] border border-[#27272A] flex items-center justify-center">
          <Scan size={22} className="text-[#2563EB]" />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-[#F8F8F8]">
          New password
        </h1>
        <p className="mt-1 text-sm text-[#A1A1AA]">
          {ready ? "Choose a new password below" : "Waiting for reset confirmation…"}
        </p>
      </div>

      {/* Error */}
      {error && (
        <div
          data-testid="reset-error"
          className="mb-5 p-4 bg-[#EF4444]/10 border border-[#EF4444]/30 rounded-2xl text-[#EF4444] text-sm text-center"
        >
          {error}
        </div>
      )}

      {/* Success */}
      {message && (
        <div
          data-testid="reset-message"
          className="mb-5 p-4 bg-[#22C55E]/10 border border-[#22C55E]/30 rounded-2xl text-[#22C55E] text-sm text-center"
        >
          {message}
        </div>
      )}

      {ready && !message && (
        <form onSubmit={handleSubmit} className="space-y-3 mb-6">
          <div className="relative">
            <Lock size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#52525B]" />
            <input
              data-testid="reset-password-input"
              type="password"
              placeholder="New password (min 6 characters)"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              className="w-full h-14 bg-[#111111] border border-[#27272A] rounded-2xl pl-11 pr-4 text-[#F8F8F8] placeholder-[#52525B] text-sm focus:outline-none focus:border-[#2563EB] transition-colors"
            />
          </div>

          <button
            data-testid="reset-submit-button"
            type="submit"
            disabled={loading}
            className="w-full h-14 bg-[#2563EB] text-[#F8F8F8] rounded-2xl font-medium text-sm active:opacity-80 transition-opacity disabled:opacity-50"
          >
            {loading ? "Updating…" : "Update password"}
          </button>
        </form>
      )}

      {!ready && !message && (
        <div className="flex justify-center">
          <div className="w-8 h-8 rounded-full border-2 border-[#2563EB] border-t-transparent animate-spin" />
        </div>
      )}

      <p className="mt-8 text-center text-sm text-[#A1A1AA]">
        <Link
          data-testid="back-to-login-link-reset"
          to="/login"
          className="text-[#2563EB] hover:underline"
        >
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
