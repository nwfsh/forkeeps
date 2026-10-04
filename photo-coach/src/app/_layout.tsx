import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useColorScheme } from 'react-native';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import { OnboardingProvider, useOnboarding } from '@/components/onboarding-provider';
import { PhotosProvider } from '@/components/photos-provider';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const colorScheme = useColorScheme();
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <OnboardingProvider>
        <PhotosProvider>
          <AnimatedSplashOverlay />
          <RootStack />
        </PhotosProvider>
      </OnboardingProvider>
    </ThemeProvider>
  );
}

/** Onboarding until it's finished, then the camera tabs. Each side redirects to the other. */
function RootStack() {
  const { finished } = useOnboarding();
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={!finished}>
        <Stack.Screen name="onboarding" />
      </Stack.Protected>
      <Stack.Protected guard={finished}>
        <Stack.Screen name="(tabs)" />
      </Stack.Protected>
    </Stack>
  );
}
