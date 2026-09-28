// Where a title card's words come from before the user types any.
//
// A chapter card names the scene it introduces, and an opening title page
// names the compilation — both of which are already sitting in a path. Typing
// them again for every joiner is the slow part of building a compilation, so
// picking a title card pre-fills the text from the file or folder it belongs
// to. This changes NOTHING about which joiner a scene gets by default: the
// default joiner is still `none`. It only means that once you choose a title
// card, there are already words on it.
//
// The names are real ones off a disk, not slugs someone designed:
//
//   -madmartigan----its-just-ai-sex.mp4      → Madmartigan its just ai sex
//   -Madmartigan- - It's Just AI Sex         → Madmartigan It's Just AI Sex
//
// Everything here is a starting point the user will edit, so the rules err
// towards preserving what was written rather than beautifying it.

const EXT = /\.[A-Za-z0-9]{1,5}$/;

function basename(path) {
  return String(path || '').replace(/\\/g, '/').replace(/\/+$/, '').split('/').pop() || '';
}

function isWordish(ch) {
  return ch != null && /[A-Za-z0-9]/.test(ch);
}

/** Turn a bare file or folder name into words fit for a card. */
export function tidyName(raw) {
  let s = String(raw || '').replace(/_/g, ' ');

  if (!/\s/.test(s)) {
    // No spaces anywhere: it is a slug, so every hyphen is a word break.
    s = s.replace(/-/g, ' ');
  } else {
    // It already reads as words, so a hyphen is only a separator when it is
    // NOT joining two characters — which keeps `FOC-Stim` and `4-phase`
    // intact while dropping the decoration in `-Madmartigan- - It's …`.
    s = s.replace(/-+/g, (m, i, str) => (
      m.length === 1 && isWordish(str[i - 1]) && isWordish(str[i + 1]) ? m : ' '
    ));
  }

  s = s.replace(/\s+/g, ' ').trim();

  // Only when the name carried no case information of its own. A name that
  // was already capitalised is left exactly as written — title-casing
  // `It's Just AI Sex` would give back `It'S Just Ai Sex`.
  if (s && s === s.toLowerCase()) s = s[0].toUpperCase() + s.slice(1);
  return s;
}

/** The words to put on a card introducing `clip`. */
export function titleForClip(clip) {
  if (!clip) return '';
  // A bookmark is a name a person chose; it beats anything derived from a
  // filename, and it is what the scene row already shows.
  if (clip.title && String(clip.title).trim()) return String(clip.title).trim();
  const base = basename(clip.file);
  return base ? tidyName(base.replace(EXT, '')) : '';
}

/** The words to put on the compilation's own title page. */
export function titleForFolder(path) {
  const base = basename(path);
  // A folder has no extension to strip — `My Show 2.0` must not become
  // `My Show 2`.
  return base ? tidyName(base) : '';
}
