import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SessionSidebar } from './SessionSidebar';

const sessions = [
  { id: 'a', label: 'Chat A', createdAt: 1 },
  { id: 'b', label: 'Chat B', createdAt: 2 },
];

describe('SessionSidebar', () => {
  it('renders session labels', () => {
    render(<SessionSidebar sessions={sessions} activeId="a" onSelect={vi.fn()} onNew={vi.fn()} activeSessions={[]} />);
    expect(screen.getByText('Chat A')).toBeInTheDocument();
    expect(screen.getByText('Chat B')).toBeInTheDocument();
  });

  it('calls onNew when + New chat is clicked', () => {
    const onNew = vi.fn();
    render(<SessionSidebar sessions={sessions} activeId="a" onSelect={vi.fn()} onNew={onNew} activeSessions={[]} />);
    fireEvent.click(screen.getByText('+ New chat'));
    expect(onNew).toHaveBeenCalledOnce();
  });

  it('marks active session with active class', () => {
    const { container } = render(
      <SessionSidebar sessions={sessions} activeId="b" onSelect={vi.fn()} onNew={vi.fn()} activeSessions={[]} />
    );
    const items = container.querySelectorAll('.session-item');
    expect(items[1]).toHaveClass('active');
  });
});
