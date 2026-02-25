import { useState } from "react";

type Props = {
  onAcknowledge: (comment: string) => void;
  onSnooze: (comment: string) => void;
  onAssign: (owner: string, comment: string) => void;
};

export default function AlertControls({ onAcknowledge, onSnooze, onAssign }: Props) {
  const [owner, setOwner] = useState("ops-team");
  const [comment, setComment] = useState("");
  return (
    <div className="alert-controls">
      <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="Owner" />
      <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment" />
      <div className="alert-controls-actions">
        <button onClick={() => onAcknowledge(comment)}>Acknowledge</button>
        <button onClick={() => onSnooze(comment)}>Snooze</button>
        <button onClick={() => onAssign(owner, comment)}>Assign</button>
      </div>
    </div>
  );
}
