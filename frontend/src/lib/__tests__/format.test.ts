import { afterEach, describe, expect, it, vi } from 'vitest';
import { copyToClipboard } from '../utils/format';

afterEach(() => vi.unstubAllGlobals());

describe('copyToClipboard', () => {
  it('copies from a provided visible input', async () => {
    const input = {
      focus: vi.fn(),
      select: vi.fn(),
      setSelectionRange: vi.fn(),
    };
    const createElement = vi.fn();

    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    });
    vi.stubGlobal('document', {
      createElement,
      execCommand: vi.fn(() => true),
    });

    await expect(
      copyToClipboard('lgw-test', input as unknown as HTMLInputElement)
    ).resolves.toBe(true);
    expect(input.focus).toHaveBeenCalled();
    expect(input.select).toHaveBeenCalled();
    expect(input.setSelectionRange).toHaveBeenCalledWith(0, 8);
    expect(createElement).not.toHaveBeenCalled();
  });

  it('uses the synchronous fallback before Clipboard API', async () => {
    const textarea = {
      value: '',
      style: {},
      setAttribute: vi.fn(),
      focus: vi.fn(),
      select: vi.fn(),
      setSelectionRange: vi.fn(),
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
