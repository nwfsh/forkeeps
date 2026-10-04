import { Cantarell_400Regular, Cantarell_700Bold } from '@expo-google-fonts/cantarell';
import { Lato_700Bold, Lato_900Black } from '@expo-google-fonts/lato';
import { useFonts } from 'expo-font';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useColorScheme } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import { OnboardingProvider, useOnboarding } from '@/components/onboarding-provider';
import { PhotosProvider } from '@/components/photos-provider';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const colorScheme = useColorScheme();
  // The app's typefaces (constants/theme FontFamily). Until they're in, nothing renders, so the
  // splash screen stays up and no text shows in the system font first. A font that fails to load
  // just falls back to the system one.
  const [fontsLoaded, fontError] = useFonts({
    Lato_700Bold,
    Lato_900Black,
    Cantarell_400Regular,
    Cantarell_700Bold,
  });
  if (!fontsLoaded && !fontError) return null;

  return (
    // Swipeable cards (photo review) need gestures handled from the root.
    <GestureHandlerRootView style={{ flex: 1 }}>
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
        <OnboardingProvider>
          <PhotosProvider>
            <AnimatedSplashOverlay />
            <RootStack />
          </PhotosProvider>
        </OnboardingProvider>
      </ThemeProvider>
    </GestureHandlerRootView>
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
        <Stack.Screen name="review" options={{ presentation: 'fullScreenModal' }} />
        <Stack.Screen name="angles" options={{ presentation: 'fullScreenModal' }} />
        <Stack.Screen name="makeup" options={{ presentation: 'fullScreenModal' }} />
        <Stack.Screen name="tune" options={{ presentation: 'fullScreenModal' }} />
      </Stack.Protected>
    </Stack>
  );
}
