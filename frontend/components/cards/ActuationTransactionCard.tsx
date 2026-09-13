"use client";

import React from "react";
import { Route, Warehouse, MessageSquare, Wrench, CheckCircle2, XCircle, Clock } from "lucide-react";
import type { ToolCallResult } from "@/lib/types";

interface ActuationTransactionCardProps {
  toolArtifacts?: Record<string, ToolCallResult>;
  disposition?: string | null;
}

export const ActuationTransactionCard: React.FC<ActuationTransactionCardProps> = ({
  toolArtifacts = {},
  disposition,
}) => {
  const legs = [
    {
      key: "routing_mutate_route",
      title: "Fleet Route Mutation",
      icon: Route,
      description: "Emergency diversion route pushed to in-cab GPS navigation",
    },
    {
      key: "warehouse_reserve_dock",
      title: "Cold Hub Dock Reservation",
      icon: Warehouse,
      description: "Fast-track cross-dock bay reserved with pre-cooled intake",
    },
    {
      key: "maintenance_dispatch_ticket",
      title: "Roadside Service Ticket",
      icon: Wrench,
      description: "Mobile refrigeration technician dispatched to mile marker",
    },
    {
      key: "sms_send_confirmation",
      title: "Driver Confirmation SMS",
      icon: MessageSquare,
      description: "Automated turn-by-turn and dock assignment sent to driver",
    },
  ];

  // Filter legs relevant to current session
  const relevantLegs = legs.filter(
    (l) => toolArtifacts[l.key] || (l.key !== "maintenance_dispatch_ticket" && disposition === "AUTONOMOUSLY_DIVERTED")
  );

  return (
    <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-5 shadow-lg space-y-4">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <Route className="w-5 h-5 text-teal-400" />
          <h3 className="font-semibold text-slate-100 text-sm tracking-wide">
            Autonomous Actuation Transaction (Batched MCP Legs)
          </h3>
        </div>
        <span className="text-xs px-2.5 py-1 rounded-full bg-teal-950/80 border border-teal-800 text-teal-300 font-medium">
          Committed Atomic Disposition
        </span>
      </div>

      <div className="space-y-2.5">
        {relevantLegs.map((leg) => {
          const artifact = toolArtifacts[leg.key];
          const isSuccess = artifact?.status === "SUCCESS";
          const isFailed = artifact?.status === "FAILED";
          const Icon = leg.icon;

          return (
            <div
              key={leg.key}
              className={`p-3 rounded-lg border transition flex items-center justify-between ${
                isSuccess
                  ? "bg-slate-950/60 border-teal-900/60 text-slate-200"
                  : isFailed
                  ? "bg-rose-950/30 border-rose-900/60 text-rose-200"
                  : "bg-slate-950/30 border-slate-800/40 text-slate-400"
              }`}
            >
              <div className="flex items-center gap-3">
                <div
                  className={`p-2 rounded-md ${
                    isSuccess ? "bg-teal-950 text-teal-300" : "bg-slate-800 text-slate-400"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div>
                  <span className="font-semibold text-xs text-slate-200 block">{leg.title}</span>
                  <span className="text-[11px] text-slate-400">{leg.description}</span>
                </div>
              </div>

              <div>
                {isSuccess ? (
                  <span className="flex items-center gap-1.5 text-xs text-teal-400 font-medium">
                    <CheckCircle2 className="w-4 h-4" /> Done
                  </span>
                ) : isFailed ? (
                  <span className="flex items-center gap-1.5 text-xs text-rose-400 font-medium">
                    <XCircle className="w-4 h-4" /> Failed
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-xs text-slate-500 font-medium">
                    <Clock className="w-3.5 h-3.5" /> Pending
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
