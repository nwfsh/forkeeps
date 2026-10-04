import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { useTheme } from '@/hooks/use-theme';

// Placeholder: marks where a Figma illustration goes. Replace with the exported artwork.

export function Illustration({ name, height = 240 }: { name: string; height?: number }) {
  const theme = useTheme();
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.box, { height, borderColor: theme.textSecondary, backgroundColor: theme.backgroundElement }]}>
      <ThemedText type="small" themeColor="textSecondary">
        Illustration: {name}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    width: '100%',
    borderRadius: 24,
    borderWidth: 1.5,
    borderStyle: 'dashed',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
