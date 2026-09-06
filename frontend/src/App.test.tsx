import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('App', () => {
  it('renders the link form', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>
    );
    expect(screen.getByRole('heading', { name: 'Media Downloader' })).toBeInTheDocument();
    expect(screen.getByLabelText('Paste a YouTube link')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Check link' })).toBeDisabled();
  });
});
