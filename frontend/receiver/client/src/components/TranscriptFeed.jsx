export default function TranscriptFeed({ chunks }) {
  return (
    <div className="transcript-feed">
      {chunks.length === 0 && (
        <div className="transcript-empty">Listening… live transcript will appear here.</div>
      )}
      {chunks.map((c) => (
        <div key={c.index} className="transcript-line">
          <div className="transcript-timestamp">{c.timestamp}</div>
          <div className="transcript-text">{c.text}</div>
        </div>
      ))}
    </div>
  );
}
