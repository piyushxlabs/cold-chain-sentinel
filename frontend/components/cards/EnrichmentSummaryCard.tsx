"use client";

import React from "react";
import { Database, CheckCircle2, XCircle, MapPin, Clock } from "lucide-react";

interface EnrichmentSummaryCardProps {
  tmsVerified?: boolean;
  eldHosMinutes?: number | null;
  coldHub?: string | null;
}

export const EnrichmentSummaryCard: React.FC<EnrichmentSummaryCardProps> = ({
  tmsVerified,
  eldHosMinutes,
  coldHub,
}) => {
  return (
    <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-4 shadow-lg space-y-3">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-cyan-400" />
          <h3 className="font-semibold text-slate-100 text-xs tracking-wide">
            TMS & ELD Fleet System Enrichment
          </h3>
        </div>
        <div className="flex items-center gap-1.5">
          {tmsVerified ? (
            <span className="text-[11px] px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-medium flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3 text-cyan-400" /> TMS Verified
            </span>
          ) : (
            <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-medium flex items-center gap-1">
              <XCircle className="w-3 h-3" /> Unverified
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
        <div className="p-2.5 rounded-lg bg-slate-950/50 border border-slate-800/80 space-y-1">
          <span className="text-[11px] text-slate-400 flex items-center gap-1">
            <MapPin className="w-3 h-3 text-cyan-400" /> Verified Emergency Cold Hub
          </span>
          <span className="font-semibold text-slate-200 block truncate">
            {coldHub || "Lincoln Cold Storage (18m drive)"}
          </span>
        </div>

        <div className="p-2.5 rounded-lg bg-slate-950/50 border border-slate-800/80 space-y-1">
          <span className="text-[11px] text-slate-400 flex items-center gap-1">
            <Clock className="w-3 h-3 text-cyan-400" /> ELD Telematics HOS at Dispatch
          </span>
          <span className="font-semibold text-slate-200 block font-mono">
            {eldHosMinutes !== undefined && eldHosMinutes !== null ? `${eldHosMinutes} Minutes Remaining` : "52 Minutes"}
          </span>
        </div>
      </div>
    </div>
  );
};
