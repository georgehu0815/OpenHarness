import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function StreamingBubble({ text }: { text: string }) {
  if (!text) return null;
  return (
    <div className="bubble streaming">
      <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
    </div>
  );
}
