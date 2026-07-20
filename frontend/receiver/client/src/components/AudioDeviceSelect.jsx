export default function AudioDeviceSelect({
  devices,
  selectedDeviceId,
  onChange,
  permission,
  onRequestPermission,
  error,
}) {
  if (permission !== "granted") {
    return (
      <div className="audio-device-select">
        <button type="button" className="audio-device-permission-btn" onClick={onRequestPermission}>
          🎙️ Enable microphone
        </button>
        {error && <div className="audio-device-error">{error}</div>}
      </div>
    );
  }

  return (
    <div className="audio-device-select">
      <label className="audio-device-label" htmlFor="audio-device">
        🎙️ Microphone
      </label>
      <select
        id="audio-device"
        className="audio-device-dropdown"
        value={selectedDeviceId}
        onChange={(e) => onChange(e.target.value)}
      >
        {devices.map((d, i) => (
          <option key={d.deviceId} value={d.deviceId}>
            {d.label || `Microphone ${i + 1}`}
          </option>
        ))}
      </select>
    </div>
  );
}
