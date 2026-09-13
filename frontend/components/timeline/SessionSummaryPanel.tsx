"use client";

import React from "react";
import { Truck, Thermometer, ShieldAlert, PackageCheck, UserCheck, MapPin, Gauge } from "lucide-react";
import type { SentinelState } from "@/lib/types";
import { EmergencyCancelButton } from "../controls/EmergencyCancelButton";

interface SessionSummaryPanelProps {
  state: SentinelState;
  onCancelled?: () => void;
  baseUrl?: string;
}

export const SessionSummaryPanel: React.FC<SessionSummaryPanelProps> = ({
  state,
  onCancelled,
  baseUrl,
}) => {
  if (!state.event_id) {
    return (
      <div className="w-full lg:w-80 p-5 bg-slate-900/70 border-l border-slate-800 text-slate-500 text-xs text-center flex items-center justify-center">
        Select an incident to view load specifications.
      </div>
    );
  }

  const manifest = state.cargo_manifest;
  const currentTemp = state.current_temp_f;
  const setpointTemp = state.setpoint_temp_f;
  const delta = currentTemp !== undefined && setpointTemp !== undefined ? (currentTemp - setpointTemp).toFixed(1) : null;

  return (
    <aside className="w-full lg:w-80 flex flex-col bg-slate-900/70 border-l border-slate-800 p-5 space-y-5 overflow-y-auto">
      {/* Excursion Temperature Gauge */}
      <div className="rounded-xl bg-slate-950 border border-slate-800 p-4 space-y-3 shadow-md">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
            <Thermometer className="w-4 h-4 text-rose-400" /> Temperature Telematics
          </span>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-rose-950 border border-rose-800 text-rose-300 font-bold">
            {delta !== null ? `+${delta}°F EXCURSION` : "MONITORING"}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-center">
          <div className="p-2 rounded bg-slate-900 border border-slate-800">
            <span className="text-[10px] text-slate-400 block">Current Reefer</span>
            <span className="text-base font-extrabold text-rose-400 font-mono">
              {currentTemp !== undefined && currentTemp !== null ? `${currentTemp}°F` : "—"}
            </span>
          </div>
          <div className="p-2 rounded bg-slate-900 border border-slate-800">
            <span className="text-[10px] text-slate-400 block">Target Setpoint</span>
            <span className="text-base font-extrabold text-teal-400 font-mono">
              {setpointTemp !== undefined && setpointTemp !== null ? `${setpointTemp}°F` : "—"}
            </span>
          </div>
        </div>

        {state.telematics_alarm_code && (
          <div className="text-xs text-amber-300 bg-amber-950/40 p-2 rounded border border-amber-800/60 flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <span className="font-mono text-[11px] truncate">{state.telematics_alarm_code}</span>
          </div>
        )}
      </div>

      {/* Tractor & Driver Info */}
      <div className="space-y-2 text-xs">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
          Asset & Driver Credentials
        </span>
        <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2 text-slate-300">
          <div className="flex items-center justify-between">
            <span className="text-slate-400">Tractor / Trailer:</span>
            <span className="font-mono font-semibold text-slate-200">
              {state.truck_id || "—"} / {state.trailer_id || "—"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-slate-400">Commercial Driver:</span>
            <span className="font-semibold text-slate-200">{state.driver_name || "—"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-slate-400">Driver Phone:</span>
            <span className="font-mono text-slate-300">{state.driver_phone_e164 || "—"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-slate-400">Spoken Locale:</span>
            <span className="font-mono text-slate-300">{state.driver_locale || "—"}</span>
          </div>
        </div>
      </div>

      {/* Cargo Manifest & Regulatory Limits */}
      {manifest && (
        <div className="space-y-2 text-xs">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
            FSMA Cargo Manifest Constraints
          </span>
          <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2 text-slate-300">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">BOL Number:</span>
              <span className="font-mono font-semibold text-slate-200">{manifest.bol_number}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Commodity Type:</span>
              <span className="px-2 py-0.5 rounded bg-indigo-950 border border-indigo-800 text-indigo-300 font-bold text-[10px]">
                {manifest.commodity_type}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Allowed Range:</span>
              <span className="font-mono text-slate-200">{manifest.min_temp_f}°F – {manifest.max_temp_f}°F</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Max Excursion:</span>
              <span className="font-mono text-amber-400">{manifest.max_allowable_excursion_minutes} Min Max</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Shipper Enterprise:</span>
              <span className="font-medium text-slate-300 truncate">{manifest.shipper_name}</span>
            </div>
          </div>
        </div>
      )}

      {/* Emergency Pre-Actuation Cancel Control */}
      <div className="pt-2">
        <EmergencyCancelButton
          eventId={state.event_id || null}
          status={state.requires_immediate_human_override ? "cancelled" : state.disposition ? "completed" : "in-progress"}
          disposition={state.disposition}
          baseUrl={baseUrl}
          onCancelled={onCancelled}
        />
      </div>
    </aside>
  );
};
