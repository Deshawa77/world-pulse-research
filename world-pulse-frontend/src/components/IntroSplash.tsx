import { useEffect, useMemo } from "react";
import WorldGlobe3D from "./WorldGlobe3D";
import "./intro-splash.css";

type IntroSplashProps = {
  onComplete: () => void;
  forced?: boolean;
};

const INTRO_DURATION_MS = 5200;

export default function IntroSplash({ onComplete, forced = false }: IntroSplashProps) {
  const reduceMotion = useMemo(() => {
    if (forced) return false;
    try {
      return !!window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    } catch {
      return false;
    }
  }, [forced]);

  useEffect(() => {
    if (forced) return;

    const timeout = window.setTimeout(onComplete, reduceMotion ? 3800 : INTRO_DURATION_MS);
    return () => window.clearTimeout(timeout);
  }, [onComplete, forced, reduceMotion]);

  return (
    <div className={`wp-intro${reduceMotion ? " wp-intro--reduced" : ""}`} role="status" aria-live="polite" aria-label="Loading The World's Pulse">
      <div className="wp-intro-brand">
        <div className="wp-intro-google-squares">
          <div className="wp-intro-google-square"></div>
          <div className="wp-intro-google-square"></div>
          <div className="wp-intro-google-square"></div>
          <div className="wp-intro-google-square"></div>
        </div>
        <div className="wp-intro-globe-shell" aria-hidden="true">
          <WorldGlobe3D data={[]} autoRotate rotationSpeed={2.2} showActivityDots={false} visualPreset="introCinematic" height="100%" />
        </div>

        <h1 className="wp-intro-title">THE WORLD'S PULSE</h1>
        <p className="wp-intro-subtitle">Reality Interface Initializing</p>
      </div>

      <div className="wp-intro-actions">
        <button type="button" className="wp-intro-skip" onClick={onComplete}>
          {forced ? "Enter Platform" : "Skip Intro"}
        </button>
      </div>
    </div>
  );
}
