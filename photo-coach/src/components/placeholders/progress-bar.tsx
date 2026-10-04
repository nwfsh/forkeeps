import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

// Placeholder: swap for the Figma progress indicator.

export function ProgressBar({ progress, label }: { progress: number; label?: string }) {
  const theme = useTheme();
  const clamped = Math.max(0, Math.min(1, progress));
  return (
    <View style={styles.wrap}>
      <View
        accessibilityRole="progressbar"
        accessibilityValue={{ min: 0, max: 100, now: Math.round(clamped * 100) }}
        style={[styles.track, { backgroundColor: theme.backgroundElement }]}>
        <View style={[styles.fill, { width: `${clamped * 100}%`, backgroundColor: theme.accent }]} />
      </View>
      {label && (
        <ThemedText type="small" themeColor="textSecondary">
          {label}
        </ThemedText>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: Spacing.one,
  },
  track: {
    height: 6,
    borderRadius: 3,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: 3,
  },
});
