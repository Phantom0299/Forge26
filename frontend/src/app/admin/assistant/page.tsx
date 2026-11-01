"use client";

import React, { useState, useRef, useEffect } from "react";
import AdminLayout from "@/components/admin/AdminLayout";

interface Citation {
  file: string;
  page: string | number;
  snippet: string;
}

interface Message {
  id: string;
  sender: "user" | "assistant";
  text: string;
  time: string;
  sources?: Citation[];
  isVisionTriggered?: boolean;
  sitrepAvailable?: boolean;
  incidentMeta?: {
    hazard: string;
    severity: string;
    location: string;
  };
}

interface SitRepData {
  incident_id: string;
  location: string;
  hazard_type: string;
  severity: string;
  sitrep_content: string;
  timestamp: string;
}

const VISION_PRESETS = [
  {
    title: "Class 3 Landslide on NH-10",
    badge: "YOLO + DEM Vision",
    color: "#DC4848",
    hazard: "landslide",
    severity: "Class 3",
    location: "NH-10 Km 48 (Siliguri-Gangtok Corridor)",
    blockage_pct: 85.0,
    water_depth_m: undefined,
    promptText: "🚨 Vision Trigger: YOLO detected a Class 3 Landslide with 85% road blockage at Km 48 on NH-10.",
  },
  {
    title: "SAR Flood Inundation",
    badge: "Sentinel-1 SAR",
    color: "#F07838",
    hazard: "flash_flood",
    severity: "Critical",
    location: "Bhalukpong Sector (Guwahati-Tawang Km 18)",
    blockage_pct: undefined,
    water_depth_m: 0.42,
    promptText: "🌊 Vision Trigger: Sentinel-1 SAR backscatter drop indicates 0.42m water depth over roadway at Bhalukpong.",
  },
  {
    title: "Sela Pass Ice & Snow Glaze",
    badge: "Thermal + IMD Radar",
    color: "#16A779",
    hazard: "black_ice",
    severity: "Class 2",
    location: "Sela Pass Portal (Altitude: 13,700 ft)",
    blockage_pct: 40.0,
    water_depth_m: undefined,
    promptText: "❄️ Vision Trigger: Black ice and freeze-thaw hazard detected near Sela Tunnel portal approach.",
  },
];

const SUGGESTIONS = [
  "What is the evacuation protocol for a Class 3 landslide?",
  "What are the IRC:SP:48 drainage and slope standards for hill roads?",
  "How does BRO Project Vartak deploy machinery for road clearance?",
  "What are the IMD rainfall thresholds for road closures?",
];

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "init",
      sender: "assistant",
      text: "RouteX Tactical Dispatch ready. Connected to verified SOP manuals: **NDMA Landslide SOP, IRC:SP:48, BRO Project Vartak, and IMD Weather Protocols**.\n\nUse the **Vision-to-SOP Triggers** below to see how our SAR radar and YOLO vision models auto-retrieve road clearance checklists, or ask natural operational queries.",
      time: "Online",
      sources: [{ file: "ndma_landslide_sop.md", page: "Overview", snippet: "RouteX Corridor Intelligence Knowledge Base" }],
    },
  ]);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"chat" | "knowledge">("chat");
  const [activeCitation, setActiveCitation] = useState<string | null>(null);
  const [currentSitRep, setCurrentSitRep] = useState<SitRepData | null>(null);
  const [copiedSitRep, setCopiedSitRep] = useState(false);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleQuery = async (queryText?: string, isVision = false, meta?: { hazard: string; severity: string; location: string }) => {
    const text = (queryText || input).trim();
    if (!text || loading) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      sender: "user",
      text,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      isVisionTriggered: isVision,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/v1/rag/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });

      if (res.ok) {
        const data = await res.json();
        setMessages((prev) => [
          ...prev,
          {
            id: `a-${Date.now()}`,
            sender: "assistant",
            text: data.answer,
            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            sources: data.sources || [],
            sitrepAvailable: isVision,
            incidentMeta: meta,
          },
        ]);
        return;
      }
      const errData = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          sender: "assistant",
          text: `⚠️ **RAG Backend Service Unreachable / Offline**\n\nCould not execute query against live pgvector & Groq LLM pipeline.\n\n*Error details:* ${err.message || "Failed to connect to /api/v1/rag/query"}\n\n*Required Service:* Ensure FastAPI engine (port 8000) and PostgreSQL PostGIS/pgvector (port 55432) are running with \`GROQ_API_KEY\` set in \`.env\`.`,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          sources: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleVisionPresetClick = async (preset: (typeof VISION_PRESETS)[0]) => {
    if (loading) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      sender: "user",
      text: preset.promptText,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      isVisionTriggered: true,
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await fetch("/api/v1/rag/vision-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hazard_type: preset.hazard,
          severity: preset.severity,
          location: preset.location,
          water_depth_m: preset.water_depth_m,
          blockage_pct: preset.blockage_pct,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setMessages((prev) => [
          ...prev,
          {
            id: `a-${Date.now()}`,
            sender: "assistant",
            text: data.dispatch_guidance,
            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            sources: data.grounding_sources || [],
            sitrepAvailable: true,
            incidentMeta: {
              hazard: preset.hazard,
              severity: preset.severity,
              location: preset.location,
            },
          },
        ]);
        return;
      }
      const errData = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          sender: "assistant",
          text: `⚠️ **Vision-to-SOP Automated Dispatch Failed**\n\nFailed to invoke live endpoint \`/api/v1/rag/vision-action\`.\n\n*Reason:* ${err.message || "Backend offline"}\n\n*Action required:* Start the RouteX backend container or service to process satellite/YOLO telemetry against pgvector SOPs.`,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          sources: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateSitRep = async (meta: { hazard: string; severity: string; location: string }) => {
    try {
      const res = await fetch("/api/v1/rag/sitrep", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hazard_type: meta.hazard,
          severity: meta.severity,
          location: meta.location,
          details: "Verified field telemetry from Sentinel-1 SAR and YOLO Road Damage detector.",
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setCurrentSitRep({
          ...data,
          timestamp: new Date().toLocaleString(),
        });
        return;
      }
      const errData = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errData.detail || `Server returned ${res.status}`);
    } catch (err: any) {
      alert(`⚠️ Tactical SitRep Generation Failed:\n${err.message || "Could not reach live backend."}\n\nPer Forge '26 live-data guidelines, static mock SitReps are disabled. Please ensure the backend RAG service is active.`);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSitRep(true);
    setTimeout(() => setCopiedSitRep(false), 2500);
  };

  return (
    <AdminLayout>
      <div className="flex flex-col gap-4 max-w-7xl mx-auto w-full">
        {/* Tactical Banner */}
        <div className="bg-[#193B32] text-white p-3.5 rounded-2xl border border-[#16A779]/30 flex flex-wrap items-center justify-between gap-3 shadow-sm">
          <div className="flex items-center gap-3">
            <span className="flex h-3 w-3 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#16A779] opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-[#16A779]" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-sm tracking-wide">ROUTEX TACTICAL DISPATCH</span>
                <span className="text-[10px] bg-[#16A779]/20 text-[#DDF4E8] px-2 py-0.5 rounded border border-[#16A779]/40 font-mono">
                  CORRIDOR: NH-13 (GUWAHATI - TAWANG)
                </span>
              </div>
              <p className="text-[11px] text-[#DDF4E8]/80 mt-0.5">
                VHF Radio Freq: 142.500 MHz | Grounded on NDMA, BRO Project Vartak, IRC:SP:48, and IMD-CWC Protocols
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("chat")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                activeTab === "chat"
                  ? "bg-[#16A779] text-white shadow-sm"
                  : "bg-white/10 text-white hover:bg-white/20"
              }`}
            >
              💬 Dispatch Operations
            </button>
            <button
              onClick={() => setActiveTab("knowledge")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                activeTab === "knowledge"
                  ? "bg-[#16A779] text-white shadow-sm"
                  : "bg-white/10 text-white hover:bg-white/20"
              }`}
            >
              📚 Knowledge Corpus (4 Manuals)
            </button>
          </div>
        </div>

        {activeTab === "chat" ? (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 items-start">
            {/* Main Chat Stream */}
            <div className="lg:col-span-3 flex flex-col bg-white rounded-2xl border border-[#DCE5D8] shadow-sm overflow-hidden min-h-[660px]">
              {/* Vision Presets Bar */}
              <div className="p-3 bg-[#FAFBF7] border-b border-[#DCE5D8]">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-bold text-[#12432A] uppercase tracking-wider flex items-center gap-1.5">
                    <span>⚡ Vision-to-SOP Dispatch Triggers:</span>
                  </span>
                  <span className="text-[10px] text-[#71877D]">Click to test closed-loop vision dispatching</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {VISION_PRESETS.map((p, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleVisionPresetClick(p)}
                      disabled={loading}
                      className="text-xs bg-white hover:bg-[#DDF4E8] text-[#193B32] px-3 py-1.5 rounded-xl border border-[#DCE5D8] hover:border-[#16A779] transition-all flex items-center gap-2 shadow-2xs"
                    >
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
                      <span className="font-semibold">{p.title}</span>
                      <span className="text-[10px] text-[#71877D] bg-[#FAFAF2] px-1.5 py-0.5 rounded border border-[#E8EFE5]">
                        {p.badge}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Chat Messages */}
              <div className="flex-1 p-5 overflow-y-auto space-y-4 max-h-[500px]">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}
                  >
                    <div className="flex items-center gap-2 mb-1 px-1">
                      <span className="text-[11px] font-bold text-[#71877D]">
                        {m.sender === "user" ? (m.isVisionTriggered ? "🛰️ ML Telemetry Feed" : "Dispatcher") : "RouteX Dispatch AI"}
                      </span>
                      <span className="text-[10px] text-[#89939A]">{m.time}</span>
                    </div>

                    <div
                      className={`max-w-[85%] rounded-2xl p-4 text-xs leading-relaxed ${
                        m.sender === "user"
                          ? m.isVisionTriggered
                            ? "bg-[#193B32] text-white border border-[#16A779] rounded-tr-none shadow-sm"
                            : "bg-[#176B4D] text-white rounded-tr-none shadow-sm"
                          : "bg-[#FAFAF2] text-[#193B32] border border-[#DCE5D8] rounded-tl-none shadow-sm whitespace-pre-wrap"
                      }`}
                    >
                      {m.text}

                      {/* SitRep Action Button */}
                      {m.sitrepAvailable && m.incidentMeta && (
                        <div className="mt-3 pt-3 border-t border-[#DCE5D8] flex items-center justify-between">
                          <span className="text-[11px] font-semibold text-[#12432A]">
                            Incident Ready for Command Briefing
                          </span>
                          <button
                            onClick={() => handleGenerateSitRep(m.incidentMeta!)}
                            className="bg-[#12432A] hover:bg-[#176B4D] text-white text-[11px] font-bold px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 shadow-2xs"
                          >
                            <span>📄 Generate Field SitRep</span>
                          </button>
                        </div>
                      )}

                      {/* Source Citations Drawer */}
                      {m.sources && m.sources.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-[#DCE5D8] text-[11px]">
                          <div className="font-bold text-[#12432A] flex items-center gap-1.5 mb-2">
                            <span>📑 Verified Grounding Sources:</span>
                            <span className="bg-[#DDF4E8] text-[#12432A] px-1.5 py-0.5 rounded text-[10px]">
                              {m.sources.length} cited
                            </span>
                          </div>

                          <div className="space-y-1.5">
                            {m.sources.map((src, sIdx) => {
                              const key = `${m.id}-${sIdx}`;
                              const isExpanded = activeCitation === key;
                              return (
                                <div key={sIdx} className="bg-white rounded-lg p-2 border border-[#DCE5D8]">
                                  <div className="flex items-center justify-between gap-2">
                                    <span className="font-semibold text-[#176B4D]">
                                      📄 {src.file} ({src.page})
                                    </span>
                                    <button
                                      onClick={() => setActiveCitation(isExpanded ? null : key)}
                                      className="text-[10px] text-[#71877D] hover:text-[#12432A] underline"
                                    >
                                      {isExpanded ? "Hide snippet" : "View source text"}
                                    </button>
                                  </div>

                                  {isExpanded && (
                                    <p className="mt-2 text-[#71877D] italic bg-[#FAFBF7] p-2 rounded border border-[#E8EFE5] text-[11px]">
                                      &ldquo;{src.snippet}&rdquo;
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {loading && (
                  <div className="flex items-center gap-2 text-xs text-[#71877D] p-3 bg-[#FAFAF2] rounded-xl border border-[#DCE5D8] w-fit">
                    <div className="w-2 h-2 rounded-full bg-[#16A779] animate-ping" />
                    <span>Executing Hybrid RRF search across pgvector & generating grounded protocol...</span>
                  </div>
                )}
                <div ref={chatBottomRef} />
              </div>

              {/* Chat Input */}
              <div className="p-3 bg-white border-t border-[#DCE5D8]">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleQuery();
                  }}
                  className="flex items-center gap-2"
                >
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask about landslide clearance, Sela Pass snow protocols, OKSRT bypass weight limits..."
                    disabled={loading}
                    className="flex-1 bg-[#FAFBF7] border border-[#DCE5D8] focus:border-[#16A779] focus:outline-none rounded-xl px-4 py-2.5 text-xs text-[#193B32] placeholder:text-[#89939A]"
                  />
                  <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    className="bg-[#176B4D] hover:bg-[#12432A] disabled:opacity-50 text-white font-semibold text-xs px-5 py-2.5 rounded-xl transition-all shadow-sm"
                  >
                    Send Query
                  </button>
                </form>
              </div>
            </div>

            {/* Sidebar Column */}
            <div className="space-y-4">
              <div className="bg-white rounded-2xl p-4 border border-[#DCE5D8] shadow-sm">
                <h3 className="text-xs font-extrabold text-[#193B32] uppercase tracking-wider mb-2">
                  🛡️ Closed-Loop Pipeline
                </h3>
                <p className="text-xs text-[#71877D] leading-relaxed mb-3">
                  Instead of a generic chatbot, RouteX pairs Satellite & Road Damage Vision with real SOPs for immediate operational response.
                </p>
                <div className="space-y-2 text-[11px]">
                  <div className="flex justify-between py-1 border-b border-[#E8EFE5]">
                    <span className="text-[#71877D]">Retrieval Mode:</span>
                    <span className="font-semibold text-[#193B32]">Hybrid RRF (Dense + Lexical)</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-[#E8EFE5]">
                    <span className="text-[#71877D]">Vector Storage:</span>
                    <span className="font-semibold text-[#193B32]">PostgreSQL (pgvector)</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-[#E8EFE5]">
                    <span className="text-[#71877D]">LLM Dispatch:</span>
                    <span className="font-semibold text-[#193B32]">Groq Llama 3.1 8B</span>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-[#71877D]">Corridor Focus:</span>
                    <span className="font-semibold text-[#193B32]">Guwahati-Tawang (NH-13)</span>
                  </div>
                </div>
              </div>

              <div className="bg-[#FAFBF7] rounded-2xl p-4 border border-[#DCE5D8]">
                <h4 className="text-xs font-bold text-[#193B32] mb-2">💡 Quick Prompt Suggestions</h4>
                <div className="space-y-1.5">
                  {SUGGESTIONS.map((s, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleQuery(s)}
                      disabled={loading}
                      className="text-left w-full text-[11px] text-[#176B4D] hover:underline p-1.5 rounded hover:bg-white transition-colors"
                    >
                      • {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* Knowledge Corpus Tab */
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              {
                file: "ndma_landslide_sop.md",
                title: "NDMA SOP: Landslide Hazard Mitigation (2024-V2)",
                scope: "Himalayan Hill Roads & Evacuation Detours",
                sections: "4 Severity Classes, 15-min Traffic Halts, OKSRT Bypass",
              },
              {
                file: "irc_sp_48_hill_roads.md",
                title: "IRC:SP:48 — Hill Road Engineering Standards",
                scope: "Safety, Drainage & Slope Retaining Specifications",
                sections: "Catchwater Drains, Culvert Sizes (>=1000mm), Net Barriers",
              },
              {
                file: "bro_mountain_road_clearance.md",
                title: "BRO Project Vartak — Emergency Road Clearance",
                scope: "Guwahati-Tawang Strategic Corridor Restorations",
                sections: "Machinery Roster (Excavators/Bailey Bridge), Sela Tunnel Rules",
              },
              {
                file: "imd_weather_alert_protocols.md",
                title: "IMD & CWC Weather Warning Matrix",
                scope: "Flash Floods, Monsoons & River Basin Alerts",
                sections: "24h & 72h Rainfall Triggers, SAR VV Backscatter Drop Thresholds",
              },
            ].map((d, idx) => (
              <div key={idx} className="bg-white rounded-2xl p-4 border border-[#DCE5D8] shadow-sm flex flex-col justify-between">
                <div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#DDF4E8] text-[#12432A] border border-[#B7E4CD] inline-block mb-2">
                    Verified Grounding Corpus
                  </span>
                  <h3 className="text-xs font-bold text-[#193B32] mb-1">{d.title}</h3>
                  <code className="text-[11px] text-[#71877D] block mb-2">{d.file}</code>
                  <p className="text-[11px] text-[#71877D]">{d.scope}</p>
                </div>
                <div className="pt-3 mt-3 border-t border-[#E8EFE5] text-[10px] text-[#176B4D] font-medium">
                  {d.sections}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Tactical SitRep Modal */}
        {currentSitRep && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl max-w-2xl w-full border border-[#DCE5D8] shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
              {/* Modal Header */}
              <div className="bg-[#12432A] text-white p-4 flex items-center justify-between border-b border-[#16A779]/40">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-extrabold text-sm tracking-wide">EMERGENCY SITUATION REPORT (SITREP)</span>
                    <span className="bg-[#DC4848] text-white text-[10px] font-bold px-2 py-0.5 rounded">
                      PRIORITY 1
                    </span>
                  </div>
                  <p className="text-[10px] text-[#DDF4E8]/80 font-mono mt-0.5">
                    {currentSitRep.incident_id} • {currentSitRep.timestamp}
                  </p>
                </div>

                <button
                  onClick={() => setCurrentSitRep(null)}
                  className="text-white/80 hover:text-white text-lg p-1"
                >
                  ✕
                </button>
              </div>

              {/* Modal Content */}
              <div className="p-5 overflow-y-auto font-mono text-xs text-[#193B32] leading-relaxed whitespace-pre-wrap bg-[#FAFBF7]">
                {currentSitRep.sitrep_content}
              </div>

              {/* Modal Footer */}
              <div className="p-3 bg-white border-t border-[#DCE5D8] flex items-center justify-between">
                <span className="text-[11px] text-[#71877D]">
                  Location: <strong>{currentSitRep.location}</strong>
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => copyToClipboard(currentSitRep.sitrep_content)}
                    className="bg-[#176B4D] hover:bg-[#12432A] text-white text-xs font-semibold px-4 py-2 rounded-xl transition-all shadow-sm"
                  >
                    {copiedSitRep ? "✓ Copied SitRep!" : "📋 Copy to Clipboard"}
                  </button>
                  <button
                    onClick={() => setCurrentSitRep(null)}
                    className="bg-white hover:bg-[#FAFAF2] text-[#193B32] border border-[#DCE5D8] text-xs font-semibold px-4 py-2 rounded-xl transition-all"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  );
}
