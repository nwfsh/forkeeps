import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { GradientBackground, INK, MUTED, PillButton } from '@/components/onboarding-style';
import { clearMakeupLook, loadMakeupLook, saveMakeupLook, type MakeupLook } from '@/lib/server';

// How much redder than the forehead the lips or cheeks are, in words (server/makeup.py measures).
function strength(value: number, strong: number, soft: number) {
  return value >= strong ? 'Strong colour' : value >= soft ? 'Soft colour' : 'Barely any colour';
}

/**
 * Sets the person's makeup look from a photo of it: the server reads the lip and cheek colour,
 * and the camera reminds them to reapply when either fades well below it. A plain check against
 * this one photo, not part of the taste model. Shown in onboarding (optional) and from Photos.
 */
export function MakeupLookScreen({ doneLabel, onDone }: { doneLabel: string; onDone: () => void }) {
  const insets = useSafeAreaInsets();
  const [look, setLook] = useState<MakeupLook | null>(null);
  const [photo, setPhoto] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A look set before (from Photos, or a previous run) is shown straight away.
  useEffect(() => {
    let cancelled = false;
    loadMakeupLook()
      .then((saved) => !cancelled && setLook(saved))
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  async function use(source: 'library' | 'camera') {
    setError(null);
    const options: ImagePicker.ImagePickerOptions = {
      mediaTypes: ['images'],
      quality: 0.85,
      // JPEG rather than HEIC, and the look as it is: no edits.
      preferredAssetRepresentationMode:
        ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Compatible,
    };
    if (source === 'camera') {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) return setError('Allow the camera in Settings to take one.');
    }
    const picked =
      source === 'camera'
        ? await ImagePicker.launchCameraAsync({
            ...options,
            cameraType: ImagePicker.CameraType.front,
          })
        : await ImagePicker.launchImageLibraryAsync(options);
    if (picked.canceled || !picked.assets[0]) return;
    const uri = picked.assets[0].uri;
    setBusy(true);
    try {
      setLook(await saveMakeupLook(uri));
      setPhoto(uri);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await clearMakeupLook();
      setLook(null);
      setPhoto(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.screen}>
      <GradientBackground />
      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 32 },
        ]}>
        <View style={styles.topBar}>
          <Pressable accessibilityRole="button" onPress={() => router.back()} hitSlop={12}>
            <Text style={styles.back}>Back</Text>
          </Pressable>
          <Text style={styles.optional}>Optional</Text>
        </View>

        <View style={styles.copy}>
          <Text style={styles.title}>Your makeup look</Text>
          <Text style={styles.subtitle}>
            Pick a photo of your makeup the way you like it. We’ll read your lip and cheek colour,
            and remind you to reapply when it fades.
          </Text>
        </View>

        <View style={styles.card}>
          {loading || busy ? (
            <View style={styles.center}>
              <ActivityIndicator color={INK} />
              {busy && <Text style={styles.muted}>Reading your lips and cheeks…</Text>}
            </View>
          ) : look ? (
            <>
              {photo && <Image source={{ uri: photo }} style={styles.photo} contentFit="cover" />}
              <View style={styles.swatches}>
                <Swatch
                  label="Lips"
                  hex={look.lips_hex}
                  detail={strength(look.lip_colour, 0.06, 0.03)}
                />
                <Swatch
                  label="Cheeks"
                  hex={look.cheeks_hex}
                  detail={
                    look.checks_blush ? strength(look.blush, 0.04, 0.015) : 'Not checked: no blush'
                  }
                />
                <Swatch label="Skin" hex={look.skin_hex} detail="What they’re compared with" />
              </View>
              <Text style={styles.muted}>
                The coach will say when your lips{look.checks_blush ? ' or cheeks' : ''} fade well
                below this.
              </Text>
            </>
          ) : (
            <Text style={styles.muted}>
              A clear, front-on photo works best, in light like where you’ll be shooting.
            </Text>
          )}
          {error && <Text style={styles.error}>{error}</Text>}

          {!busy && (
            <View style={styles.actions}>
              <PillButton
                label={look ? 'Use a different photo' : 'Choose a photo'}
                onPress={() => use('library')}
              />
              <Pressable
                accessibilityRole="button"
                onPress={() => use('camera')}
                style={({ pressed }) => [styles.outline, pressed && styles.pressed]}>
                <Text style={styles.outlineText}>Take one now</Text>
              </Pressable>
              {look && (
                <Pressable accessibilityRole="button" onPress={remove} hitSlop={8}>
                  <Text style={styles.link}>Turn off makeup reminders</Text>
                </Pressable>
              )}
            </View>
          )}
        </View>

        <PillButton label={look ? doneLabel : 'Skip for now'} onPress={onDone} disabled={busy} />
      </ScrollView>
    </View>
  );
}

function Swatch({ label, hex, detail }: { label: string; hex: string; detail: string }) {
  return (
    <View style={styles.swatch}>
      <View style={[styles.dot, { backgroundColor: hex }]} />
      <View style={styles.swatchText}>
        <Text style={styles.swatchLabel}>{label}</Text>
        <Text style={styles.muted}>{detail}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  content: {
    paddingHorizontal: 20,
    gap: 20,
  },
  topBar: {
    minHeight: 44,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  back: {
    color: INK,
    fontSize: 16,
    fontWeight: '600',
  },
  optional: {
    color: MUTED,
    fontSize: 15,
  },
  copy: {
    gap: 10,
    paddingHorizontal: 4,
  },
  title: {
    color: INK,
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '700',
    letterSpacing: -0.6,
  },
  subtitle: {
    color: MUTED,
    fontSize: 17,
    lineHeight: 24,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 32,
    padding: 20,
    gap: 18,
    shadowColor: '#000000',
    shadowOpacity: 0.06,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 3,
  },
  center: {
    alignItems: 'center',
    gap: 12,
    paddingVertical: 24,
  },
  photo: {
    width: '100%',
    aspectRatio: 4 / 3,
    borderRadius: 20,
  },
  swatches: {
    gap: 14,
  },
  swatch: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  dot: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 2,
    borderColor: '#FFFFFF',
    shadowColor: '#000000',
    shadowOpacity: 0.12,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
  },
  swatchText: {
    flex: 1,
    gap: 2,
  },
  swatchLabel: {
    color: INK,
    fontSize: 17,
    fontWeight: '600',
  },
  muted: {
    color: MUTED,
    fontSize: 15,
    lineHeight: 21,
  },
  error: {
    color: '#B42318',
    fontSize: 15,
  },
  actions: {
    gap: 12,
    alignItems: 'center',
  },
  outline: {
    alignSelf: 'stretch',
    height: 50,
    borderRadius: 999,
    borderWidth: 1.5,
    borderColor: INK,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: {
    opacity: 0.6,
  },
  outlineText: {
    color: INK,
    fontSize: 16,
    fontWeight: '600',
  },
  link: {
    color: MUTED,
    fontSize: 15,
    fontWeight: '600',
  },
});
