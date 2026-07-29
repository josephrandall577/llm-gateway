import { afterEach, describe, expect, it, vi } from 'vitest';
import { copyToClipboard } from '../utils/format';

afterEach(() => vi.unstubAllGlobals());

describe('copyToClipboard', () => {
  it('uses the synchronous fallback before Clipboard API', async () => {
    const textarea = {
      value: '',
      style: {},
      setAttribute: vi.fn(),
      focus: vi.fn(),
      select: vi.fn(),
      remove: vi.fn(),
    };
    const execCommand = vi.fn(() => true);
    const writeText = vi.fn().mockRejectedValue(new Error('denied'));
    const dialog = { appendChild: vi.fn() };

    vi.stubGlobal('navigator', {
      clipboard: { writeText },
    });
    vi.stubGlobal('document', {
      createElement: vi.fn(() => textarea),
      body: { appendChild: vi.fn() },
      activeElement: { closest: vi.fn(() => dialog) },
      execCommand,
    });

    await expect(copyToClipboard('lgw-test')).resolves.toBe(true);
    expect(textarea.value).toBe('lgw-test');
    expect(dialog.appendChild).toHaveBeenCalledWith(textarea);
    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(writeText).not.toHaveBeenCalled();
  });
});
