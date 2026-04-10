/**
 * Centripetal Catmull-Rom Spline Utilities
 *
 * Used by SnakeFlow mode to draw smooth organic curves through
 * net-pressure control points. Centripetal (alpha=0.5) avoids
 * cusps and self-intersections that uniform/chordal splines produce.
 *
 * Also includes simple 1D value noise for organic tail wobble.
 */

export interface Vec2 {
  x: number;
  y: number;
}

// ─── Centripetal Catmull-Rom ──────────────────────────────────────────────

const ALPHA = 0.5; // centripetal

function knot(t: number, p0: Vec2, p1: Vec2): number {
  const dx = p1.x - p0.x;
  const dy = p1.y - p0.y;
  return t + Math.pow(dx * dx + dy * dy, ALPHA * 0.5);
}

/**
 * Evaluate a single Catmull-Rom segment between P1 and P2,
 * given surrounding control points P0 and P3.
 *
 * @param t - Parameter 0..1 (0 = at P1, 1 = at P2)
 */
function catmullRomSegment(
  p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, t: number,
): Vec2 {
  const t0 = 0;
  const t1 = knot(t0, p0, p1);
  const t2 = knot(t1, p1, p2);
  const t3 = knot(t2, p2, p3);

  // Map t from [0,1] to [t1, t2]
  const u = t1 + t * (t2 - t1);

  const a1x = ((t1 - u) / (t1 - t0)) * p0.x + ((u - t0) / (t1 - t0)) * p1.x;
  const a1y = ((t1 - u) / (t1 - t0)) * p0.y + ((u - t0) / (t1 - t0)) * p1.y;
  const a2x = ((t2 - u) / (t2 - t1)) * p1.x + ((u - t1) / (t2 - t1)) * p2.x;
  const a2y = ((t2 - u) / (t2 - t1)) * p1.y + ((u - t1) / (t2 - t1)) * p2.y;
  const a3x = ((t3 - u) / (t3 - t2)) * p2.x + ((u - t2) / (t3 - t2)) * p3.x;
  const a3y = ((t3 - u) / (t3 - t2)) * p2.y + ((u - t2) / (t3 - t2)) * p3.y;

  const b1x = ((t2 - u) / (t2 - t0)) * a1x + ((u - t0) / (t2 - t0)) * a2x;
  const b1y = ((t2 - u) / (t2 - t0)) * a1y + ((u - t0) / (t2 - t0)) * a2y;
  const b2x = ((t3 - u) / (t3 - t1)) * a2x + ((u - t1) / (t3 - t1)) * a3x;
  const b2y = ((t3 - u) / (t3 - t1)) * a2y + ((u - t1) / (t3 - t1)) * a3y;

  return {
    x: ((t2 - u) / (t2 - t1)) * b1x + ((u - t1) / (t2 - t1)) * b2x,
    y: ((t2 - u) / (t2 - t1)) * b1y + ((u - t1) / (t2 - t1)) * b2y,
  };
}

/**
 * Full spline through an array of control points.
 * Returns a function getPointAt(t) where t is 0..1 across the entire path.
 */
export class CatmullRomSpline {
  private pts: Vec2[];
  private segCount: number;

  constructor(points: Vec2[]) {
    this.pts = points;
    this.segCount = Math.max(0, points.length - 1);
  }

  get length(): number {
    return this.pts.length;
  }

  /** Get a point along the full spline. t: 0 = start, 1 = end. */
  getPointAt(t: number): Vec2 {
    if (this.pts.length < 2) return this.pts[0] ?? { x: 0, y: 0 };
    if (this.pts.length === 2) {
      return {
        x: this.pts[0].x + (this.pts[1].x - this.pts[0].x) * t,
        y: this.pts[0].y + (this.pts[1].y - this.pts[0].y) * t,
      };
    }

    const clamped = Math.max(0, Math.min(1, t));
    const segFloat = clamped * this.segCount;
    const seg = Math.min(Math.floor(segFloat), this.segCount - 1);
    const local = segFloat - seg;

    // Clamp neighbor indices with phantom extension at edges
    const i0 = Math.max(0, seg - 1);
    const i1 = seg;
    const i2 = Math.min(this.pts.length - 1, seg + 1);
    const i3 = Math.min(this.pts.length - 1, seg + 2);

    return catmullRomSegment(
      this.pts[i0], this.pts[i1], this.pts[i2], this.pts[i3], local,
    );
  }

  /** Approximate tangent at t (unit vector). */
  getTangentAt(t: number): Vec2 {
    const dt = 0.001;
    const a = this.getPointAt(Math.max(0, t - dt));
    const b = this.getPointAt(Math.min(1, t + dt));
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    return { x: dx / len, y: dy / len };
  }

  /** Sample N evenly-spaced points along the spline. */
  sample(count: number): Vec2[] {
    const out: Vec2[] = [];
    for (let i = 0; i < count; i++) {
      out.push(this.getPointAt(i / (count - 1)));
    }
    return out;
  }
}

// ─── Simple 1D Value Noise (for organic tail wobble) ─────────────────────

// Permutation table (deterministic pseudo-random)
const PERM = new Uint8Array(512);
(function initPerm() {
  const p = new Uint8Array(256);
  for (let i = 0; i < 256; i++) p[i] = i;
  // Fisher-Yates shuffle with fixed seed
  let seed = 42;
  for (let i = 255; i > 0; i--) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    const j = seed % (i + 1);
    [p[i], p[j]] = [p[j], p[i]];
  }
  for (let i = 0; i < 512; i++) PERM[i] = p[i & 255];
})();

function fade(t: number): number {
  return t * t * t * (t * (t * 6 - 15) + 10);
}

function grad1d(hash: number, x: number): number {
  return (hash & 1) === 0 ? x : -x;
}

/** 1D Perlin-style value noise. Returns -1..1. */
export function noise1d(x: number): number {
  const xi = Math.floor(x) & 255;
  const xf = x - Math.floor(x);
  const u = fade(xf);
  const a = grad1d(PERM[xi], xf);
  const b = grad1d(PERM[xi + 1], xf - 1);
  return a + u * (b - a);
}
