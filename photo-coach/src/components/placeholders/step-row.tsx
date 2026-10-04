import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

// Placeholder: swap for the Figma step / feature row.

export function StepRow({ number, title, body }: { number: number; title: string; body: string }) {
  const theme = useTheme();
  return (
    <View style={styles.row}>
      <View style={[styles.number, { backgroundColor: theme.accent }]}>
        <ThemedText style={[styles.numberText, { color: theme.onAccent }]}>{number}</ThemedText>
      </View>
      <View style={styles.text}>
        <ThemedText style={styles.title}>{title}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {body}
        </ThemedText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: Spacing.three,
    alignItems: 'flex-start',
  },
  number: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  numberText: {
    fontWeight: 700,
  },
  text: {
    flex: 1,
    gap: Spacing.half,
  },
  title: {
    fontWeight: 600,
  },
});
