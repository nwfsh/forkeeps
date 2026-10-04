import { router } from 'expo-router';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  GradientBackground,
  INK,
  MUTED,
  PillButton,
  StepDots,
} from '@/components/onboarding-style';
import { cleanProfileName } from '@/lib/profile';
import { currentPerson, setPerson } from '@/lib/server';

/** Names this phone's taste profile: the picks train it and the camera coaches with it. */
export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const existing = currentPerson();
  const [name, setName] = useState(existing === 'me' ? '' : existing);
  const clean = cleanProfileName(name);

  function save() {
    setPerson(clean);
    router.push('/onboarding/camera-access');
  }

  return (
    <View style={styles.screen}>
      <GradientBackground />
      <KeyboardAvoidingView
        style={styles.fill}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={[styles.content, { paddingTop: insets.top + 8 }]}>
          <View style={styles.topBar}>
            <Pressable accessibilityRole="button" onPress={() => router.back()} hitSlop={12}>
              <Text style={styles.back}>Back</Text>
            </Pressable>
          </View>

          <StepDots step={1} steps={3} />

          <View style={styles.copy}>
            <Text style={styles.title}>Name your profile</Text>
            <Text style={styles.subtitle}>
              Your picks teach it what you like, and the camera coaches you with it. Use the same
              name to keep training it later.
            </Text>
          </View>

          <View style={styles.field}>
            <TextInput
              value={name}
              onChangeText={setName}
              placeholder="e.g. avery"
              placeholderTextColor="#A1A1A6"
              autoCapitalize="none"
              autoCorrect={false}
              autoFocus
              returnKeyType="done"
              onSubmitEditing={() => clean && save()}
              style={styles.input}
            />
          </View>
          {name !== '' && clean !== name.trim() && (
            <Text style={styles.hint}>
              Saved as “{clean || '…'}”: letters, numbers, - and _ only.
            </Text>
          )}
        </View>

        <View style={[styles.footer, { paddingBottom: insets.bottom + 16 }]}>
          <PillButton label="Continue" onPress={save} disabled={!clean} />
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  fill: {
    flex: 1,
  },
  content: {
    flex: 1,
    paddingHorizontal: 24,
    gap: 20,
  },
  topBar: {
    minHeight: 44,
    justifyContent: 'center',
  },
  back: {
    color: INK,
    fontSize: 16,
    fontWeight: '600',
  },
  copy: {
    gap: 10,
    marginTop: 12,
  },
  title: {
    color: INK,
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '700',
    letterSpacing: -0.6,
  },
  subtitle: {
    color: MUTED,
    fontSize: 17,
    lineHeight: 24,
  },
  field: {
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    marginTop: 8,
    shadowColor: '#000000',
    shadowOpacity: 0.06,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
  input: {
    color: INK,
    fontSize: 20,
    paddingHorizontal: 20,
    paddingVertical: 18,
  },
  hint: {
    color: MUTED,
    fontSize: 14,
  },
  footer: {
    paddingHorizontal: 20,
    paddingTop: 12,
  },
});
