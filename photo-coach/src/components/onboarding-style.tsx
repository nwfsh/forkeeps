import { Image } from 'expo-image';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

/**
 * The onboarding look from the design: always light, a warm gradient fading to white, dark ink
 * text and a black pill button. Shared by the welcome and how-it-works screens.
 */
export const INK = '#1A1A1A';
export const MUTED = '#6E6E73';

const GRADIENTS = {
  // Warm, fading to white: the welcome screen.
  warm: require('@/assets/images/onboarding/welcome-gradient.png'),
  // Peach, coral and pink all the way down: how it works.
  multicolor: require('@/assets/images/onboarding/multicolor-gradient.png'),
};

/** One of the design's gradients, filling the screen from the top. */
export function GradientBackground({ kind = 'warm' }: { kind?: keyof typeof GRADIENTS }) {
  return (
    <Image
      source={GRADIENTS[kind]}
      style={StyleSheet.absoluteFill}
      contentFit="cover"
      contentPosition="top"
    />
  );
}

/** The ribbon logo at the given width, keeping its shape. */
export function Ribbon({ width }: { width: number }) {
  return (
    <Image
      source={require('@/assets/images/onboarding/ribbon.svg')}
      style={{ width, height: width * (139 / 122) }}
      contentFit="contain"
      accessibilityLabel="Photo Coach ribbon"
    />
  );
}

// The "PickTure" wordmark (cropped from myassets/PickTureFull 1.svg) and where its P
// sits in it, as shares of its width and height, so the ribbon can be laid over that P.
const WORDMARK_RATIO = 1825 / 817;
const WORDMARK_P = { width: 594 / 1825, height: 770 / 817 };

/** The wordmark at the given width with the ribbon laid over its P, so the two Ps are one. */
export function Wordmark({ width }: { width: number }) {
  const height = width / WORDMARK_RATIO;
  return (
    <View style={{ width, height }} accessibilityLabel="PickTure" accessibilityRole="image">
      <Image
        source={require('@/assets/images/onboarding/wordmark.png')}
        style={StyleSheet.absoluteFill}
        contentFit="contain"
      />
      <Image
        source={require('@/assets/images/onboarding/ribbon.svg')}
        style={[
          styles.wordmarkP,
          { width: width * WORDMARK_P.width, height: height * WORDMARK_P.height },
        ]}
        contentFit="fill"
      />
    </View>
  );
}

/** "Step 2 of 3" with a dot per step, the current one stretched into a dash. */
export function StepDots({ step, steps }: { step: number; steps: number }) {
  return (
    <View style={styles.stepRow}>
      <Text style={styles.step}>
        Step {step} of {steps}
      </Text>
      <View style={styles.dots}>
        {Array.from({ length: steps }, (_, i) => (
          <View
            key={i}
            style={[
              styles.dot,
              i + 1 === step && styles.dotCurrent,
              i + 1 > step && styles.dotLater,
            ]}
          />
        ))}
      </View>
    </View>
  );
}

/** The black pill button with its soft shadow. */
export function PillButton({
  label,
  onPress,
  disabled,
}: {
  label: ReactNode;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        pressed && styles.pressed,
        disabled && styles.disabled,
      ]}>
      <Text style={styles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wordmarkP: {
    position: 'absolute',
    left: 0,
    top: 0,
  },
  button: {
    alignSelf: 'stretch',
    height: 54,
    borderRadius: 999,
    backgroundColor: '#1B1B1B',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000000',
    shadowOpacity: 0.18,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 6,
  },
  pressed: {
    opacity: 0.85,
  },
  disabled: {
    opacity: 0.35,
  },
  stepRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  step: {
    color: MUTED,
    fontSize: 15,
  },
  dots: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: INK,
  },
  dotCurrent: {
    width: 32,
  },
  dotLater: {
    backgroundColor: 'rgba(26,26,26,0.15)',
  },
  label: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
});
