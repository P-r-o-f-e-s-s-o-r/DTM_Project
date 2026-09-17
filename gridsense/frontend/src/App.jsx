import React, { useState, useEffect, useRef } from 'react';
import {
  Zap,
  Activity,
  Sun,
  Gauge,
  ShieldCheck,
  AlertTriangle,
  ShieldAlert,
  Play,
  Pause,
  Flame,
  CheckCircle,
  Clock,
  Server
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine
} from 'recharts';

export default function App() {
  const [telemetry, setTelemetry] = useState(null);
  const [history, setHistory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [isPaused, setIsPaused] = useState(false);
  const [wsStatus, setWsStatus] = useState('connecting'); // 'connected' | 'connecting' | 'disconnected'
  const [lastUpdate, setLastUpdate] = useState(null);
  const [surgeLoading, setSurgeLoading] = useState(false);
  const [surgeMessage, setSurgeMessage] = useState(null);

  const prevRiskRef = useRef(null);
  const wsRef = useRef(null);
  const isPausedRef = useRef(isPaused);
  isPausedRef.current = isPaused;

  // Initialize and connect WebSocket
  useEffect(() => {
    let isMounted = true;
    let reconnectTimeout = null;

    const connect = () => {
      if (!isMounted) return;

      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsHost = window.location.hostname || 'localhost';
      const wsUrl = `${wsProtocol}//${wsHost}:8000/ws/live`;

      setWsStatus('connecting');
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMounted) return;
        setWsStatus('connected');
      };

      ws.onmessage = (e) => {
        if (!isMounted || isPausedRef.current) return;
        try {
          const payload = JSON.parse(e.data);
          if (payload.type === 'telemetry_update' && payload.data) {
            const data = payload.data;
            setTelemetry(data);
            setLastUpdate(new Date());

            const timeStr = data.timestamp
              ? new Date(data.timestamp).toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' })
              : new Date().toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' });

            const point = {
              time: timeStr,
              voltage: Number(data.voltage),
              current: Number(data.current),
              renewable: Number(data.renewable),
              hostingIndex: Number(data.hosting_index)
            };

            setHistory((prev) => {
              const next = [...prev, point];
              return next.length > 20 ? next.slice(next.length - 20) : next;
            });

            // Trigger Alert on caution/critical
            const rLevel = data.risk?.risk_level?.toLowerCase();
            if (rLevel && rLevel !== 'safe' && prevRiskRef.current !== rLevel) {
              const newAlert = {
                id: Date.now(),
                time: timeStr,
                level: rLevel,
                voltage: data.voltage,
                current: data.current,
                analysis: data.risk?.analysis || 'Anomalous grid state detected.',
                recommendation: data.risk?.recommendation || 'Check feeder load.'
              };
              setAlerts((prev) => [newAlert, ...prev.slice(0, 14)]);
            }
            prevRiskRef.current = rLevel;
          }
        } catch (err) {
          console.error('Error parsing live frame:', err);
        }
      };

      ws.onclose = () => {
        if (!isMounted) return;
        setWsStatus('disconnected');
        reconnectTimeout = setTimeout(connect, 2500);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      isMounted = false;
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  // Trigger test surge event
  const triggerSurge = async () => {
    setSurgeLoading(true);
    try {
      const resp = await fetch('http://127.0.0.1:8000/simulate-surge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voltage: 247.8, current: 57.2, renewable: 84.0 })
      });
      const result = await resp.json();
      setSurgeMessage('Simulated 247.8V / 57.2A Surge Injected');
      setTimeout(() => setSurgeMessage(null), 4000);
    } catch (err) {
      console.error('Surge injection failed:', err);
    } finally {
      setSurgeLoading(false);
    }
  };

  const riskLevel = telemetry?.risk?.risk_level?.toLowerCase() || 'safe';
  const confidence = telemetry?.risk?.confidence
    ? Math.round(telemetry.risk.confidence * 100)
    : 95;

  const riskStyles = {
    safe: {
      dot: 'bg-emerald-500',
      pill: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
      border: 'border-emerald-500/30',
      label: 'SAFE',
      icon: ShieldCheck
    },
    caution: {
      dot: 'bg-amber-500',
      pill: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
      border: 'border-amber-500/30',
      label: 'CAUTION',
      icon: AlertTriangle
    },
    critical: {
      dot: 'bg-rose-500',
      pill: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
      border: 'border-rose-500/30',
      label: 'CRITICAL',
      icon: ShieldAlert
    }
  }[riskLevel] || {
    dot: 'bg-slate-500',
    pill: 'bg-slate-800 text-slate-400 border-slate-700',
    border: 'border-slate-800',
    label: 'STANDBY',
    icon: ShieldCheck
  };

  const RiskIcon = riskStyles.icon;

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-200 flex flex-col p-4 md:p-8 max-w-6xl mx-auto font-sans">
      {/* Minimal Header */}
      <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-6 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Zap className="w-4 h-4" />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-white">GridSense</h1>
            <span className="text-xs font-mono text-slate-400 bg-slate-800/80 px-2 py-0.5 rounded border border-slate-700">
              Feeder 1
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real-time distribution feeder intelligence and hosting capacity
          </p>
        </div>

        {/* Action Controls & Stream Status */}
        <div className="flex items-center gap-3">
          {/* Live indicator */}
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-xs">
            <span className={`w-2 h-2 rounded-full ${wsStatus === 'connected' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
            <span className="font-mono text-slate-300">
              {wsStatus === 'connected' ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>

          {/* Pause / Resume Button */}
          <button
            onClick={() => setIsPaused(!isPaused)}
            className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 transition-colors"
          >
            {isPaused ? <Play className="w-3 h-3 text-emerald-400" /> : <Pause className="w-3 h-3 text-amber-400" />}
            {isPaused ? 'Resume' : 'Pause'}
          </button>

          {/* Simulate Surge Action Button */}
          <button
            onClick={triggerSurge}
            disabled={surgeLoading}
            className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md bg-cyan-600/20 hover:bg-cyan-600/30 border border-cyan-500/40 text-cyan-300 transition-colors disabled:opacity-50"
            title="Inject a high-voltage and overload surge to test system reaction"
          >
            <Flame className="w-3 h-3" />
            {surgeLoading ? 'Injecting...' : 'Test Surge'}
          </button>
        </div>
      </header>

      {/* Optional Notification Toast */}
      {surgeMessage && (
        <div className="mt-4 p-2.5 bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs rounded-lg flex items-center justify-between animate-fade-in">
          <span>{surgeMessage}</span>
          <span className="text-[10px] text-slate-400">Incoming to WebSocket...</span>
        </div>
      )}

      {/* Main 4 Metric Cards (Clean & Minimal) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 my-6">
        {/* Voltage */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Voltage</span>
            <span className="font-mono text-[11px] text-cyan-400">230V Ref</span>
          </div>
          <div className="my-2">
            <span className="text-3xl font-bold font-mono text-white tracking-tight">
              {telemetry ? telemetry.voltage.toFixed(1) : '--.-'}
            </span>
            <span className="text-xs text-slate-400 ml-1.5">V</span>
          </div>
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>Deviation:</span>
            <span className="font-mono">
              {telemetry ? `${(telemetry.voltage - 230 >= 0 ? '+' : '')}${(telemetry.voltage - 230).toFixed(1)}V` : '0.0V'}
            </span>
          </div>
        </div>

        {/* Current */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Current</span>
            <span className="font-mono text-[11px] text-amber-400">50A Max</span>
          </div>
          <div className="my-2">
            <span className="text-3xl font-bold font-mono text-white tracking-tight">
              {telemetry ? telemetry.current.toFixed(1) : '--.-'}
            </span>
            <span className="text-xs text-slate-400 ml-1.5">A</span>
          </div>
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>Loading:</span>
            <span className="font-mono">
              {telemetry ? `${Math.round((telemetry.current / 50) * 100)}%` : '0%'}
            </span>
          </div>
        </div>

        {/* Renewable Penetration */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Renewables</span>
            <Sun className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="my-2">
            <span className="text-3xl font-bold font-mono text-white tracking-tight">
              {telemetry ? telemetry.renewable.toFixed(1) : '--.-'}
            </span>
            <span className="text-xs text-slate-400 ml-1.5">%</span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-1 mt-1">
            <div
              className="bg-emerald-500 h-1 rounded-full transition-all duration-300"
              style={{ width: `${Math.min(100, telemetry?.renewable || 0)}%` }}
            />
          </div>
        </div>

        {/* Hosting Capacity Index */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Hosting Index</span>
            <Gauge className="w-3.5 h-3.5 text-indigo-400" />
          </div>
          <div className="my-2">
            <span className="text-3xl font-bold font-mono text-white tracking-tight">
              {telemetry ? telemetry.hosting_index.toFixed(1) : '--.-'}
            </span>
            <span className="text-xs text-slate-400 ml-1.5">/ 100</span>
          </div>
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>Status:</span>
            <span className={`font-mono ${telemetry && telemetry.hosting_index >= 70 ? 'text-emerald-400' : 'text-amber-400'}`}>
              {telemetry && telemetry.hosting_index >= 70 ? 'Optimal' : 'Stressed'}
            </span>
          </div>
        </div>
      </div>

      {/* Minimal AI Risk Card */}
      <div className={`rounded-xl p-4 bg-slate-900/80 border ${riskStyles.border} flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all duration-300`}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-slate-800 border border-slate-700">
            <RiskIcon className="w-5 h-5 text-slate-200" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Grid Risk Level:</span>
              <span className={`text-xs font-bold font-mono px-2 py-0.5 rounded border ${riskStyles.pill}`}>
                {riskStyles.label}
              </span>
              <span className="text-xs text-slate-500 font-mono">
                ({confidence}% Confidence)
              </span>
            </div>
            <p className="text-xs text-slate-300 mt-1">
              {telemetry?.risk?.analysis || 'Feeder operating under continuous AI telemetry analysis.'}
            </p>
          </div>
        </div>

        <div className="text-left sm:text-right border-t sm:border-t-0 border-slate-800 pt-2 sm:pt-0 w-full sm:w-auto">
          <span className="text-[11px] text-slate-400 block">Mitigation Advice</span>
          <span className="text-xs font-medium text-slate-200">
            {telemetry?.risk?.recommendation || 'Maintain standard operation.'}
          </span>
        </div>
      </div>

      {/* Main Visuals & Logs Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 my-6">
        {/* Clean Line Chart */}
        <div className="lg:col-span-2 bg-slate-900/60 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3 text-xs">
            <span className="font-medium text-white">Voltage & Current Trend</span>
            <div className="flex items-center gap-4 text-[11px]">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-cyan-400" />
                <span className="text-slate-300">Voltage (V)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                <span className="text-slate-300">Current (A)</span>
              </div>
            </div>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={history} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#1e293b" />
                <XAxis dataKey="time" stroke="#475569" tick={{ fontSize: 10 }} />
                <YAxis yAxisId="v" domain={[205, 255]} stroke="#38bdf8" tick={{ fontSize: 10 }} orientation="left" />
                <YAxis yAxisId="c" domain={[0, 65]} stroke="#fbbf24" tick={{ fontSize: 10 }} orientation="right" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#334155',
                    borderRadius: '0.5rem',
                    color: '#f8fafc',
                    fontSize: '11px'
                  }}
                />
                <ReferenceLine yAxisId="v" y={230} stroke="#38bdf8" strokeDasharray="3 3" opacity={0.6} />
                <ReferenceLine yAxisId="v" y={244} stroke="#f43f5e" strokeDasharray="2 2" opacity={0.6} />
                <Line yAxisId="v" type="monotone" dataKey="voltage" stroke="#38bdf8" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line yAxisId="c" type="monotone" dataKey="current" stroke="#fbbf24" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Minimal Alert Log */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-white">Event Log</span>
            <span className="text-[11px] font-mono text-slate-400">{alerts.length} events</span>
          </div>

          <div className="flex-1 overflow-y-auto max-h-64 space-y-2 pr-1">
            {alerts.length === 0 ? (
              <div className="h-44 flex flex-col items-center justify-center text-center text-xs text-slate-500 border border-dashed border-slate-800 rounded-lg">
                <CheckCircle className="w-5 h-5 text-emerald-500/60 mb-1.5" />
                <span>Feeder state nominal. No events.</span>
              </div>
            ) : (
              alerts.map((a) => (
                <div
                  key={a.id}
                  className={`p-2.5 rounded-lg border text-xs flex flex-col gap-0.5 ${
                    a.level === 'critical'
                      ? 'bg-rose-950/20 border-rose-500/30 text-rose-300'
                      : 'bg-amber-950/20 border-amber-500/30 text-amber-300'
                  }`}
                >
                  <div className="flex items-center justify-between font-mono text-[10px]">
                    <span className="font-bold uppercase">{a.level}</span>
                    <span className="text-slate-400">{a.time}</span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-200">
                    {a.voltage}V • {a.current}A
                  </div>
                  <p className="text-[11px] text-slate-300 line-clamp-2 mt-0.5">
                    {a.analysis}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Minimal Footer System Status */}
      <footer className="mt-auto pt-4 border-t border-slate-800/80 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs text-slate-500">
        <div className="flex items-center gap-4">
          <span>MySQL: <strong className="text-slate-400 font-mono">gridsense</strong></span>
          <span>Broker: <strong className="text-slate-400 font-mono">:1883</strong></span>
          <span>Engine: <strong className="text-slate-400 font-mono">OpenRouter LLM</strong></span>
        </div>
        <div className="flex items-center gap-2">
          {lastUpdate && (
            <span>Last sync: {lastUpdate.toLocaleTimeString()}</span>
          )}
        </div>
      </footer>
    </div>
  );
}
