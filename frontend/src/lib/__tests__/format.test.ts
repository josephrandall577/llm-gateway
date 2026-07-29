import { afterEach, describe, expect, it, vi } from 'vitest';
import { copyToClipboard } from '../utils/format';

afterEach(() => vi.unstubAllGlobals());

describe('copyToClipboard', () => {
  it('falls back when Clipboard API fails', async () => {
    const textarea = {
      value: '',
      style: {},
      setAttribute: vi.fn(),
      focus: vi.fn(),
      select: vi.fn(),
      remove: vi.fn(),
    };
    const execCommand = vi.fn(() => true);

    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    });
    vi.stubGlobal('document', {
      createElement: vi.fn(() => textarea),
      body: { appendChild: vi.fn() },
      execCommand,
    });

    await expect(copyToClipboard('lgw-test')).resolves.toBe(true);
    expect(textarea.value).toBe('lgw-test');
    expect(execCommand).toHaveBeenCalledWith('copy');
  });
});
