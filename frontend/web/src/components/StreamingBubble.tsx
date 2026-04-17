export function StreamingBubble({ text }: { text: string }) {
  if (!text) return null;
  return <div className="bubble streaming">{text}</div>;
}
