export default function RiskMeter({ score = 0, label, risk }) {
  const pct = Math.max(0, Math.min(100, score));

  let barClass = "risk-bar-low";
  if (risk && risk.includes("CRITICAL")) barClass = "risk-bar-critical";
  else if (risk && risk.includes("WARNING")) barClass = "risk-bar-warning";

  return (
    <div className="risk-meter">
      <div className="risk-meter-header">
        <span>{risk || "🟢 LOW RISK"}</span>
        <span className="risk-score">{pct}/100</span>
      </div>
      <div className="risk-bar-track">
        <div className={`risk-bar-fill ${barClass}`} style={{ width: `${pct}%` }} />
      </div>
      {label && <div className="risk-meter-label">Detected intent: {label}</div>}
    </div>
  );
}
