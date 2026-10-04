import { router } from 'expo-router';
import { SymbolView, type SymbolViewProps } from 'expo-symbols';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useOnboarding } from '@/components/onboarding-provider';
import {
  GradientBackground,
  INK,
  MUTED,
  PillButton,
  ACCENT,
  BackLink,
  Appear,
} from '@/components/onboarding-style';
import { confidenceLevel } from '@/lib/onboarding';
import type { RetrainResult } from '@/lib/server';
import { FontFamily } from '@/constants/theme';

type Weights = Record<string, number>;

/**
 * What the profile learned, grouped the way people think about a photo. Each group adds up its
 * features' shares (the angle's sweet-spot curve counts with the angle) and says which way they
 * lean, from the signs of the weights.
 */
const GROUPS: {
  title: string;
  icon: SymbolViewProps['name'];
  features: string[];
  lean: (w: Weights) => string | null;
}[] = [
  {
    title: 'Chin angle',
    icon: { ios: 'face.dashed', android: 'face', web: 'face' },
    features: ['chin_up', 'chin_up_curve'],
    lean: (w) => (w.chin_up === undefined ? null : w.chin_up < 0 ? 'Chin down' : 'Chin up'),
  },
  {
    title: 'Face turn',
    icon: { ios: 'arrow.left.and.right', android: 'swap_horiz', web: 'swap_horiz' },
    features: ['left_side', 'left_side_curve'],
    lean: (w) =>
      w.left_side === undefined
        ? null
        : w.left_side > 0
          ? 'Your left side toward the camera'
          : 'Your right side toward the camera',
  },
  {
    title: 'Smile',
    icon: { ios: 'face.smiling', android: 'mood', web: 'mood' },
    features: ['smile', 'teeth_shown'],
    lean: (w) => {
      const parts = [
        w.smile === undefined ? null : w.smile > 0 ? 'A bigger smile' : 'A softer smile',
        w.teeth_shown === undefined ? null : w.teeth_shown > 0 ? 'teeth showing' : 'lips closed',
      ].filter(Boolean);
      return parts.length ? parts.join(', ') : null;
    },
  },
  {
    title: 'Eyes',
    icon: { ios: 'eye', android: 'visibility', web: 'visibility' },
    features: ['eye_contact'],
    lean: (w) =>
      w.eye_contact === undefined
        ? null
        : w.eye_contact > 0
          ? 'Looking into the lens'
          : 'Looking just past the camera',
  },
];

function groupsFor(results: RetrainResult) {
  const weights: Weights = Object.fromEntries(results.priorities.map((p) => [p.feature, p.weight]));
  const shares = Object.fromEntries(results.priorities.map((p) => [p.feature, p.share]));
  return GROUPS.map((group) => ({
    ...group,
    share: group.features.reduce((sum, f) => sum + (shares[f] ?? 0), 0),
    detail: group.lean(weights),
  }))
    .filter((group) => group.features.some((f) => f in shares))
    .sort((a, b) => b.share - a.share);
}

/** "Your profile": what the picks taught the model, most important first. */
export default function ResultsScreen() {
  const { results } = useOnboarding();
  const insets = useSafeAreaInsets();
  const groups = results ? groupsFor(results) : [];
  const largest = Math.max(...groups.map((g) => g.share), 0);
  const unclear = results && confidenceLevel(results.confidence) === 'unclear';

  return (
    <View style={styles.screen}>
      <GradientBackground />
      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 50 },
        ]}>
        <View>
          <BackLink />
        </View>
        <View>
          <Text style={styles.title}>Your profile</Text>
        </View>

        <View style={styles.card}>
          {results ? (
            <>
              <Text style={styles.lead}>You care most about:</Text>
              <View style={styles.groups}>
                {groups.map((group, i) => (
                  <Appear key={group.title} kind="slide" order={3 + i} style={styles.group}>
                    <View style={styles.groupHeading}>
                      <SymbolView name={group.icon} size={22} tintColor={INK} />
                      <Text style={styles.groupTitle}>{group.title}</Text>
                    </View>
                    {group.detail && <Text style={styles.detail}>{group.detail}</Text>}
                    <View style={styles.track}>
                      <View
                        style={[
                          styles.bar,
                          { width: `${largest ? (group.share / largest) * 100 : 0}%` },
                        ]}
                      />
                    </View>
                  </Appear>
                ))}
              </View>
              <View style={styles.note}>
                <Text style={styles.noteText}>
                  {unclear
                    ? 'No clear pattern yet: your picks may depend on things we don’t measure, like lighting or outfit. Recording again sharpens it.'
                    : 'This updates as you keep or remove photos in review.'}
                </Text>
              </View>
            </>
          ) : (
            <>
              <Text style={styles.lead}>No profile yet.</Text>
              <Text style={styles.noteText}>Record and pick your favourites to build one.</Text>
            </>
          )}
        </View>

        {/* Pushed to the bottom of the screen, below the card. */}
        <View style={styles.footer}>
          <PillButton label="Continue" onPress={() => router.push('/onboarding/voice')} />
          <Pressable
            accessibilityRole="button"
            onPress={() => router.replace('/onboarding/record')}
            hitSlop={8}
            style={styles.again}>
            <Text style={styles.againText}>Record again</Text>
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  content: {
    flexGrow: 1,
    paddingHorizontal: 34,
    gap: 24,
  },
  title: {
    fontFamily: FontFamily.heading,
    color: INK,
    fontSize: 36,
    lineHeight: 45,
    letterSpacing: -0.6,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 32,
    padding: 24,
    gap: 28,
    shadowColor: '#000000',
    shadowOpacity: 0.06,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 3,
  },
  lead: {
    fontFamily: FontFamily.body,
    color: MUTED,
    fontSize: 17,
  },
  groups: {
    gap: 14,
  },
  group: {
    gap: 8,
  },
  groupHeading: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  groupTitle: {
    fontFamily: FontFamily.heading,
    color: INK,
    fontSize: 18,
  },
  detail: {
    fontFamily: FontFamily.body,
    color: MUTED,
    fontSize: 14,
    marginLeft: 34,
  },
  track: {
    height: 10,
    borderRadius: 5,
    backgroundColor: '#EEE9E6',
    overflow: 'hidden',
    marginTop: 4,
  },
  bar: {
    height: 10,
    borderRadius: 5,
    backgroundColor: ACCENT,
  },
  note: {
    borderRadius: 20,
    padding: 18,
    backgroundColor: '#F7F5F4',
    borderWidth: 1,
    borderColor: '#EFEBE8',
  },
  noteText: {
    fontFamily: FontFamily.body,
    color: MUTED,
    fontSize: 16,
    lineHeight: 22,
  },
  footer: {
    marginTop: 'auto',
    gap: 16,
  },
  again: {
    alignSelf: 'center',
  },
  againText: {
    fontFamily: FontFamily.bodyBold,
    color: MUTED,
    fontSize: 15,
  },
});
