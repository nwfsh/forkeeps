import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useEffect, useState, type ReactNode } from 'react';
import Reanimated, { Easing as ReEasing, Keyframe } from 'react-native-reanimated';
import {
  AccessibilityInfo,
  type LayoutChangeEvent,
  type StyleProp,
  type ViewStyle,
  Animated,
  Easing,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { FontFamily } from '@/constants/theme';

/**
 * The onboarding look from the design: always light, a warm gradient fading to white, dark ink
 * text and a black pill button. Shared by the welcome and how-it-works screens.
 */
export const INK = '#1A1A1A';
export const MUTED = '#6E6E73';
/**
 * Two colours with two jobs, so what each means is obvious:
 * - PRIMARY (black) for actions you press to move on: pill buttons, outlined buttons.
 * - ACCENT (brand) for where you are and what's chosen: progress bars, the current step, the
 *   chosen photo, the selected voice or lens, recording, and things waiting for you (Review, the
 *   retrain banner).
 * To go back to an all-black look, set ACCENT to PRIMARY; nothing else needs to change.
 */
export const PRIMARY = '#1B1B1B';
export const ACCENT = '#8F1042';

const GRADIENTS = {
  // Warm, fading to white: the welcome screen.
  warm: require('@/assets/images/onboarding/welcome-gradient.png'),
  // Peach, coral and pink all the way down: how it works.
  multicolor: require('@/assets/images/onboarding/multicolor-gradient.png'),
};

/** One of the design's gradients, filling the screen from the top. */
export function GradientBackground({
  kind = 'warm',
  moving = false,
}: {
  kind?: keyof typeof GRADIENTS;
  /** Drifts slowly, with the other gradient fading in and out over it, like light moving. */
  moving?: boolean;
}) {
  if (moving) return <MovingGradient kind={kind} />;
  return (
    <Image
      source={GRADIENTS[kind]}
      style={StyleSheet.absoluteFill}
      contentFit="cover"
      contentPosition="top"
    />
  );
}

// Half a drift cycle and half a colour cycle once settled; different lengths so the motion never
// quite repeats. On arrival both run a couple of quick sweeps first (INTRO_MS each way), then
// ease into these.
const DRIFT_MS = 6000;
const BLEND_MS = 8000;
const INTRO_MS = 1500;
const INTRO_SWEEPS = 2;

function MovingGradient({ kind }: { kind: keyof typeof GRADIENTS }) {
  const [drift] = useState(() => new Animated.Value(0));
  const [blend] = useState(() => new Animated.Value(0));

  useEffect(() => {
    const ease = Easing.inOut(Easing.sin);
    const sweep = (value: Animated.Value, ms: number) =>
      Animated.sequence([
        Animated.timing(value, { toValue: 1, duration: ms, easing: ease, useNativeDriver: true }),
        Animated.timing(value, { toValue: 0, duration: ms, easing: ease, useNativeDriver: true }),
      ]);
    // A lively start that settles into a slow, endless drift.
    const arriveThenSettle = (value: Animated.Value, ms: number) =>
      Animated.sequence([
        ...Array.from({ length: INTRO_SWEEPS }, (_, i) =>
          // Each intro sweep a little slower than the last, so the change of pace is gradual.
          sweep(value, INTRO_MS + ((ms - INTRO_MS) * i) / INTRO_SWEEPS),
        ),
        Animated.loop(sweep(value, ms)),
      ]);
    const animations = [arriveThenSettle(drift, DRIFT_MS), arriveThenSettle(blend, BLEND_MS)];
    let cancelled = false;
    // Still for anyone who has asked the phone to reduce motion.
    AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (!reduce && !cancelled) animations.forEach((a) => a.start());
    });
    return () => {
      cancelled = true;
      animations.forEach((a) => a.stop());
    };
  }, [drift, blend]);

  // Larger than the screen, so drifting never shows an edge.
  const moved = {
    transform: [
      { scale: drift.interpolate({ inputRange: [0, 1], outputRange: [1.2, 1.4] }) },
      { translateX: drift.interpolate({ inputRange: [0, 1], outputRange: [-36, 36] }) },
      { translateY: drift.interpolate({ inputRange: [0, 1], outputRange: [24, -30] }) },
    ],
  };
  const other = kind === 'warm' ? 'multicolor' : 'warm';
  return (
    <View style={[StyleSheet.absoluteFill, styles.clip]} pointerEvents="none">
      <Animated.View style={[StyleSheet.absoluteFill, moved]}>
        <Image
          source={GRADIENTS[kind]}
          style={StyleSheet.absoluteFill}
          contentFit="cover"
          contentPosition="top"
        />
        <Animated.View
          style={[
            StyleSheet.absoluteFill,
            { opacity: blend.interpolate({ inputRange: [0, 1], outputRange: [0, 0.6] }) },
          ]}>
          <Image
            source={GRADIENTS[other]}
            style={StyleSheet.absoluteFill}
            contentFit="cover"
            contentPosition="top"
          />
        </Animated.View>
      </Animated.View>
    </View>
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

// Each block of a page starts this long after the one before, top to bottom.
const APPEAR_STEP_MS = 90;
const easeOut = ReEasing.out(ReEasing.cubic);

/**
 * How a block comes in, matched to what it is:
 * - rise: fades up from just below (titles, text, and the main buttons last)
 * - drop: settles down from just above (back links, step dots, logos and icons)
 * - slide: comes in from the right (cards, fields, and list items one after another)
 * - glide: a longer slide that starts partway in and eases gently into place (instructions)
 */
const APPEARANCES = {
  rise: {
    ms: 520,
    frames: {
      0: { opacity: 0, transform: [{ translateY: 16 }] },
      100: { opacity: 1, transform: [{ translateY: 0 }], easing: easeOut },
    },
  },
  drop: {
    ms: 420,
    frames: {
      0: { opacity: 0, transform: [{ translateY: -12 }] },
      100: { opacity: 1, transform: [{ translateY: 0 }], easing: easeOut },
    },
  },
  slide: {
    ms: 480,
    frames: {
      0: { opacity: 0, transform: [{ translateX: 28 }] },
      100: { opacity: 1, transform: [{ translateX: 0 }], easing: easeOut },
    },
  },
  glide: {
    ms: 750,
    frames: {
      0: { opacity: 0.35, transform: [{ translateX: 60 }] },
      // Fast at first, then a long, gentle settle (an ease-out quint).
      100: {
        opacity: 1,
        transform: [{ translateX: 0 }],
        easing: ReEasing.bezier(0.22, 1, 0.36, 1),
      },
    },
  },
} as const;

export type Appearance = keyof typeof APPEARANCES;

/**
 * Brings its content in as a page opens. `order` staggers blocks down the page (0 first) and
 * `kind` picks the motion (see APPEARANCES). Reanimated runs it natively, and skips it under
 * Reduce Motion.
 */
export function Appear({
  order = 0,
  kind = 'rise',
  style,
  onLayout,
  children,
}: {
  order?: number;
  kind?: Appearance;
  style?: StyleProp<ViewStyle>;
  onLayout?: (event: LayoutChangeEvent) => void;
  children: ReactNode;
}) {
  const { ms, frames } = APPEARANCES[kind];
  return (
    <Reanimated.View
      entering={new Keyframe(frames).duration(ms).delay(order * APPEAR_STEP_MS)}
      style={style}
      onLayout={onLayout}>
      {children}
    </Reanimated.View>
  );
}

/** The "Back" link at the top of a page. */
export function BackLink({
  label = 'Back',
  onPress = () => router.back(),
}: {
  label?: string;
  onPress?: () => void;
}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} hitSlop={12} style={styles.backLink}>
      <Text style={styles.backText}>{label}</Text>
    </Pressable>
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
  backLink: {
    alignSelf: 'flex-start',
    minHeight: 32,
    justifyContent: 'center',
  },
  backText: {
    fontFamily: FontFamily.bodyBold,
    color: INK,
    fontSize: 16,
  },
  clip: {
    overflow: 'hidden',
  },
  wordmarkP: {
    position: 'absolute',
    left: 0,
    top: 0,
  },
  button: {
    alignSelf: 'stretch',
    height: 54,
    borderRadius: 999,
    backgroundColor: PRIMARY,
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
    fontFamily: FontFamily.body,
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
    backgroundColor: ACCENT,
  },
  dotLater: {
    backgroundColor: 'rgba(26,26,26,0.15)',
  },
  label: {
    fontFamily: FontFamily.bodyBold,
    color: '#FFFFFF',
    fontSize: 17,
  },
});
