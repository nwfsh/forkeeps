import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MaxContentWidth, Spacing } from '@/constants/theme';

// Placeholder: swap for the Figma page layout.

export type ScreenProps = {
  children: ReactNode;
  /** Buttons pinned to the bottom of the screen. */
  footer?: ReactNode;
  /** Shows a back button that goes to the previous screen. */
  back?: boolean;
  /** Top-right corner, e.g. a Skip button. */
  topRight?: ReactNode;
};

export function Screen({ children, footer, back, topRight }: ScreenProps) {
  return (
    <ThemedView style={styles.fill}>
      <SafeAreaView style={styles.fill}>
        <View style={styles.topBar}>
          {back && router.canGoBack() ? (
            <Pressable accessibilityRole="button" onPress={() => router.back()} hitSlop={12}>
              <ThemedText themeColor="textSecondary">Back</ThemedText>
            </Pressable>
          ) : (
            <View />
          )}
          {topRight}
        </View>
        <ScrollView contentContainerStyle={styles.content}>{children}</ScrollView>
        {footer && <View style={styles.footer}>{footer}</View>}
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
  },
  topBar: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.four,
  },
  content: {
    flexGrow: 1,
    gap: Spacing.four,
    padding: Spacing.four,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  footer: {
    gap: Spacing.two,
    paddingHorizontal: Spacing.four,
    paddingBottom: Spacing.three,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
});
