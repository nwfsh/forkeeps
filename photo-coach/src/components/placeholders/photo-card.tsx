import { Image } from 'expo-image';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import type { PhotoOption } from '@/lib/onboarding';

// Placeholder: swap for the Figma photo card.

export type PhotoCardProps = {
  photo: PhotoOption;
  onPress: () => void;
};

export function PhotoCard({ photo, onPress }: PhotoCardProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Pick ${photo.placeholderLabel}`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      {photo.uri ? (
        <Image source={{ uri: photo.uri }} style={styles.fill} contentFit="cover" />
      ) : (
        <View style={[styles.fill, styles.placeholder, { backgroundColor: photo.placeholderColor }]}>
          <ThemedText type="smallBold" style={styles.placeholderText}>
            {photo.placeholderLabel}
          </ThemedText>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    aspectRatio: 3 / 4,
    borderRadius: 20,
    overflow: 'hidden',
  },
  pressed: {
    transform: [{ scale: 0.97 }],
  },
  fill: {
    flex: 1,
  },
  placeholder: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 12,
  },
  placeholderText: {
    color: '#1C1C1E',
    textAlign: 'center',
  },
});
