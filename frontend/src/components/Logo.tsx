import { useId } from 'react';

/** Знак Gigo: булавка карты, в которую вписана «G». Исходники — public/logo.svg, public/favicon.svg, docs/brand/. */
function GlyphMask({ id }: { id: string }) {
  return (
    <mask id={id} maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">
      <path d="M29 60A27 27 0 1 1 71 60L54.2 82.5Q50 88 45.8 82.5Z" fill="#fff" />
      <circle cx="50" cy="43" r="12" fill="#000" />
      <path d="M50 43L76 9H100V41H50Z" fill="#000" />
      <path d="M50 41H76.93A27 27 0 0 1 75.46 52H50Z" fill="#fff" />
    </mask>
  );
}

export function LogoMark({ size = 40 }: { size?: number }) {
  const id = `gm${useId().replace(/:/g, '')}`;
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true" focusable="false" className="logo-mark">
      <defs>
        <GlyphMask id={id} />
      </defs>
      <rect width="100" height="100" rx="26" fill="var(--brand)" />
      <rect width="100" height="100" fill="#fff" mask={`url(#${id})`} />
    </svg>
  );
}

/** Знак + надпись «gigo» (цвет надписи — currentColor). */
export function Logo({ height = 32 }: { height?: number }) {
  const id = `gl${useId().replace(/:/g, '')}`;
  return (
    <svg height={height} width={(height * 292) / 100} viewBox="0 0 292 100" role="img" aria-label="Gigo" className="logo" focusable="false">
      <defs>
        <GlyphMask id={id} />
      </defs>
      <rect width="100" height="100" rx="26" fill="var(--brand)" />
      <rect width="100" height="100" fill="#fff" mask={`url(#${id})`} />
      <g fill="none" stroke="currentColor" strokeWidth="12" strokeLinecap="round">
        <circle cx="140" cy="50" r="14" />
        <path d="M154 36V74A14 14 0 0 1 127.9 81" />
        <path d="M178 36V64" />
        <circle cx="216" cy="50" r="14" />
        <path d="M230 36V74A14 14 0 0 1 203.9 81" />
        <circle cx="270" cy="50" r="14" />
      </g>
      <circle cx="178" cy="17" r="7" fill="currentColor" />
    </svg>
  );
}
