export default function PhoneFrame({ label, children }) {
  return (
    <div className="phone-wrap">
      {label && <div className="phone-label">{label}</div>}
      <div className="phone-frame">
        <div className="phone-notch" />
        <div className="phone-screen">{children}</div>
        <div className="phone-home-bar" />
      </div>
    </div>
  );
}
