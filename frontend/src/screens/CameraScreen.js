import React, { useRef, useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { X, ScanSearch } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function CameraScreen() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const navigate = useNavigate();

  const [cameraReady, setCameraReady] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [error, setError] = useState(null);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const startCamera = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        streamRef.current = stream;
        await videoRef.current.play();
        setCameraReady(true);
      }
    } catch {
      setError(
        "Camera access denied. Please allow camera permission or use the Upload option."
      );
    }
  }, []);

  useEffect(() => {
    startCamera();
    return stopCamera;
  }, [startCamera, stopCamera]);

  const capture = useCallback(async () => {
    if (!cameraReady || isCapturing) return;
    setIsCapturing(true);

    const video = videoRef.current;
    const canvas = canvasRef.current;
    const w = video.videoWidth || 1280;
    const h = video.videoHeight || 720;
    canvas.width = w;
    canvas.height = h;
    canvas.getContext("2d").drawImage(video, 0, 0, w, h);

    const imageDataUrl = canvas.toDataURL("image/jpeg", 0.92);
    stopCamera();

    canvas.toBlob(
      async (blob) => {
        const formData = new FormData();
        formData.append("file", blob, "capture.jpg");

        try {
          const res = await fetch(`${BACKEND_URL}/api/analyze`, {
            method: "POST",
            body: formData,
          });
          const result = await res.json();
          if (!res.ok) throw new Error(result.detail || "Analysis failed");
          navigate("/results", { state: { result, imageDataUrl } });
        } catch (err) {
          setIsCapturing(false);
          setError(err.message || "Analysis failed. Please try again.");
          startCamera();
        }
      },
      "image/jpeg",
      0.92
    );
  }, [cameraReady, isCapturing, navigate, stopCamera, startCamera]);

  return (
    <div
      className="fixed inset-0 bg-black flex flex-col"
      data-testid="camera-screen"
    >
      {/* Live video */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="absolute inset-0 w-full h-full object-cover"
        data-testid="camera-video"
      />
      <canvas ref={canvasRef} className="hidden" />

      {/* Viewfinder guide */}
      {!isCapturing && (
        <div
          className="absolute inset-0 pointer-events-none z-10"
          data-testid="viewfinder-overlay"
        >
          {/* Dimming regions */}
          <div className="absolute top-0 left-0 right-0 bg-black/55" style={{ height: "17%" }} />
          <div className="absolute bottom-0 left-0 right-0 bg-black/55" style={{ height: "27%" }} />
          <div className="absolute bg-black/55" style={{ top: "17%", bottom: "27%", left: 0, width: "7%" }} />
          <div className="absolute bg-black/55" style={{ top: "17%", bottom: "27%", right: 0, width: "7%" }} />

          {/* Guide label */}
          <p
            className="absolute left-0 right-0 text-center text-xs text-[#A1A1AA] uppercase tracking-[0.2em]"
            style={{ top: "calc(17% - 24px)" }}
          >
            Align screen within frame
          </p>

          {/* Corner brackets */}
          <div
            className="absolute"
            style={{ top: "17%", left: "7%", right: "7%", bottom: "27%" }}
          >
            <div className="absolute top-0 left-0 w-8 h-8 border-t-2 border-l-2 border-[#2563EB]" />
            <div className="absolute top-0 right-0 w-8 h-8 border-t-2 border-r-2 border-[#2563EB]" />
            <div className="absolute bottom-0 left-0 w-8 h-8 border-b-2 border-l-2 border-[#2563EB]" />
            <div className="absolute bottom-0 right-0 w-8 h-8 border-b-2 border-r-2 border-[#2563EB]" />

            {/* Scan line hint */}
            <div className="absolute left-8 right-8 top-1/2 h-px bg-[#2563EB]/20" />
          </div>
        </div>
      )}

      {/* Analyzing overlay */}
      {isCapturing && (
        <div
          className="absolute inset-0 bg-black/85 flex flex-col items-center justify-center z-50 fade-in"
          data-testid="analyzing-overlay"
        >
          <div className="mb-4 w-16 h-16 rounded-2xl bg-[#181818] border border-[#27272A] flex items-center justify-center">
            <ScanSearch size={28} className="text-[#2563EB]" />
          </div>
          <div className="w-12 h-12 rounded-full border-2 border-[#2563EB] border-t-transparent animate-spin mb-5" />
          <p className="text-[#F8F8F8] font-medium text-lg">Analyzing screen...</p>
          <p className="text-[#A1A1AA] text-sm mt-2">Detecting and extracting answers</p>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div
          className="absolute inset-x-4 bottom-36 bg-[#EF4444]/10 border border-[#EF4444]/30 rounded-2xl p-4 z-30 fade-in"
          data-testid="camera-error"
        >
          <p className="text-[#EF4444] text-sm text-center">{error}</p>
        </div>
      )}

      {/* Camera loading */}
      {!cameraReady && !error && (
        <div
          className="absolute inset-0 bg-black flex items-center justify-center z-20"
          data-testid="camera-loading"
        >
          <div className="w-8 h-8 rounded-full border-2 border-[#2563EB] border-t-transparent animate-spin" />
        </div>
      )}

      {/* Controls */}
      <div
        className="absolute bottom-0 left-0 right-0 px-8 pb-12 pt-4 flex justify-between items-center z-20"
        data-testid="camera-controls"
      >
        {/* Back */}
        <button
          data-testid="camera-back-button"
          onClick={() => { stopCamera(); navigate("/"); }}
          className="w-12 h-12 rounded-full bg-black/50 border border-white/20 flex items-center justify-center text-white active:opacity-70 transition-opacity duration-150"
        >
          <X size={20} />
        </button>

        {/* Shutter */}
        <button
          data-testid="capture-shutter-button"
          onClick={capture}
          disabled={!cameraReady || isCapturing}
          className="w-20 h-20 rounded-full bg-white border-4 border-[#1a1a1a] flex items-center justify-center active:scale-95 transition-transform duration-150 disabled:opacity-40"
          aria-label="Capture photo"
        >
          <div className="w-14 h-14 rounded-full bg-[#2563EB]" />
        </button>

        {/* Symmetry spacer */}
        <div className="w-12 h-12" />
      </div>
    </div>
  );
}
