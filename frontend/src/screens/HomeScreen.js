import React, { useRef, useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Camera, Upload, Scan, LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const ANON_KEY = "lensora_anon_id";

function getOrCreateAnonId() {
  let id = localStorage.getItem(ANON_KEY);
  if (!id) {
    const r = () => Math.random().toString(36).slice(2, 9);
    id = `anon_${r()}${r()}`;
    localStorage.setItem(ANON_KEY, id);
  }
  return id;
}

function readFileAsDataURL(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target.result);
    reader.readAsDataURL(file);
  });
}

export default function HomeScreen() {
  const navigate = useNavigate();
  const location = useLocation();
  const fileInputRef = useRef(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState(null);
  const [showSignupWall, setShowSignupWall] = useState(false);
  const [scanStatus, setScanStatus] = useState(null);
  const { user, signOut } = useAuth();

  const handleSignOut = async () => {
    await signOut();
    navigate("/login", { replace: true });
  };

  // Fetch anonymous scan status on mount (only for unauthenticated users)
  useEffect(() => {
    if (user) { setScanStatus(null); return; }
    const anonId = getOrCreateAnonId();
    fetch(`${BACKEND_URL}/api/anonymous/check?anonymous_id=${encodeURIComponent(anonId)}`)
      .then((r) => r.json())
      .then((data) => setScanStatus(data))
      .catch(() => setScanStatus({ can_scan: true }));
  }, [user]);

  // Show signup wall if CameraScreen navigated back with flag
  useEffect(() => {
    if (location.state?.showSignupWall) {
      setShowSignupWall(true);
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [location.state, location.pathname, navigate]);

  const handleCameraClick = () => {
    if (!user && scanStatus && !scanStatus.can_scan) {
      setShowSignupWall(true);
      return;
    }
    navigate("/camera");
  };

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // UX pre-check (backend also enforces independently)
    if (!user && scanStatus && !scanStatus.can_scan) {
      setShowSignupWall(true);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setIsAnalyzing(true);
    setError(null);

    const imageDataUrl = await readFileAsDataURL(file);
    const formData = new FormData();
    formData.append("file", file);
    if (!user) formData.append("anonymous_id", getOrCreateAnonId());

    try {
      const res = await fetch(`${BACKEND_URL}/api/analyze`, {
        method: "POST",
        body: formData,
      });
      const result = await res.json();

      if (res.status === 403) {
        setScanStatus((prev) => ({ ...(prev || {}), can_scan: false }));
        setShowSignupWall(true);
        setIsAnalyzing(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
        return;
      }

      if (!res.ok) throw new Error(result.detail || "Analysis failed");

      // Optimistically update local scan status
      if (!user) {
        setScanStatus((prev) =>
          prev
            ? {
                ...prev,
                analysis_count: (prev.analysis_count || 0) + 1,
                analyses_remaining: Math.max(0, (prev.analyses_remaining ?? 1) - 1),
                can_scan: (prev.analyses_remaining ?? 1) > 1,
              }
            : null
        );
      }

      navigate("/results", { state: { result, imageDataUrl } });
    } catch (err) {
      setError(err.message || "Upload failed. Please try again.");
      setIsAnalyzing(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div
      className="flex flex-col min-h-screen p-8 bg-[#0A0A0A]"
      data-testid="home-screen"
    >
      {/* User bar */}
      {user && (
        <div
          data-testid="user-bar"
          className="flex items-center justify-between mb-2"
        >
          <span
            data-testid="user-email"
            className="text-xs text-[#52525B] truncate max-w-[200px]"
          >
            {user.email}
          </span>
          <button
            data-testid="sign-out-button"
            onClick={handleSignOut}
            className="flex items-center gap-1.5 text-xs text-[#52525B] hover:text-[#F8F8F8] transition-colors px-2 py-1 rounded-lg hover:bg-[#181818]"
            aria-label="Sign out"
          >
            <LogOut size={13} />
            Sign out
          </button>
        </div>
      )}
      {/* Hero section */}
      <div className="flex-1 flex flex-col items-center justify-center text-center">
        <div className="mb-6 w-16 h-16 rounded-2xl bg-[#181818] border border-[#27272A] flex items-center justify-center">
          <Scan size={28} className="text-[#2563EB]" />
        </div>

        <p className="text-xs uppercase tracking-[0.3em] text-[#A1A1AA] mb-3">
          Vision AI
        </p>

        <h1
          data-testid="app-title"
          className="text-4xl font-semibold tracking-tighter text-[#F8F8F8] mb-4"
        >
          Lensora
        </h1>

        <p className="text-base text-[#A1A1AA] max-w-[220px] leading-relaxed">
          Instant Answers From Screens & Screenshots
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div
          data-testid="upload-error"
          className="mb-4 p-4 bg-[#EF4444]/10 border border-[#EF4444]/30 rounded-xl text-[#EF4444] text-sm text-center fade-in"
        >
          {error}
        </div>
      )}

      {/* Action buttons */}
      <div className="w-full space-y-3 pb-4" data-testid="action-buttons">
        <button
          data-testid="capture-button"
          onClick={handleCameraClick}
          disabled={isAnalyzing}
          className="w-full h-14 bg-[#2563EB] text-[#F8F8F8] rounded-2xl font-medium flex items-center justify-center gap-3 active:opacity-80 transition-opacity duration-150 disabled:opacity-50"
        >
          <Camera size={20} />
          Capture Screen
        </button>

        <button
          data-testid="upload-button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isAnalyzing}
          className="w-full h-14 bg-[#111111] border border-[#27272A] text-[#F8F8F8] rounded-2xl font-medium flex items-center justify-center gap-3 active:opacity-80 transition-opacity duration-150 disabled:opacity-50"
        >
          <Upload size={20} />
          Upload Screenshot
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/jpg"
          className="hidden"
          onChange={handleUpload}
          data-testid="file-input"
        />
      </div>

      {/* Loading overlay */}
      {isAnalyzing && (
        <div
          className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 fade-in"
          data-testid="loading-overlay"
        >
          <div className="bg-[#181818] rounded-2xl p-8 flex flex-col items-center space-y-4 border border-[#27272A] mx-6">
            <div className="w-10 h-10 rounded-full border-2 border-[#2563EB] border-t-transparent animate-spin" />
            <p className="text-[#F8F8F8] font-medium">Analyzing screen...</p>
            <p className="text-[#A1A1AA] text-sm text-center">
              Detecting content and extracting answers
            </p>
          </div>
        </div>
      )}

      {/* Signup wall — shown when free scan limit is reached */}
      {showSignupWall && (
        <div
          data-testid="signup-wall"
          className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-end z-50"
          onClick={() => setShowSignupWall(false)}
        >
          <div
            className="w-full bg-[#181818] rounded-t-3xl border-t border-[#27272A] px-8 pb-12 pt-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-10 h-1 bg-[#27272A] rounded-full mx-auto mb-6" />
            <div className="mb-4 w-12 h-12 rounded-2xl bg-[#2563EB]/10 border border-[#2563EB]/30 flex items-center justify-center">
              <Scan size={22} className="text-[#2563EB]" />
            </div>
            <h2
              data-testid="signup-wall-heading"
              className="text-xl font-semibold text-[#F8F8F8] mb-2"
            >
              You've used all free scans.
            </h2>
            <p className="text-sm text-[#A1A1AA] mb-8 leading-relaxed">
              Create a free account to continue scanning without limits.
            </p>
            <div className="space-y-3">
              <button
                data-testid="signup-wall-register-button"
                onClick={() => navigate("/register")}
                className="w-full h-14 bg-[#2563EB] text-white rounded-2xl font-medium text-sm active:opacity-80 transition-opacity"
              >
                Create Free Account
              </button>
              <button
                data-testid="signup-wall-login-button"
                onClick={() => navigate("/login")}
                className="w-full h-14 bg-[#111111] border border-[#27272A] text-[#F8F8F8] rounded-2xl font-medium text-sm active:opacity-80 transition-opacity"
              >
                Login
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
