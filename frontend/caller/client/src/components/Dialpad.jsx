import { useState } from "react";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];

export default function Dialpad({ ownNumber, hint, onCall, disabled }) {
  const [number, setNumber] = useState("");

  const press = (k) => setNumber((n) => n + k);
  const backspace = () => setNumber((n) => n.slice(0, -1));

  return (
    <div className="dialpad">
      <div className="dialpad-own-number">Your number: {ownNumber}</div>
      {hint && <div className="dialpad-hint">{hint}</div>}

      <div className="dialpad-display">{number || "Enter a number"}</div>

      <div className="dialpad-keys">
        {KEYS.map((k) => (
          <button key={k} className="dialpad-key" onClick={() => press(k)}>
            {k}
          </button>
        ))}
      </div>

      <div className="dialpad-actions">
        <button
          className="btn btn-danger btn-round"
          onClick={backspace}
          disabled={!number}
          aria-label="Backspace"
        >
          ⌫
        </button>
        <button
          className="btn btn-call btn-round"
          onClick={() => onCall(number)}
          disabled={!number || disabled}
          aria-label="Call"
        >
          📞
        </button>
      </div>
    </div>
  );
}
