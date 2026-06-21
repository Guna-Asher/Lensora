/**
 * RegisterScreen — email/password sign up.
 *
 * On success with email confirmation enabled: shows confirmation message.
 * On success without email confirmation: session is created immediately and
 * AuthContext redirects the user to the app.
 */
import React, { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Scan, Mail, Lock } from "lucide-react";
import { supabase } from "../lib/supabaseClient";
import { useAuth } from "../context/AuthContext";

export default function RegisterScreen() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  const handleSignUp = async (e) => {
    e.preventDefault();
    if (!supabase) {
      setError("Authentication is not configured. Set REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY.");
      return;
    }
    setLoading(true);
    setError(null);
    setMessage(null);

    const { data, error: err } = await supabase.auth.signUp({ email, password });
    setLoading(false);

    if (err) {
      setError(err.message);
      return;
    }

    if (data.user && !data.session) {
      // Email confirmation required
      setMessage("Check your email for a confirmation link to complete sign up.");
    }
    // If session is returned immediately, AuthContext will redirect via useEffect above
  };

  return (
    <div
      className="flex flex-col min-h-screen bg-[#0A0A0A] px-6 py-10"
      data-testid="register-screen"
    >
      {/* Header */}
      <div className="flex flex-col items-center mb-10">
        <div className="mb-4 w-12 h-12 rounded-2xl bg-[#181818] border border-[#27272A] flex items-center justify-center">
          <Scan size={22} className="text-[#2563EB]" />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-[#F8F8F8]">
          Create account
        </h1>
        <p className="mt-1 text-sm text-[#A1A1AA]">to get started with ScreenSolve</p>
      </div>

      {/* Error */}
      {error && (
        <div
          data-testid="register-error"
          className="mb-5 p-4 bg-[#EF4444]/10 border border-[#EF4444]/30 rounded-2xl text-[#EF4444] text-sm text-center"
        >
          {error}
        </div>
      )}

      {/* Success */}
      {message && (
        <div
          data-testid="register-message"
          className="mb-5 p-4 bg-[#22C55E]/10 border border-[#22C55E]/30 rounded-2xl text-[#22C55E] text-sm text-center"
        >
          {message}
        </div>
      )}

      {/* Sign up form */}
      {!message && (
        <form onSubmit={handleSignUp} className="space-y-3 mb-8">
          <div className="relative">
            <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#52525B]" />
            <input
              data-testid="register-email-input"
              type="email"
              placeholder="Email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full h-14 bg-[#111111] border border-[#27272A] rounded-2xl pl-11 pr-4 text-[#F8F8F8] placeholder-[#52525B] text-sm focus:outline-none focus:border-[#2563EB] transition-colors"
            />
          </div>

          <div className="relative">
            <Lock size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#52525B]" />
            <input
              data-testid="register-password-input"
              type="password"
              placeholder="Password (min 6 characters)"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              className="w-full h-14 bg-[#111111] border border-[#27272A] rounded-2xl pl-11 pr-4 text-[#F8F8F8] placeholder-[#52525B] text-sm focus:outline-none focus:border-[#2563EB] transition-colors"
            />
          </div>

          <button
            data-testid="register-submit-button"
            type="submit"
            disabled={loading}
            className="w-full h-14 bg-[#2563EB] text-[#F8F8F8] rounded-2xl font-medium text-sm active:opacity-80 transition-opacity disabled:opacity-50"
          >
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>
      )}

      {/* Sign in link */}
      <p className="text-center text-sm text-[#A1A1AA]">
        Already have an account?{" "}
        <Link
          data-testid="login-link"
          to="/login"
          className="text-[#2563EB] hover:underline"
        >
          Sign in
        </Link>
      </p>
    </div>
  );
}
