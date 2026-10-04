import { Image } from 'expo-image';
import { forwardRef, useImperativeHandle } from 'react';
import { Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  interpolate,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';

import type { Verdict } from '@/lib/server';
import { FontFamily } from '@/constants/theme';

// A drag past this share of the screen width, or a flick faster than FLICK (px/s), decides.
const DECIDE_AT = 0.3;
const FLICK = 800;
// How far the card leans at the edge of the screen.
const MAX_TILT = 12;
const FLY_MS = 220;

export type SwipeCardHandle = {
  /** Throws the card off as if swiped, e.g. from the ✕ and ♥ buttons. */
  swipe: (verdict: Verdict) => void;
};

type Props = {
  uri: string;
  /** Called once the card has left the screen. */
  onDecide: (verdict: Verdict) => void;
};

/** A photo you drag right to keep or left to remove, leaning and stamped as it goes. */
export const SwipeCard = forwardRef<SwipeCardHandle, Props>(function SwipeCard(
  { uri, onDecide },
  ref,
) {
  const { width } = useWindowDimensions();
  const x = useSharedValue(0);
  const y = useSharedValue(0);

  function flyOff(verdict: Verdict) {
    'worklet';
    const direction = verdict === 'keep' ? 1 : -1;
    x.set(
      withTiming(direction * width * 1.5, { duration: FLY_MS }, (finished) => {
        if (finished) runOnJS(onDecide)(verdict);
      }),
    );
  }

  useImperativeHandle(ref, () => ({ swipe: (verdict) => flyOff(verdict) }));

  const pan = Gesture.Pan()
    .onChange((e) => {
      x.set(x.get() + e.changeX);
      y.set(y.get() + e.changeY);
    })
    .onEnd((e) => {
      const decided = Math.abs(x.get()) > width * DECIDE_AT || Math.abs(e.velocityX) > FLICK;
      if (decided) {
        flyOff((Math.abs(e.velocityX) > FLICK ? e.velocityX : x.get()) > 0 ? 'keep' : 'remove');
      } else {
        x.set(withSpring(0));
      }
      y.set(withSpring(0));
    });

  const cardStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: x.get() },
      { translateY: y.get() },
      { rotate: `${interpolate(x.get(), [-width, width], [-MAX_TILT, MAX_TILT])}deg` },
    ],
  }));
  const keepStyle = useAnimatedStyle(() => ({
    opacity: interpolate(x.get(), [0, width * DECIDE_AT], [0, 1], 'clamp'),
  }));
  const removeStyle = useAnimatedStyle(() => ({
    opacity: interpolate(x.get(), [-width * DECIDE_AT, 0], [1, 0], 'clamp'),
  }));

  return (
    <GestureDetector gesture={pan}>
      <Animated.View style={[styles.card, cardStyle]}>
        <Image source={{ uri }} style={StyleSheet.absoluteFill} contentFit="cover" />
        <Animated.View style={[styles.stamp, styles.keepStamp, keepStyle]}>
          <Text style={[styles.stampText, styles.keepText]}>KEEP</Text>
        </Animated.View>
        <Animated.View style={[styles.stamp, styles.removeStamp, removeStyle]}>
          <Text style={[styles.stampText, styles.removeText]}>REMOVE</Text>
        </Animated.View>
      </Animated.View>
    </GestureDetector>
  );
});

/** The round ✕ or ♥ button under a swipe card, which throws the card the same way a swipe does. */
export function RoundButton({
  label,
  color,
  disabled,
  onPress,
  accessibilityLabel,
}: {
  label: string;
  color: string;
  disabled: boolean;
  onPress: () => void;
  accessibilityLabel: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.round,
        { borderColor: color },
        (pressed || disabled) && styles.pressed,
      ]}>
      <Text style={[styles.roundLabel, { color }]}>{label}</Text>
    </Pressable>
  );
}

/** The next photo, sitting still behind the one being swiped. */
export function NextCard({ uri }: { uri: string }) {
  return (
    <View style={[styles.card, styles.behind]}>
      <Image source={{ uri }} style={StyleSheet.absoluteFill} contentFit="cover" />
    </View>
  );
}

const KEEP = '#3DDC84';
const REMOVE = '#F87171';

const styles = StyleSheet.create({
  card: {
    ...StyleSheet.absoluteFill,
    borderRadius: 24,
    overflow: 'hidden',
    backgroundColor: '#222',
  },
  behind: {
    transform: [{ scale: 0.95 }, { translateY: 12 }],
    opacity: 0.6,
  },
  stamp: {
    position: 'absolute',
    top: 32,
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderWidth: 4,
    borderRadius: 8,
  },
  keepStamp: {
    left: 24,
    borderColor: KEEP,
    transform: [{ rotate: '-14deg' }],
  },
  removeStamp: {
    right: 24,
    borderColor: REMOVE,
    transform: [{ rotate: '14deg' }],
  },
  round: {
    width: 68,
    height: 68,
    borderRadius: 34,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(127,127,127,0.12)',
  },
  pressed: {
    opacity: 0.5,
  },
  roundLabel: {
    fontFamily: FontFamily.heading,
    fontSize: 28,
  },
  stampText: {
    fontFamily: FontFamily.headingBlack,
    fontSize: 32,
    letterSpacing: 2,
  },
  keepText: {
    color: KEEP,
  },
  removeText: {
    color: REMOVE,
  },
});
