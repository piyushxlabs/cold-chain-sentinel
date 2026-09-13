"use client";

import React, { useState } from "react";
import { OctagonX, Loader2 } from "lucide-react";

interface EmergencyCancelButtonProps {
  eventId: string | null;
  status?: string;
  disposition?: string | null;
  baseUrl?: string;
  onCancelled?: () => void;
}

export const EmergencyCancelButton: React.FC<EmergencyCancelButtonProps> = ({
  eventId,
  status,
  disposition,
  baseUrl = "http://localhost:8000",
  onCancelled,
}) => {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const isPostActuation =
    status === "completed" ||
    status === "cancelled" ||
    (disposition && disposition.startsWith("AUTONOMOUSLY_"));

  const handleCancel = async () => {
    if (!eventId || isPostActuation || loading) return;
    setLoading(true);
    setMessage(null);

    try {
      const res = await fetch(`${baseUrl}/sessions/${eventId}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "cancel", event_id: eventId }),
      });

      const data = await res.json();
      setMessage(data.reason);
      if (data.accepted) {
        onCancelled?.();
      }
    } catch (err) {
      setMessage("Failed to contact backend cancel endpoint");
    } finally {
      setLoading(false);
    }
  };

  if (!eventId) return null;

  return (
    <div className="space-y-1.5">
      <button
        onClick={handleCancel}
        disabled={isPostActuation || loading}
        className={`w-full py-2.5 px-4 rounded-xl text-xs font-bold flex items-center justify-center gap-2 transition shadow-md ${
          isPostActuation
            ? "bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700/50"
            : "bg-rose-600 hover:bg-rose-500 active:scale-98 text-white border border-rose-500 shadow-rose-950/50"
        }`}
        title={
          isPostActuation
            ? "Actuation committed or session closed — no naive rollback available"
            : "Cancel session immediately before actuation commits"
        }
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <OctagonX className="w-4 h-4" />
        )}
        <span>{isPostActuation ? "Cancel Unavailable (Committed)" : "Emergency Stop / Cancel Session"}</span>
      </button>

      {message && (
        <span className="text-[11px] block text-center text-slate-400 italic">
          {message}
        </span>
      )}
    </div>
  );
};
