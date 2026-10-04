import { useCameraPermissions } from 'expo-camera';
import { StyleSheet, View } from 'react-native';

import { useOnboarding } from '@/components/onboarding-provider';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/placeholders/button';
import { Illustration } from '@/components/placeholders/illustration';
import { Screen } from '@/components/placeholders/screen';
import { Spacing } from '@/constants/theme';

/**
 * Explains the camera before iOS/Android ask, so the system prompt isn't a surprise.
 * Finishing here swaps the app over to the camera tabs (see app/_layout.tsx).
 */
export default function CameraAccessScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const { finish } = useOnboarding();

  async function allow() {
    await requestPermission();
    // Finish either way: the camera tab has its own "Allow camera" button if they said no.
    finish();
  }

  const footer = permission?.granted ? (
    <Button label="Open the camera" onPress={finish} />
  ) : (
    <>
      <Button label="Allow camera" onPress={allow} />
      <Button variant="text" label="Not now" onPress={finish} />
    </>
  );

  return (
    <Screen back footer={footer}>
      <View style={styles.center}>
        <Illustration name="camera permission" height={260} />
        <View style={styles.text}>
          <ThemedText type="subtitle">Let Photo Coach see your shot</ThemedText>
          <ThemedText themeColor="textSecondary">
            The coach looks at the camera preview to give you tips on framing and expression. It only
            uses the camera while you’re on the camera screen.
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
