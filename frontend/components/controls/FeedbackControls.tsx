"use client";

import React, { useState } from "react";
import { ThumbsUp, ThumbsDown, Star, MessageSquare } from "lucide-react";

interface FeedbackControlsProps {
  onScoreSubmitted?: (name: string, value: any, comment?: string) => void;
}

export const FeedbackControls: React.FC<FeedbackControlsProps> = ({ onScoreSubmitted }) => {
  const [thumbs, setThumbs] = useState<boolean | null>(null);
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = () => {
    if (thumbs !== null) onScoreSubmitted?.("user_thumbs", thumbs, comment);
    if (rating !== null) onScoreSubmitted?.("user_rating", rating, comment);
    setSubmitted(true);
  };

  return (
    <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 space-y-3 text-xs text-slate-300">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <span className="font-semibold text-slate-200">Incident Telemetry Feedback (Langfuse)</span>
        {submitted && <span className="text-emerald-400 font-medium">Logged ✓</span>}
      </div>

      <div className="flex items-center justify-between">
        <span className="text-slate-400">Resolution Accuracy:</span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setThumbs(true)}
            className={`p-1.5 rounded hover:bg-slate-800 transition ${
              thumbs === true ? "text-emerald-400 bg-slate-800" : "text-slate-500"
            }`}
          >
            <ThumbsUp className="w-4 h-4" />
          </button>
          <button
            onClick={() => setThumbs(false)}
            className={`p-1.5 rounded hover:bg-slate-800 transition ${
              thumbs === false ? "text-rose-400 bg-slate-800" : "text-slate-500"
            }`}
          >
            <ThumbsDown className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-slate-400">Overall Rating:</span>
        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((s) => (
            <button
              key={s}
              onClick={() => setRating(s)}
              className={`p-1 transition ${
                rating && rating >= s ? "text-amber-400" : "text-slate-600"
              }`}
            >
              <Star className="w-3.5 h-3.5 fill-current" />
            </button>
          ))}
        </div>
      </div>

      {!submitted && (thumbs !== null || rating !== null) && (
        <button
          onClick={handleSubmit}
          className="w-full py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition"
        >
          Submit Telemetry Annotation
        </button>
      )}
    </div>
  );
};
