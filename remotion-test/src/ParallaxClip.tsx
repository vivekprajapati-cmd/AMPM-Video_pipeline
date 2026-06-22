import React from "react";
import {
  AbsoluteFill,
  staticFile,
  spring,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";

export type Beat = "Finance" | "Business" | "Politics" | "Culture" | "GlobalAffairs";

const IMG: React.CSSProperties = { width: "100%", height: "100%", objectFit: "cover" };

// ════════════════════════════════════════════════════════════════════════════
// CORE PRIMITIVES — industry-standard building blocks only
// ════════════════════════════════════════════════════════════════════════════

// Vignette — always on, every professional news clip has this
const Vignette: React.FC<{ opacity: number; falloff?: string; pulse?: number }> = ({
  opacity, falloff = "50%", pulse = 0,
}) => (
  <AbsoluteFill style={{
    background: `radial-gradient(ellipse at center, transparent ${falloff}, rgba(0,0,0,${opacity + pulse}) 100%)`,
    pointerEvents: "none",
  }} />
);

// Light sweep — single pass of directional light across the frame
// One per clip max. Cinematic without being decorative.
const LightSweep: React.FC<{
  progress: number;        // 0 → 1 over desired duration
  opacity: number;
  direction?: "left" | "right" | "up";
  color?: string;
}> = ({ progress, opacity, direction = "right", color = "rgba(255,255,255,1)" }) => {
  const pos = progress * 130 - 15; // travels -15% to 115%
  let gradient = "";
  if (direction === "right") {
    gradient = `linear-gradient(to right, transparent, ${color} ${pos}%, transparent ${pos + 18}%, transparent)`;
  } else if (direction === "left") {
    gradient = `linear-gradient(to left, transparent, ${color} ${100 - pos}%, transparent ${100 - pos + 18}%, transparent)`;
  } else {
    gradient = `linear-gradient(to bottom, transparent, ${color} ${pos}%, transparent ${pos + 18}%, transparent)`;
  }
  return (
    <AbsoluteFill style={{
      background: gradient,
      opacity,
      pointerEvents: "none",
      mixBlendMode: "screen",
      filter: "blur(6px)",
    }} />
  );
};

// Edge glow — brand color bleeding from edges, defines the show's identity
const EdgeGlow: React.FC<{
  color: string; opacity: number;
  sides: ("left" | "right" | "top" | "bottom")[];
}> = ({ color, opacity, sides }) => {
  const parts: string[] = [];
  if (sides.includes("left"))   parts.push(`linear-gradient(to right, ${color}, transparent 20%)`);
  if (sides.includes("right"))  parts.push(`linear-gradient(to left,  ${color}, transparent 20%)`);
  if (sides.includes("top"))    parts.push(`linear-gradient(to bottom,${color}, transparent 20%)`);
  if (sides.includes("bottom")) parts.push(`linear-gradient(to top,   ${color}, transparent 20%)`);
  return (
    <AbsoluteFill style={{
      background: parts.join(", "),
      opacity,
      pointerEvents: "none",
      mixBlendMode: "screen",
    }} />
  );
};

// Scanlines — broadcast/documentary texture, used in news consistently
const Scanlines: React.FC<{ opacity: number }> = ({ opacity }) => (
  <AbsoluteFill style={{
    backgroundImage: `repeating-linear-gradient(0deg,
      rgba(0,0,0,${opacity}) 0px, rgba(0,0,0,${opacity}) 1px,
      transparent 1px, transparent 4px)`,
    pointerEvents: "none",
  }} />
);

// Corner brackets + data line — Bloomberg/CNBC standard for finance
const CornerBrackets: React.FC<{ progress: number; color: string }> = ({ progress, color }) => {
  const s = 48 * Math.min(progress, 1);
  const op = Math.min(progress, 1);
  const corner = (top: boolean, left: boolean): React.CSSProperties => ({
    position: "absolute",
    [top ? "top" : "bottom"]: 24,
    [left ? "left" : "right"]: 24,
    width: s, height: s,
    borderTop:    top  ? `2px solid ${color}` : "none",
    borderBottom: !top ? `2px solid ${color}` : "none",
    borderLeft:   left  ? `2px solid ${color}` : "none",
    borderRight:  !left ? `2px solid ${color}` : "none",
    opacity: op, boxSizing: "border-box",
  });
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div style={corner(true,  true)} />  <div style={corner(true,  false)} />
      <div style={corner(false, true)} />  <div style={corner(false, false)} />
    </AbsoluteFill>
  );
};

const DataLine: React.FC<{ progress: number; color: string; y: string }> = ({ progress, color, y }) => (
  <AbsoluteFill style={{ pointerEvents: "none" }}>
    <div style={{
      position: "absolute", top: y, left: "5%",
      height: "1px", width: `${Math.min(progress * 90, 90)}%`,
      backgroundColor: color,
      boxShadow: `0 0 8px ${color}`,
      opacity: Math.min(progress * 2, 0.85),
    }} />
    <div style={{
      position: "absolute", top: y,
      left: `${4.5 + Math.min(progress * 90, 90)}%`,
      width: 5, height: 5, borderRadius: "50%",
      backgroundColor: color, transform: "translateY(-2px)",
      boxShadow: `0 0 10px ${color}`,
      opacity: Math.min(progress * 3, 1),
    }} />
  </AbsoluteFill>
);


// ════════════════════════════════════════════════════════════════════════════
// BEAT COMPONENTS
// ════════════════════════════════════════════════════════════════════════════

// ── FINANCE ───────────────────────────────────────────────────────────────
// Motion: staccato push-in — hard scale jumps at keyframes, not smooth spring
//         Feels like a data chart. Precise, mechanical.
// Grade:  cold, desaturated, high contrast. Bloomberg terminal at 2am.
// Extra:  corner brackets + data line draw (industry standard for finance)
const FinanceClip: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Hard scale steps — jumps between values, not interpolated smoothly
  // This is what makes Finance feel different from every other beat
  const scale = interpolate(frame,
    [0,   8,   9,    24,  25,   60,  61,   150],
    [1.0, 1.0, 1.18, 1.18, 1.28, 1.28, 1.22, 1.22],
    { extrapolateRight: "clamp" }
  );
  const panX = interpolate(frame, [0, 150], [-3, -10], { extrapolateRight: "clamp" });
  const panY = interpolate(frame, [0, 150], [0,  -4],  { extrapolateRight: "clamp" });

  // Background — opposite direction, blurred
  const bgScale = interpolate(frame, [0, 150], [1.45, 1.55], { extrapolateRight: "clamp" });
  const bgX     = interpolate(frame, [0, 150], [12, 18],     { extrapolateRight: "clamp" });

  // Grade: cold, desaturated, sharp
  const grade = "contrast(1.22) saturate(0.65) brightness(0.93) hue-rotate(-8deg)";

  // Light sweep — single pass, cold white, left-to-right at ~1s
  const sweepProg = interpolate(frame, [8, 55], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const sweepOp   = interpolate(frame, [8, 20, 48, 55], [0, 0.18, 0.14, 0], { extrapolateRight: "clamp" });

  // Effects
  const bracketProg = spring({ frame, fps, config: { damping: 20, stiffness: 60 }, from: 0, to: 1, durationInFrames });
  const lineProg    = spring({ frame, fps, config: { damping: 200, stiffness: 25 }, from: 0, to: 1, durationInFrames });
  const vigOp       = interpolate(frame, [0, 20], [0, 0.38], { extrapolateRight: "clamp" });
  const glowOp      = interpolate(frame, [0, 30, 80], [0, 0.22, 0.16], { extrapolateRight: "clamp" });

  // Entry: 2-frame lime flash — imperceptible as hold, just feels like a cut
  const flashOp = frame <= 2 ? interpolate(frame, [0, 2], [0.80, 0], { extrapolateRight: "clamp" }) : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#060810", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${bgScale}) translateX(${bgX}px)`, filter: `${grade} blur(8px)`, opacity: 0.45 }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
      <AbsoluteFill style={{ transform: `scale(${scale}) translate(${panX}px, ${panY}px)`, filter: grade }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
      {/* Cold blue tint */}
      <AbsoluteFill style={{ backgroundColor: "rgba(5,15,40,1)", opacity: 0.09, pointerEvents: "none" }} />
      <Vignette opacity={vigOp} falloff="52%" />
      <Scanlines opacity={0.09} />
      <LightSweep progress={sweepProg} opacity={sweepOp} direction="right" color="rgba(200,220,255,1)" />
      <CornerBrackets progress={bracketProg} color="#AAFF47" />
      <DataLine progress={lineProg} color="#AAFF47" y="80%" />
      <EdgeGlow color="rgba(170,255,71,0.7)" opacity={glowOp} sides={["left", "right"]} />
      {flashOp > 0 && <AbsoluteFill style={{ backgroundColor: "#AAFF47", opacity: flashOp, pointerEvents: "none" }} />}
    </AbsoluteFill>
  );
};


// ── BUSINESS ──────────────────────────────────────────────────────────────
// Motion: continuous upward drift — linear, never stops, entire clip rises
//         Feels like momentum, aspiration, Series A energy.
// Grade:  warm golden hour, amber-cream, slight overexposure in highlights
// Extra:  amber light sweep rising from bottom
const BusinessClip: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Continuous rise — linear drift, scale grows slightly while rising
  const driftY = interpolate(frame, [0, 150], [0,   -30], { extrapolateRight: "clamp" });
  const scale  = interpolate(frame, [0, 150], [1.12, 1.22], { extrapolateRight: "clamp" });

  // Background rises slower — parallax depth
  const bgDrift = interpolate(frame, [0, 150], [0,  -14], { extrapolateRight: "clamp" });
  const bgScale = interpolate(frame, [0, 150], [1.38, 1.46], { extrapolateRight: "clamp" });

  // Grade: warm, golden, slight overexposure
  const grade = "contrast(1.06) saturate(1.18) brightness(1.05) sepia(0.10)";

  // Light sweep — amber rising from bottom (matches upward motion)
  const sweepY  = interpolate(frame, [10, 120], [105, -30], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const sweepOp = interpolate(frame, [10, 30, 95, 120], [0, 0.28, 0.24, 0], { extrapolateRight: "clamp" });

  const vigOp  = interpolate(frame, [0, 20], [0, 0.42], { extrapolateRight: "clamp" });
  const glowOp = interpolate(frame, [0, 40, 90], [0, 0.20, 0.16], { extrapolateRight: "clamp" });

  // Entry: lime sweep line wipes across
  const wipeX  = interpolate(frame, [0, 20], [-105, 115], { extrapolateRight: "clamp" });
  const wipeOp = interpolate(frame, [0, 2, 16, 24], [0, 1, 1, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0D0906", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${bgScale}) translateY(${bgDrift}px)`, filter: `${grade} blur(9px)`, opacity: 0.50 }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
      <AbsoluteFill style={{ transform: `scale(${scale}) translateY(${driftY}px)`, filter: grade }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
      {/* Warm amber tint */}
      <AbsoluteFill style={{ backgroundColor: "rgba(80,40,0,1)", opacity: 0.07, pointerEvents: "none" }} />
      {/* Amber light sweep rising from bottom */}
      <AbsoluteFill style={{ pointerEvents: "none", overflow: "hidden" }}>
        <div style={{
          position: "absolute", left: 0, right: 0,
          top: `${sweepY}%`, height: "55%",
          background: "linear-gradient(to top, rgba(255,165,30,0.9) 0%, transparent 100%)",
          opacity: sweepOp, mixBlendMode: "screen", filter: "blur(10px)",
        }} />
      </AbsoluteFill>
      <Vignette opacity={vigOp} falloff="55%" />
      <EdgeGlow color="rgba(255,160,30,0.8)" opacity={glowOp} sides={["bottom"]} />
      {/* Entry sweep line */}
      <AbsoluteFill style={{ pointerEvents: "none", overflow: "hidden" }}>
        <div style={{
          position: "absolute", top: "50%", left: 0, right: 0,
          height: "3px", backgroundColor: "#AAFF47",
          transform: `translateX(${wipeX}%)`, opacity: wipeOp,
          boxShadow: "0 0 16px #AAFF47, 0 0 5px #AAFF47",
        }} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};


// ── POLITICS ──────────────────────────────────────────────────────────────
// Motion: weighted push-in with entry camera wobble, then locks
//         High mass spring = heavy, overshoots slightly. Handheld news camera feel.
// Grade:  near-monochrome, crushed blacks, cold. Consequence and gravity.
// Extra:  scanlines (documentary texture), breathing vignette
const PoliticsClip: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Heavy weighted push — mass 2.2, overshoots and locks
  const scale = spring({ frame, fps, config: { damping: 60, stiffness: 18, mass: 2.2 }, from: 1.0, to: 1.18, durationInFrames });
  const panX  = spring({ frame, fps, config: { damping: 60, stiffness: 18, mass: 2.2 }, from: 0, to: -6, durationInFrames });
  const panY  = spring({ frame, fps, config: { damping: 60, stiffness: 18, mass: 2.2 }, from: 0, to: -3, durationInFrames });

  // Entry wobble — handheld camera on cut-in, frames 0–6
  const wobbleX = interpolate(frame, [0, 1, 2, 3, 4, 5, 6], [0, -5, 7, -4, 3, -1, 0], { extrapolateRight: "clamp" });
  const wobbleY = interpolate(frame, [0, 1, 2, 3, 4, 5, 6], [0,  2, -4,  2, -1,  1, 0], { extrapolateRight: "clamp" });

  // Background — minimal movement, creates depth
  const bgScale = spring({ frame, fps, config: { damping: 200, stiffness: 4, mass: 3 }, from: 1.45, to: 1.52, durationInFrames });
  const bgX     = interpolate(frame, [0, 150], [8, 12], { extrapolateRight: "clamp" });

  // Grade: heavily desaturated, crushed blacks, cold shift
  const grade = "contrast(1.20) saturate(0.52) brightness(0.87) hue-rotate(-5deg)";

  // Light sweep — cold, single pass at ~1.5s, subtle
  const sweepProg = interpolate(frame, [20, 70], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const sweepOp   = interpolate(frame, [20, 35, 60, 70], [0, 0.14, 0.10, 0], { extrapolateRight: "clamp" });

  // Vignette breathes — tension effect
  const vigBase = interpolate(frame, [0, 20], [0, 0.78], { extrapolateRight: "clamp" });
  const vPulse  = Math.sin(frame * 0.04) * 0.05;

  const glowOp = interpolate(frame, [0, 30, 80], [0, 0.32, 0.26], { extrapolateRight: "clamp" });

  // Entry: 2-frame red flash + 10-frame crush dissolve (no solid black hold)
  const redFlash = frame <= 2 ? interpolate(frame, [0, 2], [0.55, 0], { extrapolateRight: "clamp" }) : 0;
  const crushOp  = interpolate(frame, [0, 10], [0.60, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#080404", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${bgScale}) translateX(${bgX}px)`, filter: `${grade} blur(9px)`, opacity: 0.50 }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
      <AbsoluteFill style={{
        transform: `scale(${scale}) translate(${panX + wobbleX}px, ${panY + wobbleY}px)`,
        filter: grade,
      }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
      {/* Dark red tint */}
      <AbsoluteFill style={{ backgroundColor: "rgba(60,0,0,1)", opacity: 0.12, pointerEvents: "none" }} />
      {/* Breathing vignette */}
      <AbsoluteFill style={{
        background: `radial-gradient(ellipse at center, transparent 36%, rgba(0,0,0,${vigBase + vPulse}) 100%)`,
        pointerEvents: "none",
      }} />
      <Scanlines opacity={0.13} />
      <LightSweep progress={sweepProg} opacity={sweepOp} direction="right" color="rgba(180,180,200,1)" />
      <EdgeGlow color="rgba(180,0,0,0.9)" opacity={glowOp} sides={["left", "right", "top"]} />
      {/* Entry */}
      {redFlash > 0 && <AbsoluteFill style={{ backgroundColor: "#ef4444", opacity: redFlash, pointerEvents: "none" }} />}
      <AbsoluteFill style={{ backgroundColor: "#000", opacity: crushOp, pointerEvents: "none" }} />
    </AbsoluteFill>
  );
};


// ── CULTURE ───────────────────────────────────────────────────────────────
// Motion: restless — 3 direction changes in 5s, snap zoom then bounce then drift
//         Never commits to one direction. TikTok / social-native energy.
// Grade:  oversaturated, high vibrance, warm-cool split. Maximalist.
// Extra:  RGB glitch on entry (NowThis/Vice/Vox standard for culture beats)
const CultureClip: React.FC = () => {
  const frame = useCurrentFrame();

  // Phase 1 (0–8f): snap zoom in — fast
  // Phase 2 (8–70f): hold, drift right
  // Phase 3 (70–150f): bounce left, slight pull-back — restless
  const scale = interpolate(frame,
    [0, 8,    40,   70,   150],
    [1.0, 1.38, 1.38, 1.30, 1.26],
    { extrapolateRight: "clamp" }
  );
  const panX = interpolate(frame,
    [0, 8,   40,  70,   150],
    [0, -14, -14,  10,   -6],
    { extrapolateRight: "clamp" }
  );
  const panY = interpolate(frame,
    [0, 8,  60,  150],
    [0, -8, -6,  -12],
    { extrapolateRight: "clamp" }
  );

  // Background moves opposite at each phase
  const bgScale = interpolate(frame, [0, 150], [1.35, 1.58], { extrapolateRight: "clamp" });
  const bgX     = interpolate(frame, [0, 8, 40, 70, 150], [0, 18, 18, -10, 8], { extrapolateRight: "clamp" });
  const bgY     = interpolate(frame, [0, 150], [0, 14], { extrapolateRight: "clamp" });

  // Grade: high saturation, vibrant, slight warm push
  const grade = "contrast(1.05) saturate(1.60) brightness(1.04) hue-rotate(5deg)";

  // Light sweep — warm diagonal, fast pass at start
  const sweepProg = interpolate(frame, [6, 40], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const sweepOp   = interpolate(frame, [6, 15, 32, 40], [0, 0.22, 0.16, 0], { extrapolateRight: "clamp" });

  const vigOp  = interpolate(frame, [0, 20], [0, 0.48], { extrapolateRight: "clamp" });
  const glowOp = interpolate(frame, [0, 30, 80], [0, 0.24, 0.18], { extrapolateRight: "clamp" });

  // Entry: RGB glitch — industry standard for social/culture (NowThis, Vice, Vox)
  const gx  = interpolate(frame, [0, 1, 2, 3, 4, 5], [12, -8, 5, -3, 2, 0], { extrapolateRight: "clamp" });
  const hue = interpolate(frame, [0, 1, 2, 3, 4, 5], [80, -60, 30, -15, 5, 0], { extrapolateRight: "clamp" });
  const gOp = interpolate(frame, [0, 1, 8], [1, 1, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#080008", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${bgScale}) translate(${bgX}px, ${bgY}px)`, filter: `${grade} blur(8px)`, opacity: 0.50 }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
      <AbsoluteFill style={{ transform: `scale(${scale}) translate(${panX}px, ${panY}px)`, filter: grade }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
      {/* Purple tint */}
      <AbsoluteFill style={{ backgroundColor: "rgba(80,0,120,1)", opacity: 0.09, pointerEvents: "none" }} />
      <Vignette opacity={vigOp} falloff="46%" />
      <LightSweep progress={sweepProg} opacity={sweepOp} direction="right" color="rgba(255,220,100,1)" />
      <EdgeGlow color="rgba(170,255,71,0.8)" opacity={glowOp} sides={["left", "right"]} />
      {/* RGB glitch entry — image copy with hue shift, not a color frame */}
      <AbsoluteFill style={{
        transform: `translateX(${gx}px)`,
        filter: `hue-rotate(${hue}deg) brightness(1.9)`,
        opacity: gOp, pointerEvents: "none", mixBlendMode: "screen",
      }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};


// ── GLOBAL AFFAIRS ────────────────────────────────────────────────────────
// Motion: slow pull-back — starts tight, reveals outward over full clip
//         Opposite of every other beat. Documentary reveal.
// Grade:  sepia-split tone, cold highlights, warm shadows, haze. Distant, heavy.
// Extra:  vignette open entry (edge darkness pulls back, image always visible)
const GlobalAffairsClip: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Pull-back — starts zoomed in, slowly reveals. Mass 3 = very slow, deliberate.
  const scale = spring({ frame, fps, config: { damping: 200, stiffness: 5, mass: 3.0 }, from: 1.45, to: 1.08, durationInFrames });
  const panX  = spring({ frame, fps, config: { damping: 200, stiffness: 5, mass: 3.0 }, from: -8, to:  3, durationInFrames });
  const panY  = spring({ frame, fps, config: { damping: 200, stiffness: 5, mass: 3.0 }, from: -4, to:  1, durationInFrames });

  // Background moves inward slowly — opposite direction to foreground
  const bgScale = spring({ frame, fps, config: { damping: 200, stiffness: 3, mass: 3.0 }, from: 1.35, to: 1.50, durationInFrames });
  const bgX     = interpolate(frame, [0, 150], [0, 5], { extrapolateRight: "clamp" });

  // Grade: sepia-split tone, desaturated, cold highlights, warm shadows, haze
  const grade = "contrast(1.10) saturate(0.55) brightness(0.85) sepia(0.25) hue-rotate(-12deg)";

  // Light sweep — single slow pass, warm amber, ~2s in
  const sweepProg = interpolate(frame, [30, 90], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const sweepOp   = interpolate(frame, [30, 50, 80, 90], [0, 0.15, 0.12, 0], { extrapolateRight: "clamp" });

  // Film haze — diffusion layer, like satellite feed
  const hazeOp = interpolate(frame, [0, 40], [0, 0.07], { extrapolateRight: "clamp" });

  // Vignette — deep, documentary
  const vigOp = interpolate(frame, [0, 30], [0, 0.88], { extrapolateRight: "clamp" });

  // Entry: vignette open — image always present, extreme darkness at edges pulls back
  const entryVig = interpolate(frame, [0, 35], [0.75, 0], { extrapolateRight: "clamp" });

  const glowOp = interpolate(frame, [0, 40, 100], [0, 0.25, 0.20], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#050301", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${bgScale}) translateX(${bgX}px)`, filter: `${grade} blur(10px)`, opacity: 0.48 }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
      <AbsoluteFill style={{ transform: `scale(${scale}) translate(${panX}px, ${panY}px)`, filter: grade }}>
        <img src={staticFile("image.jpg")} style={IMG} />
      </AbsoluteFill>
      {/* Warm shadow tint */}
      <AbsoluteFill style={{ backgroundColor: "rgba(20,12,4,1)", opacity: 0.16, pointerEvents: "none" }} />
      {/* Film haze */}
      <AbsoluteFill style={{ backgroundColor: "rgba(200,160,80,1)", opacity: hazeOp, pointerEvents: "none", mixBlendMode: "soft-light" }} />
      {/* Deep documentary vignette */}
      <Vignette opacity={vigOp} falloff="34%" />
      <Scanlines opacity={0.07} />
      <LightSweep progress={sweepProg} opacity={sweepOp} direction="right" color="rgba(220,180,100,1)" />
      <EdgeGlow color="rgba(80,40,8,0.9)" opacity={glowOp} sides={["left", "right", "bottom"]} />
      {/* Entry: vignette open — image always visible, darkness pulls back from edges */}
      <AbsoluteFill style={{
        background: `radial-gradient(ellipse at center, rgba(0,0,0,0.50) 0%, rgba(5,3,1,1) 100%)`,
        opacity: entryVig,
        pointerEvents: "none",
      }} />
    </AbsoluteFill>
  );
};


// ════════════════════════════════════════════════════════════════════════════
// ROUTER
// ════════════════════════════════════════════════════════════════════════════

export const ParallaxClip: React.FC<{ beat: Beat }> = ({ beat }) => {
  switch (beat) {
    case "Finance":       return <FinanceClip />;
    case "Business":      return <BusinessClip />;
    case "Politics":      return <PoliticsClip />;
    case "Culture":       return <CultureClip />;
    case "GlobalAffairs": return <GlobalAffairsClip />;
  }
};
