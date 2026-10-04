import { Stack } from 'expo-router';

/**
 * The camera, with the gallery on top of it: no tab bar. The camera's last-photo button opens
 * the gallery; the gallery's "Back to camera" (or a swipe from the left edge) returns.
 */
export default function CameraLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="photos" />
    </Stack>
  );
}
