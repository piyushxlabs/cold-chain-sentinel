"use client";

import React, { useEffect, useState } from "react";
import {
  ThermometerSnowflake,
  ShieldCheck,
  Cpu,
  RefreshCw,
  Radio,
  Plus,
  Activity,
  Code2,
  Terminal,
} from "lucide-react";
import type { SessionSummary } from "@/lib/types";
import { useIncidentStream } from "@/lib/useIncidentStream";
import { SessionQueue } from "@/components/timeline/SessionQueue";
import { IncidentTimeline } from "@/components/timeline/IncidentTimeline";
import { SessionSummaryPanel } from "@/components/timeline/SessionSummaryPanel";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function OperationsCockpitPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"timeline" | "trace">("timeline");
  const [health, setHealth] = useState<any>(null);

  const {
    state,
    nodeStatuses,
    events,
    escalationAlert,
    isStreaming,
    isCompleted,
    refreshState,
  } = useIncidentStream(selectedEventId, BACKEND_URL);

  // Fetch session list and backend health
  const fetchSessionsAndHealth = async () => {
    try {
      const [sessRes, healthRes] = await Promise.all([
        fetch(`${BACKEND_URL}/sessions`),
        fetch(`${BACKEND_URL}/health`),
      ]);

      if (sessRes.ok) {
        const data = await sessRes.json();
        setSessions(data);
        if (!selectedEventId && data.length > 0) {
          setSelectedEventId(data[0].event_id);
        }
      }

      if (healthRes.ok) {
        setHealth(await healthRes.json());
      }
    } catch (err) {
      console.warn("Could not connect to Cold Chain Sentinel backend:", err);
    }
  };

  useEffect(() => {
    fetchSessionsAndHealth();
    const interval = setInterval(fetchSessionsAndHealth, 5000);
    return () => clearInterval(interval);
  }, [selectedEventId]);

  // Trigger Demo Excursion Alert
  const handleTriggerDemo = async () => {
    const demoEventId = `evt_demo_${Date.now().toString().slice(-4)}`;
    const payload = {
      event_id: demoEventId,
      session_id: `sess_${demoEventId}`,
      timestamp: new Date().toISOString(),
      truck_id: "TRK-902",
      trailer_id: "TRL-8841",
      current_temp_f: 38.5,
      setpoint_temp_f: 34.0,
      temp_differential_f: 4.5,
      duration_minutes: 20,
      telematics_alarm_code: "ALARM 18 - HIGH ENGINE TEMP",
      current_coordinates: { latitude: 40.8136, longitude: -96.7026 },
      target_destination: "Omaha Distribution Center",
      origin: "Kansas City Cold Hub",
      cargo_manifest: {
        bol_number: `BOL-${Math.floor(10000 + Math.random() * 90000)}`,
        commodity_type: "Dairy",
        min_temp_f: 32.0,
        max_temp_f: 36.0,
        max_allowable_excursion_minutes: 60,
        shipper_name: "Midwest Dairy Logistics",
      },
      driver_phone_e164: "+12065550198",
      driver_name: "Marcus Vance",
      driver_locale: "en-US",
      config: {
        trace_id: `trc_${demoEventId}`,
        client_mode: "mock",
        max_tool_retry_attempts: 3,
        min_hos_minutes_for_reroute: 35,
      },
    };

    try {
      const res = await fetch(`${BACKEND_URL}/webhook/telematics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setSelectedEventId(demoEventId);
        fetchSessionsAndHealth();
      }
    } catch (err) {
      console.error("Demo trigger failed:", err);
    }
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#0b0f17]">
      {/* Top Cockpit Header */}
      <header className="h-14 border-b border-slate-800 bg-slate-950/80 backdrop-blur px-5 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-600/20 text-cyan-400 border border-cyan-500/30">
            <ThermometerSnowflake className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-extrabold text-sm tracking-wider text-slate-100 uppercase">
                Cold Chain Sentinel
              </h1>
              <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-bold tracking-wide">
                OPERATIONS COCKPIT
              </span>
            </div>
          </div>
        </div>

        {/* Global Agent Status & Autonomy Badge */}
        <div className="flex items-center gap-3 text-xs">
          <div className="hidden md:flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-slate-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>Mode: <strong className="text-slate-100 font-semibold">Semi-Autonomous</strong></span>
          </div>

          {health && (
            <div className="hidden lg:flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-slate-400 text-[11px]">
              <Cpu className="w-3.5 h-3.5 text-purple-400" />
              <span>{health.primary_model}</span>
              <span className="text-slate-600">|</span>
              <span className="capitalize">{health.checkpoint_backend} Saver</span>
            </div>
          )}

          <button
            onClick={handleTriggerDemo}
            className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs shadow-md shadow-cyan-950 flex items-center gap-1.5 transition active:scale-98"
          >
            <Plus className="w-4 h-4" />
            <span>Simulate Excursion</span>
          </button>
        </div>
      </header>

      {/* Main 3-Column Cockpit Surface */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Rail: Session Queue */}
        <SessionQueue
          sessions={sessions}
          selectedEventId={selectedEventId}
          onSelectSession={(id) => setSelectedEventId(id)}
          onTriggerDemo={handleTriggerDemo}
        />

        {/* Center Panel: Incident Timeline / Raw Trace */}
        <main className="flex-1 flex flex-col overflow-hidden bg-slate-950/40">
          {/* Timeline Tab Navigation */}
          <div className="h-10 border-b border-slate-800 px-6 flex items-center justify-between text-xs bg-slate-900/40">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setActiveTab("timeline")}
                className={`h-full border-b-2 flex items-center gap-1.5 font-semibold transition ${
                  activeTab === "timeline"
                    ? "border-cyan-400 text-cyan-300"
                    : "border-transparent text-slate-400 hover:text-slate-200"
                }`}
              >
                <Activity className="w-3.5 h-3.5" />
                Live Incident Timeline
              </button>

              <button
                onClick={() => setActiveTab("trace")}
                className={`h-full border-b-2 flex items-center gap-1.5 font-semibold transition ${
                  activeTab === "trace"
                    ? "border-cyan-400 text-cyan-300"
                    : "border-transparent text-slate-400 hover:text-slate-200"
                }`}
              >
                <Terminal className="w-3.5 h-3.5" />
                Raw SSE Trace ({events.length} Events)
              </button>
            </div>

            <div className="flex items-center gap-2">
              {isStreaming && (
                <span className="flex items-center gap-1.5 text-cyan-400 text-[11px] animate-pulse">
                  <Radio className="w-3 h-3" /> Live SSE Stream
                </span>
              )}
              {isCompleted && (
                <span className="text-emerald-400 text-[11px] font-medium">
                  Timeline Frozen ✓
                </span>
              )}
            </div>
          </div>

          {/* Tab Content */}
          {activeTab === "timeline" ? (
            <IncidentTimeline
              state={state}
              nodeStatuses={nodeStatuses}
              escalationAlert={escalationAlert}
            />
          ) : (
            <div className="flex-1 overflow-y-auto p-6 bg-slate-950 font-mono text-xs text-slate-300 space-y-2">
              <span className="text-slate-500 block mb-4">
                Raw OpenTelemetry & Server-Sent Event stream log for event: {selectedEventId}
              </span>
              {events.length === 0 ? (
                <p className="text-slate-600">No events captured yet.</p>
              ) : (
                events.map((ev, i) => (
                  <div key={i} className="p-2 rounded bg-slate-900 border border-slate-800/80">
                    <span className="text-cyan-400 font-bold block mb-1">[{ev.type}]</span>
                    <pre className="text-slate-300 text-[11px] whitespace-pre-wrap overflow-x-auto">
                      {JSON.stringify(ev, null, 2)}
                    </pre>
                  </div>
                ))
              )}
            </div>
          )}
        </main>

        {/* Right Rail: Session Summary Panel */}
        <SessionSummaryPanel
          state={state}
          onCancelled={refreshState}
          baseUrl={BACKEND_URL}
        />
      </div>
    </div>
  );
}
