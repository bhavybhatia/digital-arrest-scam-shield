// Dialpad input only ever produces raw digits (0-9 * #), while configured
// numbers (VITE_*_NUMBER) are formatted with "+91" and spaces. Comparing
// them for equality needs to ignore that formatting difference.
export function normalizePhoneNumber(number) {
  return (number || "").replace(/\D/g, "").slice(-10);
}

export function isSamePhoneNumber(a, b) {
  const normA = normalizePhoneNumber(a);
  const normB = normalizePhoneNumber(b);
  return Boolean(normA) && normA === normB;
}
