/** The bulb from the logo, hanging from the top of the hero. It lights up on load. */
function Lamp({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 520 640" className={className} aria-hidden="true">
      <defs>
        <radialGradient id="lamp-glow">
          <stop offset="0" stopColor="#64ffda" stopOpacity="0.34" />
          <stop offset="0.45" stopColor="#64ffda" stopOpacity="0.11" />
          <stop offset="1" stopColor="#64ffda" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="lamp-glass">
          <stop offset="0" stopColor="#d9fff5" stopOpacity="0.95" />
          <stop offset="0.3" stopColor="#64ffda" stopOpacity="0.55" />
          <stop offset="1" stopColor="#64ffda" stopOpacity="0.07" />
        </radialGradient>
      </defs>

      <path d="M260 0V142" stroke="#3a5478" strokeWidth="4" />
      <circle className="lamp-on" cx="260" cy="395" r="260" fill="url(#lamp-glow)" />
      <path
        className="lamp-on"
        d="M224 232 180 296A130 130 0 1 0 340 296L296 232Z"
        fill="url(#lamp-glass)"
      />
      <g fill="none" stroke="#64ffda" strokeLinecap="round" strokeLinejoin="round">
        <path strokeWidth="20" d="M244 154h32M228 190h64" />
        <path strokeWidth="16" d="M224 232 180 296A130 130 0 1 0 340 296L296 232" />
      </g>
    </svg>
  );
}

export default Lamp;
