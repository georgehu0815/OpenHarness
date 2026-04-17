import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message } from '../types';

export function MessageBubble({ message }: { message: Message }) {
  return (
    <div className={`bubble ${message.role}`}>
      {message.role === 'assistant'
        ? <Markdown remarkPlugins={[remarkGfm]}>{message.text}</Markdown>
        : message.text}
    </div>
  );
}
