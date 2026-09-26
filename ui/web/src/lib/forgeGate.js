// The gate on the Forge tab's "Mark forged" button.
//
// "Mark forged" asserts that the files on disk are the ones this project
// describes. The button was enabled through every state where that is
// false: before any forge had run at all, while one was still encoding,
// and after the project was edited out from under a finished render. On a
// long compilation the middle one is the dangerous case — the render can
// take hours, and the button sat there inviting a click the whole time.
//
// Why this is a module and not a boolean written inline in App.jsx:
// nothing in this suite mounts a component (see the note at the top of
// eslint.config.js), so a condition living in JSX cannot be tested at
// all. A gate that decides whether the user can lie to themselves about
// their own output should be tested.
//
// The comparison is on a SIGNATURE of what the engine would be handed —
// the stringified forgeproject, see projectAdapter.projectSignature — and
// deliberately not on the `dirty` flag. `dirty` is cleared by a plain
// Save, which would re-enable the button over a stale render, and it also
// trips for edits the engine never reads. Same bytes in, same output out.
export function markForgedGate({ forging, sig, forgedSig }) {
  if (forging) {
    return {
      enabled: false,
      reason: 'Still forging — this unlocks when the render finishes.',
    };
  }
  if (!forgedSig) {
    return {
      enabled: false,
      reason: 'Nothing forged yet — press Forge to render the output.',
    };
  }
  if (forgedSig !== sig) {
    return {
      enabled: false,
      reason: 'The project changed since the last forge — forge again so the files match.',
    };
  }
  return { enabled: true, reason: null };
}
