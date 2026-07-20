import { useCallback, useEffect, useState } from "react";

/**
 * Lets the user pick which microphone to use for the WebRTC call. Device
 * labels are blank until getUserMedia has been granted at least once, so
 * requestPermission() grabs a throwaway stream just to unlock them, then
 * immediately stops it — the real stream (with the chosen deviceId) is
 * requested later by useWebRTCCall when the call actually starts.
 */
export function useAudioDevices() {
  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [permission, setPermission] = useState("prompt"); // prompt | granted | denied
  const [error, setError] = useState(null);

  const refreshDevices = useCallback(async () => {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      const mics = all.filter((d) => d.kind === "audioinput");
      setDevices(mics);
      setSelectedDeviceId((prev) => (prev && mics.some((m) => m.deviceId === prev) ? prev : mics[0]?.deviceId || ""));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const requestPermission = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      setPermission("granted");
      setError(null);
      await refreshDevices();
    } catch (e) {
      setPermission("denied");
      setError(e.message);
    }
  }, [refreshDevices]);

  useEffect(() => {
    if (!navigator.mediaDevices?.enumerateDevices) return undefined;
    refreshDevices();
    const onChange = () => refreshDevices();
    navigator.mediaDevices.addEventListener("devicechange", onChange);
    return () => navigator.mediaDevices.removeEventListener("devicechange", onChange);
  }, [refreshDevices]);

  return {
    devices,
    selectedDeviceId,
    setSelectedDeviceId,
    permission,
    requestPermission,
    error,
  };
}
