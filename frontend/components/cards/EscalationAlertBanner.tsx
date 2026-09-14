"use client";

import React from "react";
import { AlertTriangle, BellRing, PhoneCall, ShieldAlert, UserX } from "lucide-react";

interface EscalationAlertBannerProps {
  reasons: string[];
  severity?: "P0" | "P1";
  alertId?: string;
}

export const EscalationAlertBanner: React.FC<EscalationAlertBannerProps> = ({
  reasons,
  severity = "P0",
  alertId = "alrt_live",
}) => {
  const uniqueReasons = Array.from(new Set(reasons || []));
  if (uniqueReasons.length === 0) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="rounded-xl bg-gradient-to-r from-rose-950/95 via-red-900/90 to-rose-950/95 border-2 border-rose-600 p-5 shadow-2xl text-rose-100 space-y-3 animate-pulse-slow"
    >
      <div className="flex items-center justify-between border-b border-rose-800/80 pb-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-rose-600 text-white shadow-md">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs px-2 py-0.5 rounded bg-rose-500 text-white font-extrabold tracking-wider">
                {severity} DISPATCH ALERT
              </span>
              <span className="text-xs font-mono text-rose-300">ID: {alertId}</span>
            </div>
            <h2 className="text-base font-bold text-white tracking-wide mt-0.5">
              Autonomous Divert Blocked — Human Dispatch Intervention Required
            </h2>
          </div>
        </div>

        <div className="hidden sm:flex items-center gap-1.5 text-xs text-rose-300 bg-rose-950/80 px-3 py-1.5 rounded-lg border border-rose-800">
          <BellRing className="w-4 h-4 text-rose-400" />
          <span>Notified: Human Operations & Claims</span>
        </div>
      </div>

      <div className="space-y-1.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-rose-300 block">
          Triggered Safety / Regulatory Escalation Reasons:
        </span>
        <ul className="space-y-1 text-xs">
          {uniqueReasons.map((reason, idx) => (
            <li key={idx} className="flex items-start gap-2 bg-rose-950/60 p-2 rounded border border-rose-800/50">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
              <span className="font-medium text-rose-100">{reason}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="text-[11px] text-rose-300/80 flex items-center justify-between pt-1">
        <span>Notify-and-Terminate: Graph reached terminal persistence. Actuation tools locked.</span>
        <span>Action required out-of-band via TMS / Dispatch radio.</span>
      </div>
    </div>
  );
};
