import { lineColor } from '../format';

export function MetroDot({ color, title }: { color: string | null | undefined; title?: string | null }) {
  return <span className="metro-dot" style={{ background: lineColor(color) }} title={title ?? undefined} aria-hidden="true" />;
}
