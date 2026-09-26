import { describe, it, expect } from 'vitest';
import { markForgedGate } from './forgeGate';

const SIG = '{"name":"comp","sections":[1,2]}';
const OTHER = '{"name":"comp","sections":[1,2,3]}';

describe('markForgedGate', () => {
  it('blocks while a forge is running, even when a previous render matched', () => {
    // The case this gate was added for: a multi-hour encode with the
    // button sitting enabled the whole way through.
    const g = markForgedGate({ forging: true, sig: SIG, forgedSig: SIG });
    expect(g.enabled).toBe(false);
  });

  it('blocks before anything has been forged', () => {
    expect(markForgedGate({ forging: false, sig: SIG, forgedSig: null }).enabled).toBe(false);
  });

  it('blocks when the project changed since the render that finished', () => {
    expect(markForgedGate({ forging: false, sig: OTHER, forgedSig: SIG }).enabled).toBe(false);
  });

  it('allows when a finished render matches the project', () => {
    const g = markForgedGate({ forging: false, sig: SIG, forgedSig: SIG });
    expect(g.enabled).toBe(true);
    expect(g.reason).toBeNull();
  });

  it('fails closed on an unsignable project', () => {
    // projectSignature returns null rather than throwing; null must never
    // read as "matches".
    expect(markForgedGate({ forging: false, sig: null, forgedSig: SIG }).enabled).toBe(false);
    expect(markForgedGate({ forging: false, sig: null, forgedSig: null }).enabled).toBe(false);
  });

  it('always explains why it blocked', () => {
    const blocked = [
      { forging: true, sig: SIG, forgedSig: SIG },
      { forging: false, sig: SIG, forgedSig: null },
      { forging: false, sig: OTHER, forgedSig: SIG },
    ];
    for (const s of blocked) {
      const g = markForgedGate(s);
      expect(g.enabled).toBe(false);
      expect(typeof g.reason).toBe('string');
      expect(g.reason.length).toBeGreaterThan(0);
    }
  });
});
