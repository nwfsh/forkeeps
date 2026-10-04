import { File, Paths } from 'expo-file-system';

/**
 * The profile name chosen in onboarding. It names this phone's taste model on the server
 * (its swipes and its weights), so it's kept on the phone and sent with every request.
 */
const profileFile = new File(Paths.document, 'profile.json');

export function loadProfileName(): string | null {
  if (!profileFile.exists) return null;
  try {
    const name = JSON.parse(profileFile.textSync()).name;
    return typeof name === 'string' && name ? name : null;
  } catch {
    return null;
  }
}

export function saveProfileName(name: string) {
  profileFile.write(JSON.stringify({ name }));
}

/** A profile name as the server stores it: letters, numbers, - and _, lower case. */
export function cleanProfileName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, '');
}
