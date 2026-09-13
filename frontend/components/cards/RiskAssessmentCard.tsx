"use client";

import React, { useState } from "react";
import { Sparkles, ShieldCheck, AlertOctagon, ShieldAlert, Cpu, ThumbsUp, ThumbsDown, Star } from "lucide-react";
import type { ComplianceReviewDecision } from "@/lib/types";

interface RiskAssessmentCardProps {
  decision?: ComplianceReviewDecision | null;
  onFeedback?: (scoreName: string, value: any, comment?: string) => void;
}

export const RiskAssessmentCard: React.FC<RiskAssessmentCardProps> = ({ decision, onFeedback }) => {
  const [ratedThumbs, setRatedThumbs] = useState<boolean | null>(null);
  const [starRating, setStarRating] = useState<number | null>(null);

  if (!decision) {
    return (
      <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 text-slate-400 text-sm flex items-center gap-2">
        <Sparkles className="w-4 h-4 animate-spin text-purple-400" />
        <span>Awaiting Google Gemini cognitive compliance review...</span>
      </div>
    );
  }

  const riskBadgeStyles = {
    LOW: "bg-emerald-950/80 border-emerald-700 text-emerald-300",
    MODERATE: "bg-amber-950/80 border-amber-700 text-amber-300",
    HIGH: "bg-rose-950/80 border-rose-700 text-rose-300",
  }[decision.claim_risk_level] || "bg-slate-800 text-slate-300";

  const confidencePct = Math.round(decision.review_confidence * 100);

  const handleThumbs = (value: boolean) => {
    setRatedThumbs(value);
    onFeedback?.("user_thumbs", value);
  };

  const handleStar = (stars: number) => {
    setStarRating(stars);
    onFeedback?.("user_rating", stars);
  };

  return (
    <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-5 shadow-lg space-y-4">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-purple-400" />
          <h3 className="font-semibold text-slate-100 text-sm tracking-wide">
            Cognitive Compliance & Cargo Risk Assessment
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-3 py-1 rounded-full border font-bold ${riskBadgeStyles}`}>
            {decision.claim_risk_level} CLAIM RISK
          </span>
        </div>
      </div>

      {/* Model & Confidence Bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 text-slate-400">
            <Cpu className="w-3.5 h-3.5 text-purple-400" />
            <span>Evaluated by <strong className="text-slate-200 font-mono">{decision.reviewer_model}</strong></span>
          </div>
          <span className="font-mono text-slate-300 font-semibold">{confidencePct}% Confidence</span>
        </div>

        <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${
              confidencePct >= 75
                ? "bg-gradient-to-r from-emerald-500 to-teal-400"
                : confidencePct >= 50
                ? "bg-gradient-to-r from-amber-500 to-yellow-400"
                : "bg-gradient-to-r from-rose-500 to-red-400"
            }`}
            style={{ width: `${confidencePct}%` }}
          />
        </div>
      </div>

      {/* Prompt Injection Anomaly Chip */}
      {decision.suspected_injection && (
        <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-xs flex items-start gap-2">
          <AlertOctagon className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div>
            <strong className="block font-semibold">Prompt Injection / Scope Redirection Flagged (OWASP LLM01)</strong>
            <span>{decision.injection_evidence_note || "Driver utterance contained instruction override patterns."}</span>
          </div>
        </div>
      )}

      {/* Field-Grounded Reasoning Summary */}
      <div className="p-3.5 rounded-lg bg-slate-950/60 border border-slate-800/80 text-xs leading-relaxed text-slate-300 space-y-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
          Grounding Rationale & Evidence Citations
        </span>
        <p className="italic text-slate-200 font-sans">
          "{decision.reasoning_summary}"
        </p>
      </div>

      {/* Feedback & Quality Annotation Controls */}
      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
        <span className="text-[11px]">Rate AI Judgment Quality:</span>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <button
              onClick={() => handleThumbs(true)}
              className={`p-1.5 rounded hover:bg-slate-800 transition ${
                ratedThumbs === true ? "text-emerald-400 bg-slate-800" : "text-slate-400"
              }`}
              title="Accurate judgment"
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => handleThumbs(false)}
              className={`p-1.5 rounded hover:bg-slate-800 transition ${
                ratedThumbs === false ? "text-rose-400 bg-slate-800" : "text-slate-400"
              }`}
              title="Inaccurate judgment"
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-0.5">
            {[1, 2, 3, 4, 5].map((star) => (
              <button
                key={star}
                onClick={() => handleStar(star)}
                className={`p-1 hover:text-amber-400 transition ${
                  starRating && starRating >= star ? "text-amber-400" : "text-slate-600"
                }`}
              >
                <Star className="w-3.5 h-3.5 fill-current" />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
