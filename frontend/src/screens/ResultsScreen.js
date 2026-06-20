import React, { useState, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Copy,
  BookOpen,
  RotateCcw,
  CheckCircle,
  AlertCircle,
  Check,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

function dataURLtoBlob(dataURL) {
  const [header, data] = dataURL.split(",");
  const mime = header.match(/:(.*?);/)[1];
  const binary = atob(data);
  const arr = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

function AnswerItem({ line, index }) {
  const isExplanation =
    line.trimStart().startsWith("→") ||
    line.startsWith("   ") ||
    line.startsWith("\t");

  const isCode = line.includes("```");

  const delay = `${index * 60}ms`;

  if (isExplanation) {
    return (
      <p
        className="text-sm text-[#A1A1AA] pl-5 leading-relaxed answer-item"
        style={{ animationDelay: delay }}
        data-testid="answer-explanation"
      >
        {line.trim()}
      </p>
    );
  }

  if (isCode) {
    return (
      <code
        className="block font-mono text-sm text-[#A1A1AA] bg-[#111111] border border-[#27272A] rounded-lg px-3 py-2 answer-item"
        style={{ animationDelay: delay }}
        data-testid="code-line"
      >
        {line}
      </code>
    );
  }

  return (
    <p
      className="text-2xl font-medium tracking-tight text-[#F8F8F8] leading-snug answer-item"
      style={{ animationDelay: delay }}
      data-testid="answer-line"
    >
      {line}
    </p>
  );
}

export default function ResultsScreen() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const answersRef = useRef(null);

  const [sheetVisible, setSheetVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isExplaining, setIsExplaining] = useState(false);
  const [explanations, setExplanations] = useState(null);
  const [explainError, setExplainError] = useState(null);

  const result = state?.result;
  const imageDataUrl = state?.imageDataUrl;

  useEffect(() => {
    if (!result) {
      navigate("/", { replace: true });
      return;
    }
    const t1 = setTimeout(() => setSheetVisible(true), 50);
    const t2 = setTimeout(() => {
      answersRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 400);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [result, navigate]);

  const copyAll = async () => {
    const text = explanations || result?.answers || "";
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const handleExplain = async () => {
    if (!imageDataUrl || isExplaining || explanations) return;
    setIsExplaining(true);
    setExplainError(null);

    const blob = dataURLtoBlob(imageDataUrl);
    const formData = new FormData();
    formData.append("file", blob, "image.jpg");
    formData.append("explain", "true");

    try {
      const res = await fetch(`${BACKEND_URL}/api/analyze`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to get explanations");
      setExplanations(data.answers);
    } catch (err) {
      setExplainError(err.message || "Could not load explanations.");
    } finally {
      setIsExplaining(false);
    }
  };

  const displayText = explanations || result?.answers || "";
  const answerLines = displayText.split("\n").filter((l) => l.trim());

  if (!result) return null;

  return (
    <div
      className="fixed inset-0 bg-[#0A0A0A] flex flex-col"
      data-testid="results-screen"
    >
      {/* Background image (dimmed) */}
      {imageDataUrl && (
        <div className="absolute inset-0">
          <img
            src={imageDataUrl}
            alt="Analyzed screen"
            className="w-full h-full object-cover opacity-15"
            data-testid="result-image-preview"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-[#0A0A0A]/70 via-transparent to-[#0A0A0A]" />
        </div>
      )}

      {/* Bottom Sheet */}
      <div
        data-testid="results-bottom-sheet"
        className={`
          absolute bottom-0 left-0 right-0 z-10
          bg-[#181818] rounded-t-3xl border-t border-[#27272A]
          shadow-[0_-8px_40px_rgba(0,0,0,0.7)]
          transition-transform duration-300 ease-out
          max-h-[88vh] flex flex-col
          ${sheetVisible ? "translate-y-0" : "translate-y-full"}
        `}
      >
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-2 shrink-0">
          <div className="w-10 h-1 bg-[#27272A] rounded-full" />
        </div>

        {/* Header */}
        <div className="px-6 pb-4 flex items-start justify-between shrink-0">
          <div>
            <div className="flex items-center gap-2 mb-1">
              {result.screen_detected ? (
                <CheckCircle size={14} className="text-[#22C55E]" />
              ) : (
                <AlertCircle size={14} className="text-[#A1A1AA]" />
              )}
              <span className="text-xs text-[#A1A1AA] uppercase tracking-widest">
                {result.screen_detected ? "Screen Detected" : "Full Image"}
              </span>
            </div>
            <p className="text-xs text-[#A1A1AA]" data-testid="result-meta">
              {result.model_used?.split("/").pop() ?? "AI"} &middot;{" "}
              {result.processing_time_ms}ms
              {result.verification_used && " · Verified"}
            </p>
          </div>

          {explanations && (
            <span className="text-xs text-[#2563EB] bg-[#2563EB]/10 px-2 py-1 rounded-full">
              Explained
            </span>
          )}
        </div>

        {/* Answers list */}
        <div
          ref={answersRef}
          className="flex-1 overflow-y-auto px-6 pb-4 space-y-2 scrollbar-hide"
          data-testid="answers-container"
        >
          {answerLines.length === 0 ? (
            <p
              className="text-[#A1A1AA] text-center py-10"
              data-testid="no-answers"
            >
              No answers could be extracted.
            </p>
          ) : (
            answerLines.map((line, i) => (
              <AnswerItem key={i} line={line} index={i} />
            ))
          )}

          {explainError && (
            <p
              className="text-[#EF4444] text-sm text-center py-2"
              data-testid="explain-error"
            >
              {explainError}
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div
          className="px-6 pb-10 pt-3 space-y-3 border-t border-[#27272A] shrink-0"
          data-testid="result-actions"
        >
          <div className="grid grid-cols-2 gap-3">
            <button
              data-testid="copy-all-button"
              onClick={copyAll}
              className="h-12 bg-[#111111] border border-[#27272A] text-[#F8F8F8] rounded-xl font-medium flex items-center justify-center gap-2 active:opacity-70 transition-opacity duration-150"
            >
              {copied ? (
                <Check size={16} className="text-[#22C55E]" />
              ) : (
                <Copy size={16} />
              )}
              <span className={copied ? "text-[#22C55E]" : ""}>
                {copied ? "Copied!" : "Copy All"}
              </span>
            </button>

            <button
              data-testid="explain-button"
              onClick={handleExplain}
              disabled={isExplaining || !!explanations || !imageDataUrl}
              className="h-12 bg-[#111111] border border-[#27272A] text-[#F8F8F8] rounded-xl font-medium flex items-center justify-center gap-2 active:opacity-70 transition-opacity duration-150 disabled:opacity-50"
            >
              {isExplaining ? (
                <div className="w-4 h-4 rounded-full border border-[#2563EB] border-t-transparent animate-spin" />
              ) : (
                <BookOpen size={16} />
              )}
              {isExplaining ? "Loading..." : explanations ? "Explained" : "Explain"}
            </button>
          </div>

          <button
            data-testid="retake-button"
            onClick={() => navigate("/camera")}
            className="w-full h-12 bg-[#2563EB] text-white rounded-xl font-medium flex items-center justify-center gap-2 active:opacity-80 transition-opacity duration-150"
          >
            <RotateCcw size={16} />
            Retake Photo
          </button>

          <button
            data-testid="home-button"
            onClick={() => navigate("/")}
            className="w-full h-10 text-[#A1A1AA] text-sm font-medium flex items-center justify-center gap-2 active:opacity-70 transition-opacity duration-150"
          >
            Back to Home
          </button>
        </div>
      </div>
    </div>
  );
}
