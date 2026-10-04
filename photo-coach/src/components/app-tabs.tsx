import { NativeTabs } from 'expo-router/unstable-native-tabs';
import { useColorScheme } from 'react-native';

import { Colors } from '@/constants/theme';

export default function AppTabs() {
  const scheme = useColorScheme();
  const colors = Colors[scheme === 'unspecified' ? 'light' : scheme];

  return (
    <NativeTabs
      backgroundColor={colors.background}
      indicatorColor={colors.backgroundElement}
      labelStyle={{ selected: { color: colors.text } }}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Label>Camera</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="camera" />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="photos">
        <NativeTabs.Trigger.Label>Photos</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="photo.on.rectangle" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
