import { useState, useEffect, useRef } from "react";

interface TypewriterTextProps {
  text: string;
  speed?: number; // milliseconds per character
  className?: string;
  onComplete?: () => void;
  trigger?: string | number; // Change this to re-trigger animation
}

export default function TypewriterText({
  text,
  speed = 30,
  className = "",
  onComplete,
  trigger,
}: TypewriterTextProps) {
  const [displayedText, setDisplayedText] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const currentIndexRef = useRef(0);

  useEffect(() => {
    // Clear any existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    // Reset state
    setDisplayedText("");
    currentIndexRef.current = 0;
    setIsTyping(true);

    const typeNextChar = () => {
      if (currentIndexRef.current < text.length) {
        const nextChar = text[currentIndexRef.current];
        setDisplayedText((prev) => prev + nextChar);
        currentIndexRef.current += 1;

        // Calculate dynamic speed (slightly variable for natural feel)
        const dynamicSpeed = speed + Math.random() * 10 - 5;

        timeoutRef.current = setTimeout(typeNextChar, dynamicSpeed);
      } else {
        setIsTyping(false);
        onComplete?.();
      }
    };

    // Start typing
    timeoutRef.current = setTimeout(typeNextChar, speed);

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [text, speed, trigger, onComplete]);

  return (
    <span className={`typewriter-text ${className} ${isTyping ? "typing" : "complete"}`}>
      {displayedText}
      {isTyping && <span className="typewriter-cursor">|</span>}
    </span>
  );
}
