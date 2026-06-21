import React, { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, Upload, Scan, LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

function readFileAsDataURL(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target.result);
    reader.readAsDataURL(file);
  });
}

export default function HomeScreen() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState(null);
  const { user, signOut } = useAuth();

  const handleSignOut = async () => {
    await signOut();
    navigate("/login", { replace: true });
  };

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsAnalyzing(true);
    setError(null);

    const imageDataUrl = await readFileAsDataURL(file);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${BACKEND_URL}/api/analyze`, {
        method: "POST",
        body: formData,
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || "Analysis failed");
      navigate("/results", { state: { result, imageDataUrl } });
    } catch (err) {
      setError(err.message || "Upload failed. Please try again.");
      setIsAnalyzing(false);
      // Reset input so same file can be re-selected
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
          ScreenSolve
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
          onClick={() => navigate("/camera")}
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
    </div>
  );
}
