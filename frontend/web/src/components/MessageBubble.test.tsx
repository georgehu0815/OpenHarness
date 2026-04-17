import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MessageBubble } from './MessageBubble';

describe('MessageBubble', () => {
  it('renders user message with user class', () => {
    const { container } = render(<MessageBubble message={{ id: '1', role: 'user', text: 'Hello' }} />);
    expect(container.firstChild).toHaveClass('user');
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders assistant message with assistant class', () => {
    const { container } = render(<MessageBubble message={{ id: '2', role: 'assistant', text: 'Hi there' }} />);
    expect(container.firstChild).toHaveClass('assistant');
  });
});
