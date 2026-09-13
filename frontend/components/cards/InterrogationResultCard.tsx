"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, PhoneCall, ShieldAlert, Clock, Fuel, Snowflake, Droplets, Box } from "lucide-react";
import type { PhysicalObservations } from "@/lib/types";

interface InterrogationResultCardProps {
  observations?: PhysicalObservations | null;
  hosMinutes?: number | null;
  alarmCode?: string | null;
  callStatus?: string | null;
  confidence?: number | null;
  selectedOption?: string | null;
}

export const InterrogationResultCard: React.FC<InterrogationResultCardProps> = ({
  observations,
  hosMinutes,
  alarmCode,
  callStatus,
  confidence,
  selectedOption,
}) => {
  if (!observations && !alarmCode && !hosMinutes) {
    return (
      <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 text-slate-400 text-sm flex items-center gap-2">
        <PhoneCall className="w-4 h-4 animate-pulse text-indigo-400" />
        <span>Interrogating commercial driver via CALL-E voice agent...</span>
      </div>
    );
  }

  const isHosSufficient = hosMinutes !== undefined && hosMinutes !== null && hosMinutes >= 35;

  return (
    <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-5 shadow-lg space-y-4">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <PhoneCall className="w-5 h-5 text-emerald-400" />
          <h3 className="font-semibold text-slate-100 text-sm tracking-wide">
            CALL-E Driver Interrogation Triage
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {confidence !== undefined && confidence !== null && (
            <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-950/80 border border-emerald-800 text-emerald-300 font-medium">
              {(confidence * 100).toFixed(0)}% Voice Confidence
            </span>
          )}
          <span className="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 capitalize font-mono">
            {callStatus || "completed"}
          </span>
        </div>
      </div>

      {/* Driver Reported Alarm & Choice */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {alarmCode && (
          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
            <span className="text-xs text-slate-400 block font-medium mb-1">Driver Reported Alarm</span>
            <span className="text-sm font-semibold text-amber-300 font-mono flex items-center gap-1.5">
              <ShieldAlert className="w-4 h-4 text-amber-400" />
              {alarmCode}
            </span>
          </div>
        )}

        {hosMinutes !== undefined && hosMinutes !== null && (
          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
            <span className="text-xs text-slate-400 block font-medium mb-1">Driver Verified HOS Remaining</span>
            <span
              className={`text-sm font-semibold flex items-center gap-1.5 ${
                isHosSufficient ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              <Clock className="w-4 h-4" />
              {hosMinutes} Minutes {isHosSufficient ? "(Compliant ≥35m)" : "(HOS Breach <35m)"}
            </span>
          </div>
        )}
      </div>

      {/* Physical Observation Checklist */}
      {observations && (
        <div className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Physical Inspection Checklist
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            <div
              className={`p-2.5 rounded-md flex items-center justify-between border ${
                observations.air_bulkhead_obstructed
                  ? "bg-amber-950/30 border-amber-800/60 text-amber-200"
                  : "bg-slate-950/40 border-slate-800/60 text-slate-300"
              }`}
            >
              <span className="flex items-center gap-2">
                <Box className="w-3.5 h-3.5" />
                Bulkhead Obstructed
              </span>
              {observations.air_bulkhead_obstructed ? (
                <AlertTriangle className="w-4 h-4 text-amber-400" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              )}
            </div>

            <div
              className={`p-2.5 rounded-md flex items-center justify-between border ${
                observations.cargo_sweating_detected
                  ? "bg-rose-950/40 border-rose-800/70 text-rose-200"
                  : "bg-slate-950/40 border-slate-800/60 text-slate-300"
              }`}
            >
              <span className="flex items-center gap-2">
                <Droplets className="w-3.5 h-3.5" />
                Cargo Sweating / Moisture
              </span>
              {observations.cargo_sweating_detected ? (
                <AlertTriangle className="w-4 h-4 text-rose-400" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              )}
            </div>

            <div
              className={`p-2.5 rounded-md flex items-center justify-between border ${
                observations.evaporator_ice_detected
                  ? "bg-amber-950/30 border-amber-800/60 text-amber-200"
                  : "bg-slate-950/40 border-slate-800/60 text-slate-300"
              }`}
            >
              <span className="flex items-center gap-2">
                <Snowflake className="w-3.5 h-3.5" />
                Evaporator Ice / Frost
              </span>
              {observations.evaporator_ice_detected ? (
                <AlertTriangle className="w-4 h-4 text-amber-400" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              )}
            </div>

            <div
              className={`p-2.5 rounded-md flex items-center justify-between border ${
                !observations.fuel_level_sufficient
                  ? "bg-rose-950/40 border-rose-800/70 text-rose-200"
                  : "bg-slate-950/40 border-slate-800/60 text-slate-300"
              }`}
            >
              <span className="flex items-center gap-2">
                <Fuel className="w-3.5 h-3.5" />
                Reefer Diesel Level
              </span>
              {observations.fuel_level_sufficient ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-rose-400" />
              )}
            </div>
          </div>

          {observations.driver_action_taken && (
            <div className="mt-2 p-2.5 rounded bg-slate-950/50 border border-slate-800 text-xs text-slate-300">
              <span className="text-slate-400 font-medium">On-Site Action Taken: </span>
              {observations.driver_action_taken}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
