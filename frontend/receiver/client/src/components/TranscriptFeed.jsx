function riskBadgeClass(riskStatus) {
  if (riskStatus && riskStatus.includes("CRITICAL")) return "transcript-risk-critical";
  if (riskStatus && riskStatus.includes("WARNING")) return "transcript-risk-warning";
  return "transcript-risk-low";
}

export default function TranscriptFeed({ chunks }) {
  return (
    <div className="transcript-feed">
      {chunks.length === 0 && (
        <div className="transcript-empty">Listening… live transcript will appear here.</div>
      )}
      {chunks.map((c) => (
        <div key={c.index} className="transcript-line">
          <div className="transcript-line-header">
            <span className="transcript-timestamp">{c.timestamp}</span>
            {c.risk_status && (
              <span className={`transcript-risk-badge ${riskBadgeClass(c.risk_status)}`}>
                {c.risk_status} · {c.scam_score}/100
              </span>
            )}
          </div>
          <div className="transcript-text">{c.text}</div>
          {c.scam_label && <div className="transcript-intent">Detected intent: {c.scam_label}</div>}
        </div>
      ))}
    </div>
  );
}
