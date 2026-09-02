export function isRenderableBbox(bbox?: number[]): bbox is number[] {
  return (
    Array.isArray(bbox) &&
    bbox.length === 4 &&
    bbox.every((value) => Number.isFinite(value)) &&
    bbox[2] !== bbox[0] &&
    bbox[3] !== bbox[1]
  );
}

export function bboxStyle(bbox: number[]): string {
  const left = Math.min(bbox[0], bbox[2]) / 10;
  const top = Math.min(bbox[1], bbox[3]) / 10;
  const width = Math.abs(bbox[2] - bbox[0]) / 10;
  const height = Math.abs(bbox[3] - bbox[1]) / 10;
  return `left:${left}%;top:${top}%;width:${width}%;height:${height}%`;
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
}
