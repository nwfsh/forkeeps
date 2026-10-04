import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/placeholders/button';
import { Illustration } from '@/components/placeholders/illustration';
import { Screen } from '@/components/placeholders/screen';
import { Spacing } from '@/constants/theme';

export default function WelcomeScreen() {
  return (
    <Screen footer={<Button label="Get started" onPress={() => router.push('/onboarding/how-it-works')} />}>
      <View style={styles.center}>
        <Illustration name="welcome hero" height={320} />
        <View style={styles.text}>
          <ThemedText type="subtitle">Photo Coach</ThemedText>
          <ThemedText themeColor="textSecondary">
            Live coaching for photos of you that you’ll actually like.
          </ThemedText>
        </View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    justifyContent: 'center',
    gap: Spacing.five,
  },
  text: {
    gap: Spacing.two,
  },
});
