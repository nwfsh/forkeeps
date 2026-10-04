import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Priority } from '@/lib/onboarding';

// Placeholder: swap for the Figma priority / trait row.

export function PriorityRow({ priority, largestShare }: { priority: Priority; largestShare: number }) {
  const theme = useTheme();
  const direction = priority.weight > 0 ? 'more' : 'less';
  // Bars are scaled to the top priority so the biggest one fills the row.
  const width = largestShare > 0 ? priority.share / largestShare : 0;
  return (
    <View
      style={styles.row}
      accessible
      accessibilityLabel={`${priority.label}, ${direction}, ${Math.round(priority.share * 100)} percent`}>
      <View style={styles.labels}>
        <ThemedText style={styles.label}>{priority.label}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {direction} · {Math.round(priority.share * 100)}%
        </ThemedText>
      </View>
      <View style={[styles.track, { backgroundColor: theme.backgroundElement }]}>
        <View style={[styles.bar, { width: `${width * 100}%`, backgroundColor: theme.accent }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: Spacing.one,
  },
  labels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    gap: Spacing.two,
  },
  label: {
    flex: 1,
    fontWeight: 600,
  },
  track: {
    height: 8,
    borderRadius: 4,
    overflow: 'hidden',
  },
  bar: {
    height: '100%',
    borderRadius: 4,
  },
});
