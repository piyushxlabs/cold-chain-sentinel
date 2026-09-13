"use client";

import React from "react";
import {
  CheckCircle2,
  Clock,
  AlertTriangle,
  Radio,
  FileCheck2,
  Database,
  PhoneCall,
  Sparkles,
  GitBranch,
  Route,
  ShieldAlert,
  Archive,
} from "lucide-react";
import type { SentinelState } from "@/lib/types";
import { GRAPH_NODES, type NodeStatusRecord } from "@/lib/useIncidentStream";
import { EnrichmentSummaryCard } from "../cards/EnrichmentSummaryCard";
import { InterrogationResultCard } from "../cards/InterrogationResultCard";
import { RiskAssessmentCard } from "../cards/RiskAssessmentCard";
import { ActuationTransactionCard } from "../cards/ActuationTransactionCard";
import { EscalationAlertBanner } from "../cards/EscalationAlertBanner";

interface IncidentTimelineProps {
  state: SentinelState;
  nodeStatuses: Record<string, NodeStatusRecord>;
  escalationAlert?: {
    reasons: string[];
    severity: "P0" | "P1";
    alert_id: string;
  } | null;
  onFeedback?: (scoreName: string, value: any, comment?: string) => void;
}

const NODE_ICONS: Record<string, React.ElementType> = {
  ingress: Radio,
  enrichment: Database,
  call_interrogation: PhoneCall,
  compliance_review: Sparkles,
  decision_gate: GitBranch,
  autonomous_actuation: Route,
  escalation_failure: ShieldAlert,
  persistence_audit: Archive,
};

export const IncidentTimeline: React.FC<IncidentTimelineProps> = ({
  state,
  nodeStatuses,
  escalationAlert,
  onFeedback,
}) => {
  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Top Level Escalation Alert Banner if fired */}
      {escalationAlert && (
        <EscalationAlertBanner
          reasons={escalationAlert.reasons}
          severity={escalationAlert.severity}
          alertId={escalationAlert.alert_id}
        />
      )}

      {/* Vertical 8-Node StateGraph Timeline */}
      <div className="space-y-6 relative before:absolute before:inset-0 before:left-5 before:w-0.5 before:bg-slate-800">
        {GRAPH_NODES.map((node, index) => {
          const statusInfo = nodeStatuses[node.id] || { status: "pending" };
          const status = statusInfo.status;
          const Icon = NODE_ICONS[node.id] || Radio;

          const isPending = status === "pending";
          const isInProgress = status === "in-progress";
          const isComplete = status === "complete";
          const isFailed = status === "failed";

          return (
            <div key={node.id} className="relative flex items-start gap-4">
              {/* Step Icon Indicator */}
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 z-10 border transition ${
                  isComplete
                    ? "bg-slate-950 border-emerald-500 text-emerald-400 shadow-md shadow-emerald-950"
                    : isInProgress
                    ? "bg-slate-950 border-cyan-400 text-cyan-400 shadow-md shadow-cyan-950 animate-pulse"
                    : isFailed
                    ? "bg-slate-950 border-rose-500 text-rose-400 shadow-md shadow-rose-950"
                    : "bg-slate-950 border-slate-800 text-slate-600"
                }`}
              >
                <Icon className="w-5 h-5" />
              </div>

              {/* Node Card Content */}
              <div
                className={`flex-1 rounded-xl border p-4 transition space-y-3 shadow-lg ${
                  isInProgress
                    ? "bg-slate-900/90 border-cyan-500/60 ring-1 ring-cyan-500/20"
                    : isComplete
                    ? "bg-slate-900/60 border-slate-800"
                    : isFailed
                    ? "bg-rose-950/20 border-rose-900/60"
                    : "bg-slate-950/40 border-slate-800/40 opacity-50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-400 font-mono">0{index + 1}.</span>
                    <h3 className="text-sm font-bold text-slate-100 tracking-wide">{node.label}</h3>
                  </div>

                  <div className="flex items-center gap-2">
                    {statusInfo.timestamp && (
                      <span className="text-[10px] text-slate-500 font-mono">
                        {new Date(statusInfo.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </span>
                    )}
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                        isComplete
                          ? "bg-emerald-950 border border-emerald-800 text-emerald-300"
                          : isInProgress
                          ? "bg-cyan-950 border border-cyan-800 text-cyan-300 animate-pulse"
                          : isFailed
                          ? "bg-rose-950 border border-rose-800 text-rose-300"
                          : "bg-slate-800 text-slate-500"
                      }`}
                    >
                      {status}
                    </span>
                  </div>
                </div>

                {/* Nested Generative Cards depending on active node */}
                {node.id === "enrichment" && (isComplete || isInProgress) && (
                  <EnrichmentSummaryCard
                    tmsVerified={state.tms_verified}
                    eldHosMinutes={state.eld_hos_minutes_at_dispatch}
                    coldHub={state.nearest_verified_cold_hub}
                  />
                )}

                {node.id === "call_interrogation" && (isComplete || isInProgress) && (
                  <InterrogationResultCard
                    observations={state.physical_observations}
                    hosMinutes={state.driver_hos_minutes_remaining}
                    alarmCode={state.driver_reported_alarm_code}
                    callStatus={state.call_status}
                    confidence={state.call_evidence?.completion_confidence}
                    selectedOption={state.agreed_action}
                  />
                )}

                {node.id === "compliance_review" && (isComplete || isInProgress) && (
                  <RiskAssessmentCard
                    decision={state.compliance_review}
                    onFeedback={onFeedback}
                  />
                )}

                {node.id === "decision_gate" && isComplete && (
                  <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs space-y-1">
                    <span className="text-slate-400 font-medium">Deterministic Rule Resolution:</span>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-200 font-mono">
                        {state.agreed_action || "ESCALATE_TO_HUMAN_DISPATCH"}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                        {state.disposition || "EVALUATED"}
                      </span>
                    </div>
                  </div>
                )}

                {node.id === "autonomous_actuation" && (isComplete || isInProgress) && (
                  <ActuationTransactionCard
                    toolArtifacts={state.tool_artifacts}
                    disposition={state.disposition}
                  />
                )}

                {node.id === "persistence_audit" && isComplete && (
                  <div className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200 flex items-center gap-1.5">
                        <FileCheck2 className="w-4 h-4 text-emerald-400" />
                        FSMA Regulatory Deliverable Committed
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">Immutable Relational Write</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Triage record, voice call transcript pointer, OTel telemetry trace, and post-actuation leg manifests locked to PostgreSQL/SQLite storage.
                    </p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
