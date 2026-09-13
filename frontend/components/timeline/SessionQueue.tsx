"use client";

import React, { useState } from "react";
import { ThermometerSnowflake, AlertTriangle, ShieldCheck, Clock, Search, Truck } from "lucide-react";
import type { SessionSummary } from "@/lib/types";

interface SessionQueueProps {
  sessions: SessionSummary[];
  selectedEventId: string | null;
  onSelectSession: (eventId: string) => void;
  onTriggerDemo?: () => void;
}

export const SessionQueue: React.FC<SessionQueueProps> = ({
  sessions,
  selectedEventId,
  onSelectSession,
  onTriggerDemo,
}) => {
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState<string>("");

  const filteredSessions = sessions.filter((s) => {
    const matchesSearch =
      s.truck_id.toLowerCase().includes(search.toLowerCase()) ||
      s.trailer_id.toLowerCase().includes(search.toLowerCase()) ||
      s.driver_name.toLowerCase().includes(search.toLowerCase()) ||
      s.event_id.toLowerCase().includes(search.toLowerCase());

    if (!matchesSearch) return false;
    if (filter === "active") return s.status === "in-progress" || s.status === "pending";
    if (filter === "escalated") return s.override_required;
    if (filter === "completed") return s.status === "completed" && !s.override_required;
    return true;
  });

  return (
    <aside className="w-full lg:w-80 flex flex-col bg-slate-900/70 border-r border-slate-800 h-full">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ThermometerSnowflake className="w-5 h-5 text-cyan-400" />
            <h2 className="font-bold text-sm text-slate-100 tracking-wide">Excursion Queue</h2>
          </div>
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">
            {sessions.length} Incidents
          </span>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search truck, driver, event..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-600"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1 text-[11px]">
          {["all", "active", "escalated", "completed"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded-md capitalize transition font-medium ${
                filter === f
                  ? "bg-cyan-950 border border-cyan-800 text-cyan-300"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {filteredSessions.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500 space-y-2">
            <p>No excursion incidents match criteria.</p>
            {onTriggerDemo && (
              <button
                onClick={onTriggerDemo}
                className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs shadow"
              >
                Trigger Demo Alert
              </button>
            )}
          </div>
        ) : (
          filteredSessions.map((s) => {
            const isSelected = s.event_id === selectedEventId;
            const tempDelta = (s.current_temp_f - s.setpoint_temp_f).toFixed(1);

            return (
              <button
                key={s.event_id}
                onClick={() => onSelectSession(s.event_id)}
                className={`w-full text-left p-3 rounded-xl border transition flex flex-col gap-2 ${
                  isSelected
                    ? "bg-slate-800/90 border-cyan-500 shadow-md ring-1 ring-cyan-500/30"
                    : "bg-slate-950/40 border-slate-800/80 hover:bg-slate-800/50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs text-slate-200 flex items-center gap-1.5">
                    <Truck className="w-3.5 h-3.5 text-cyan-400" />
                    {s.truck_id} / {s.trailer_id}
                  </span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                      s.override_required
                        ? "bg-rose-950 border border-rose-800 text-rose-300"
                        : s.status === "completed"
                        ? "bg-emerald-950 border border-emerald-800 text-emerald-300"
                        : "bg-amber-950 border border-amber-800 text-amber-300 animate-pulse"
                    }`}
                  >
                    {s.override_required ? "Escalated" : s.status}
                  </span>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400">
                  <span>{s.driver_name} ({s.commodity_type})</span>
                  <span className="font-mono text-amber-400 font-semibold">
                    +{tempDelta}°F Excursion
                  </span>
                </div>

                <div className="text-[10px] text-slate-500 flex items-center justify-between font-mono">
                  <span>{s.event_id}</span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5" />
                    {new Date(s.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
};
