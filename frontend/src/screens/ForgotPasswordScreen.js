/**
 * ForgotPasswordScreen — sends a Supabase password-reset email.
 *
 * The reset link in the email will redirect to /reset-password.
 * The redirectTo URL must be added to the Supabase project's
 * "Redirect URLs" allowlist in the dashboard.
 */
import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Scan, Mail } from "lucide-react";
import { supabase } from "../lib/supabaseClient";

export default function ForgotPasswordScreen() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!supabase) {
      setError("Authentication is not configured.");
      return;
    }
    setLoading(true);
    setError(null);
    setMessage(null);

    const { error: err } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    setLoading(false);

    if (err) {
      setError(err.message);
    } else {
      setMessage("Password reset email sent. Check your inbox.");
    }
  };

  return (
    <div
      className="flex flex-col min-h-screen bg-[#0A0A0A] px-6 py-10"
      data-testid="forgot-password-screen"
    >
      {/* Header */}
      <div className="flex flex-col items-center mb-10">
        <div className="mb-4 w-12 h-12 rounded-2xl bg-[#181818] border border-[#27272A] flex items-center justify-center">
          <Scan size={22} className="text-[#2563EB]" />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-[#F8F8F8]">
          Reset password
        </h1>
        <p className="mt-1 text-sm text-[#A1A1AA]">
          Enter your email to receive a reset link
        </p>
      </div>

      {/* Error */}
      {error && (
        <div
          data-testid="forgot-error"
          className="mb-5 p-4 bg-[#EF4444]/10 border border-[#EF4444]/30 rounded-2xl text-[#EF4444] text-sm text-center"
        >
          {error}
        </div>
      )}

      {/* Success */}
      {message && (
        <div
          data-testid="forgot-message"
          className="mb-5 p-4 bg-[#22C55E]/10 border border-[#22C55E]/30 rounded-2xl text-[#22C55E] text-sm text-center"
        >
          {message}
        </div>
      )}

      {!message && (
        <form onSubmit={handleSubmit} className="space-y-3 mb-6">
          <div className="relative">
            <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#52525B]" />
            <input
              data-testid="forgot-email-input"
              type="email"
              placeholder="Email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full h-14 bg-[#111111] border border-[#27272A] rounded-2xl pl-11 pr-4 text-[#F8F8F8] placeholder-[#52525B] text-sm focus:outline-none focus:border-[#2563EB] transition-colors"
            />
          </div>

          <button
            data-testid="forgot-submit-button"
            type="submit"
            disabled={loading}
            className="w-full h-14 bg-[#2563EB] text-[#F8F8F8] rounded-2xl font-medium text-sm active:opacity-80 transition-opacity disabled:opacity-50"
          >
            {loading ? "Sending…" : "Send reset link"}
          </button>
        </form>
      )}

      <p className="text-center text-sm text-[#A1A1AA]">
        <Link
          data-testid="back-to-login-link"
          to="/login"
          className="text-[#2563EB] hover:underline"
        >
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
