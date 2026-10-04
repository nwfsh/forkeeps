import { Pressable, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

// Placeholder: swap for the Figma button.

export type ButtonProps = {
  label: string;
  onPress?: () => void;
  variant?: 'primary' | 'secondary' | 'text';
  disabled?: boolean;
};

export function Button({ label, onPress, variant = 'primary', disabled }: ButtonProps) {
  const theme = useTheme();
  const background =
    variant === 'primary' ? theme.accent : variant === 'secondary' ? theme.backgroundElement : 'transparent';
  const color = variant === 'primary' ? theme.onAccent : variant === 'secondary' ? theme.text : theme.accent;

  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: background },
        (pressed || disabled) && styles.dimmed,
      ]}>
      <ThemedText style={[styles.label, { color }]}>{label}</ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 52,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.four,
  },
  label: {
    fontWeight: 600,
  },
  dimmed: {
    opacity: 0.6,
  },
});
